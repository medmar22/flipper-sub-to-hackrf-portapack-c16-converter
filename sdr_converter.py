import os
import argparse
import math
from typing import List, Tuple, Dict, Any, Optional
import numpy as np
import wave
import logging
import sys
# ---- NEW: Import SciPy for resampling ----
try:
    from scipy import signal
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False
# ----------------------------------------

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

SUPPORTED_PROTOCOLS = ['RAW', 'BinRAW']
DEFAULT_FREQUENCY = 433920000 # Default Hz (e.g., 433.92 MHz)
DEFAULT_SAMPLING_RATE = 1000000 # Default samples/sec (e.g., 1 MSps)
DEFAULT_INTERMEDIATE_FREQ = 50000 # Default Hz for SUB synthesis
DEFAULT_AMPLITUDE = 100 # Default % for SUB synthesis

# --- Helper for resampling ---
def _greatest_common_divisor(a: int, b: int) -> int:
    """Calculates the greatest common divisor."""
    return math.gcd(a, b) # Available in Python 3.5+
# ----------------------------

# =============================================================================
# Parsing Functions (Read data from input files)
# =============================================================================

def parse_sub(file: str) -> Dict[str, Any]:
    """Parses Flipper Zero .sub files (RAW protocol)."""
    logging.info(f"Parsing SUB file: {file}")
    info: Dict[str, Any] = {'file_type': '.sub', 'frequency': None, 'protocol': None, 'sampling_rate': None} # Add sampling_rate=None
    data_lines = []
    data_started = False
    try:
        with open(file, 'r') as f:
            lines = f.readlines()
    except Exception as e:
        logging.error(f'Cannot read input file "{file}": {e}')
        sys.exit(-1)

    for line in lines:
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if line.startswith('RAW_Data:'):
            data_started = True
            data_part = line[len('RAW_Data:'):].strip()
            if data_part:
                data_lines.append(data_part)
        elif data_started:
            data_lines.append(line)
        elif ':' in line:
            k, v = line.split(':', 1)
            info[k.strip().lower()] = v.strip()
        else:
            continue

    if info.get('protocol') not in SUPPORTED_PROTOCOLS:
        logging.error(f'Failed to parse {file}: Supported protocols are {", ".join(SUPPORTED_PROTOCOLS)} (found: {info.get("protocol")})')
        logging.warning("Proceeding anyway, but results may be unexpected.")

    try:
        if info.get('frequency'):
            freq_str = ''.join(filter(str.isdigit, info['frequency']))
            if freq_str: info['frequency'] = int(freq_str)
            else: info['frequency'] = None
    except ValueError:
        logging.warning(f"Could not parse frequency '{info.get('frequency')}' in {file}. Using default or user value.")
        info['frequency'] = None

    durations: List[int] = []
    for line in data_lines:
        for value in line.strip().split():
            if not value: continue
            try:
                durations.append(int(value))
            except ValueError:
                logging.error(f"Invalid non-integer value '{value}' found in RAW_Data section of {file}.")
                sys.exit(-1)

    if not durations:
        logging.error(f"No RAW_Data found or parsed in {file}.")
        sys.exit(-1)

    info['raw_durations'] = durations
    # SUB files do not have an intrinsic sample rate for the RAW data itself
    info['sampling_rate'] = None
    logging.info(f"Parsed {len(durations)} durations from {file}.")
    return info

def parse_wav(file: str) -> Dict[str, Any]:
    """Parses RIFF WAVE (.wav) files (mono, 16-bit PCM assumed)."""
    logging.info(f"Parsing WAV file: {file}")
    try:
        with wave.open(file, 'r') as wf:
            nchannels = wf.getnchannels()
            sampwidth = wf.getsampwidth()
            framerate = wf.getframerate()
            nframes = wf.getnframes()

            if nchannels != 1:
                logging.error(f"WAV file {file} has {nchannels} channels. Only mono WAV files are supported.")
                sys.exit(-1)

            if sampwidth != 2: # 2 bytes = 16 bits
                logging.error(f"WAV file {file} has sample width {sampwidth*8}-bit. Only 16-bit WAV files are supported.")
                sys.exit(-1)

            logging.info(f"WAV properties: Rate={framerate} Hz, Channels={nchannels}, Width={sampwidth*8}-bit, Frames={nframes}")

            audio_data = wf.readframes(nframes)
            # Data is already int16 PCM bytes
            samples = np.frombuffer(audio_data, dtype=np.int16).tolist()

            info = {
                'file_type': '.wav',
                'sampling_rate': framerate, # Original sample rate
                'samples_i': samples,      # Treat mono audio as I component
                'samples_q': [0] * len(samples), # Create zero Q component
                'frequency': None # WAV doesn't store center frequency
            }
            logging.info(f"Parsed {len(samples)} samples from {file}.")
            return info
    except wave.Error as e:
        logging.error(f'Error opening or reading WAV file "{file}": {e}')
        sys.exit(-1)
    except Exception as e:
        logging.error(f'Unexpected error parsing WAV file "{file}": {e}')
        sys.exit(-1)

def parse_iq(file: str) -> Dict[str, Any]:
    """Parses raw interleaved IQ files (assuming int16 format)."""
    logging.info(f"Parsing IQ (int16) file: {file}")
    try:
        with open(file, 'rb') as f:
            iq_data = f.read()
        samples = np.frombuffer(iq_data, dtype=np.int16)

        if len(samples) % 2 != 0:
            logging.warning(f"IQ file {file} has an odd number of int16 values ({len(samples)}). The last value will be discarded.")
            samples = samples[:-1]

        if len(samples) == 0:
            logging.error(f"No valid IQ data found in file {file}.")
            sys.exit(-1)

        samples_i = samples[0::2].tolist()
        samples_q = samples[1::2].tolist()

        info = {
            'file_type': '.iq',
            'samples_i': samples_i,
            'samples_q': samples_q,
            'sampling_rate': None, # Cannot know from raw file
            'frequency': None
        }
        logging.info(f"Parsed {len(samples_i)} IQ pairs from {file}.")
        return info
    except Exception as e:
        logging.error(f'Cannot read IQ file "{file}": {e}')
        sys.exit(-1)

def parse_bin(file: str) -> Dict[str, Any]:
    """Parses raw interleaved IQ files (assuming uint8 format)."""
    logging.info(f"Parsing BIN (uint8 IQ) file: {file}")
    try:
        with open(file, 'rb') as f:
            bin_data = f.read()
        samples_u8 = np.frombuffer(bin_data, dtype=np.uint8)

        if len(samples_u8) % 2 != 0:
            logging.warning(f"BIN file {file} has an odd number of bytes ({len(samples_u8)}). The last byte will be discarded.")
            samples_u8 = samples_u8[:-1]

        if len(samples_u8) == 0:
            logging.error(f"No valid data found in file {file}.")
            sys.exit(-1)

        # Convert uint8 (0..255) to int16 (-32k..+32k), centered around 0
        samples_int16 = ((samples_u8.astype(np.float32) - 128.0) * 256.0).astype(np.int16)

        samples_i = samples_int16[0::2].tolist()
        samples_q = samples_int16[1::2].tolist()

        info = {
            'file_type': '.bin',
            'samples_i': samples_i,
            'samples_q': samples_q,
            'sampling_rate': None, # Cannot know from raw file
            'frequency': None
        }
        logging.info(f"Parsed and converted {len(samples_i)} uint8 IQ pairs from {file}.")
        return info
    except Exception as e:
        logging.error(f'Cannot read BIN file "{file}": {e}')
        sys.exit(-1)

# =============================================================================
# IQ Synthesis Functions (for .sub files)
# =============================================================================

def us_to_sin(level: bool, duration_us: int, sampling_rate: int, intermediate_freq: int, amplitude_percent: int) -> List[Tuple[int, int]]:
    """Generates IQ samples for a single duration pulse."""
    if duration_us <= 0: return []
    num_samples = int(round(sampling_rate * duration_us / 1_000_000)) # Use round for better accuracy
    if num_samples == 0: return []
    if not level: return [(0, 0)] * num_samples

    phase_step_per_sample = 2 * math.pi * intermediate_freq / sampling_rate
    max_amplitude_int16 = int(32767 * (amplitude_percent / 100.0))
    samples = [
        (
            int(math.cos(i * phase_step_per_sample) * max_amplitude_int16),
            int(math.sin(i * phase_step_per_sample) * max_amplitude_int16)
        )
        for i in range(num_samples)
    ]
    return samples

def durations_to_iq_sequence(durations: List[int], sampling_rate: int, intermediate_freq: int, amplitude_percent: int) -> List[Tuple[int, int]]:
    """Converts a list of +/- microsecond durations into an IQ sample sequence."""
    if not durations: return []
    logging.info(f"Synthesizing IQ sequence: SR={sampling_rate}Hz, IF={intermediate_freq}Hz, Ampl={amplitude_percent}%")
    sequence = []
    current_phase = 0.0 # Maintain phase across pulses for smoother transitions
    phase_step_per_sample = 2 * math.pi * intermediate_freq / sampling_rate
    max_amplitude_int16 = int(32767 * (amplitude_percent / 100.0))

    for duration_us in durations:
        is_high_level = duration_us > 0
        abs_duration_us = abs(duration_us)
        num_samples = int(round(sampling_rate * abs_duration_us / 1_000_000))
        if num_samples == 0: continue

        if not is_high_level:
            # Append zeros for low level
            sequence.extend([(0, 0)] * num_samples)
        else:
            # Append sine wave samples, continuing phase
            chunk_samples = []
            for i in range(num_samples):
                i_samp = int(math.cos(current_phase) * max_amplitude_int16)
                q_samp = int(math.sin(current_phase) * max_amplitude_int16)
                chunk_samples.append((i_samp, q_samp))
                current_phase += phase_step_per_sample
            sequence.extend(chunk_samples)
        # Keep phase within [0, 2*pi) for numerical stability (optional but good practice)
        current_phase = math.fmod(current_phase, 2 * math.pi)

    logging.info(f"Synthesized {len(sequence)} IQ samples.")
    if sequence:
        min_i, max_i = min(s[0] for s in sequence), max(s[0] for s in sequence)
        min_q, max_q = min(s[1] for s in sequence), max(s[1] for s in sequence)
        logging.info(f'Synthesized IQ Range -> I:[{min_i},{max_i}], Q:[{min_q},{max_q}]')
    return sequence

# =============================================================================
# Output Functions
# =============================================================================

def build_iq_sequence_from_samples(samples_i: List[int], samples_q: List[int]) -> List[Tuple[int, int]]:
    """Combines I and Q sample lists into an IQ sequence, clamping to int16 range."""
    if len(samples_i) != len(samples_q):
         logging.error(f"Internal error: I ({len(samples_i)}) and Q ({len(samples_q)}) sample lists have different lengths.")
         sys.exit(-1)
    max_val, min_val = 32767, -32768
    return [
        (max(min_val, min(max_val, int(round(i)))), max(min_val, min(max_val, int(round(q)))))
        for i, q in zip(samples_i, samples_q)
    ] # Use round before int cast after potential float operations (like resampling)

def sequence_to_16le_buffer(sequence: List[Tuple[int, int]]) -> bytes:
    """Converts a list of (I, Q) int tuples into a little-endian int16 byte buffer."""
    if not sequence: return b''
    iq_array = np.array(sequence, dtype=np.int16)
    buffer = iq_array.astype('<i2').tobytes()
    return buffer

def generate_meta_string(frequency: Optional[int], sampling_rate: int) -> str:
    """Generates the metadata string for the .txt file."""
    freq_str = str(frequency) if frequency is not None else 'UNKNOWN'
    sr_str = str(sampling_rate)
    meta = [['sample_rate', sr_str], ['center_frequency', freq_str]]
    return '\n'.join(' = '.join(map(str, r)) for r in meta)

def write_hrf_files(output_base_path: str, buffer: bytes, frequency: Optional[int], sampling_rate: int) -> List[str]:
    """Writes the C16 IQ data and the TXT metadata file."""
    c16_path = f'{output_base_path}.c16'
    txt_path = f'{output_base_path}.txt'
    paths = [c16_path, txt_path]

    try:
        logging.info(f"Writing IQ data to: {c16_path} ({len(buffer)/1024:.2f} kiB)")
        with open(c16_path, 'wb') as f: f.write(buffer)
        logging.info(f"Writing metadata to: {txt_path}")
        with open(txt_path, 'w') as f: f.write(generate_meta_string(frequency, sampling_rate))
    except Exception as e:
        logging.error(f'Cannot write output file(s) starting with "{output_base_path}": {e}')
        sys.exit(-1)

    duration_seconds = (len(buffer) / 4) / sampling_rate if sampling_rate > 0 else 0
    logging.info(f'Written {len(buffer) / 1024:.2f} kiB, representing {duration_seconds:.3f} seconds of IQ data at {sampling_rate} Hz.')
    return paths

# =============================================================================
# Main Processing Logic
# =============================================================================

def auto_detect_parameters(file: str) -> Dict[str, Any]:
    """Attempts to detect parameters based on file type."""
    file_ext = os.path.splitext(file)[1].lower()
    params = {'sampling_rate': None, 'frequency': None, 'intermediate_freq': None, 'amplitude': DEFAULT_AMPLITUDE } # Init amplitude here

    logging.info(f"Auto-detecting parameters for file: {file}")

    try:
        if file_ext == '.sub':
             partial_info = parse_sub(file) # Need freq from here
             params['frequency'] = partial_info.get('frequency')
             params['sampling_rate'] = None # Cannot auto-detect SR for SUB synthesis
        elif file_ext == '.wav':
             with wave.open(file, 'r') as wf:
                 params['sampling_rate'] = wf.getframerate() # Can detect SR from WAV
             params['frequency'] = None # Cannot detect freq from WAV
    except Exception as e:
        logging.warning(f"Could not auto-detect some parameters from {file}: {e}")

    # Apply general defaults where detection wasn't possible or failed
    params['sampling_rate'] = params['sampling_rate'] or DEFAULT_SAMPLING_RATE
    params['frequency'] = params['frequency'] or DEFAULT_FREQUENCY

    # Set IF based on frequency (only relevant for SUB)
    if params['frequency']:
         params['intermediate_freq'] = min(params['frequency'] // 100, DEFAULT_INTERMEDIATE_FREQ)
    else: # Fallback if frequency is unknown
         params['intermediate_freq'] = DEFAULT_INTERMEDIATE_FREQ

    logging.info(f"Auto-detected parameters -> Sampling Rate: {params['sampling_rate']}, Frequency: {params['frequency']}, "
                 f"IF (for .sub): {params['intermediate_freq']}, Amplitude (for .sub): {params['amplitude']}")
    return params

def process_file(input_file: str, output_base_path: str,
                 target_sampling_rate: int, target_frequency: Optional[int], # Target output params
                 intermediate_freq: int, amplitude_percent: int, # Only for SUB synthesis
                 verbose: bool):
    """Parses, optionally resamples, and converts an input file to C16/TXT format."""

    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        logging.debug(f'Processing: {input_file} -> {output_base_path}.[c16,txt]')
        logging.debug(f'Target Params: SR={target_sampling_rate}, Freq={target_frequency}, IF={intermediate_freq}, Amp={amplitude_percent}')

    file_ext = os.path.splitext(input_file)[1].lower()
    info: Dict[str, Any] = {}

    # --- 1. Parse the input file ---
    if file_ext == '.sub': info = parse_sub(input_file)
    elif file_ext == '.wav': info = parse_wav(input_file)
    elif file_ext == '.iq': info = parse_iq(input_file)
    elif file_ext == '.bin': info = parse_bin(input_file)
    else:
        logging.error(f'Unsupported file format: {file_ext} for file {input_file}')
        sys.exit(-1)

    # --- Determine final frequency (for metadata) ---
    # Priority: User override > File metadata (SUB) > Default
    final_frequency = target_frequency # Start with user-provided target
    if final_frequency is None and info.get('frequency') is not None:
        final_frequency = info.get('frequency')
        logging.info(f"Using frequency from input file: {final_frequency} Hz")
    elif final_frequency is None:
        final_frequency = DEFAULT_FREQUENCY
        logging.warning(f"Frequency not specified or found in file, using default: {final_frequency} Hz")
    else: # User specified frequency
         logging.info(f"Using user-provided frequency: {final_frequency} Hz")


    # --- Handle Sample Rate and Potential Resampling ---
    input_sr = info.get('sampling_rate') # Original SR if known (from WAV)
    final_sampling_rate = target_sampling_rate # Target SR specified by user/auto/default

    # Check if resampling is needed and possible
    resampling_needed = False
    if SCIPY_AVAILABLE and info.get('file_type') == '.wav' and input_sr is not None and final_sampling_rate is not None and input_sr != final_sampling_rate:
        resampling_needed = True
        logging.info(f"Input sample rate ({input_sr} Hz) differs from target ({final_sampling_rate} Hz). Resampling required.")
    elif info.get('file_type') in ['.iq', '.bin']:
        if final_sampling_rate is None: # Should have been caught by arg parsing logic but double check
            logging.error("Target sample rate must be specified for .iq/.bin files.")
            sys.exit(-1)
        # Cannot resample IQ/BIN without knowing original rate
        logging.info(f"Using user-specified sample rate {final_sampling_rate} Hz for IQ/BIN file.")
        # Set the effective input rate to the target rate for sequence building
        # No resampling actually occurs, but we use the target rate downstream
        input_sr = final_sampling_rate
    elif info.get('file_type') == '.sub':
        # SR for SUB is purely for synthesis, not resampling
        logging.info(f"Using target sample rate {final_sampling_rate} Hz for .sub synthesis.")
        input_sr = final_sampling_rate # Use the target rate for generation


    if resampling_needed and input_sr is not None: # Must have input_sr to resample
        try:
            samples_i_np = np.array(info['samples_i'], dtype=np.float32)
            samples_q_np = np.array(info['samples_q'], dtype=np.float32)

            # Calculate resampling factors using GCD
            common = _greatest_common_divisor(int(final_sampling_rate), int(input_sr))
            up = int(final_sampling_rate // common)
            down = int(input_sr // common)
            logging.info(f"Resampling from {input_sr} Hz to {final_sampling_rate} Hz (up={up}, down={down})...")

            # Use resample_poly for potentially better quality
            resampled_i = signal.resample_poly(samples_i_np, up, down)
            resampled_q = signal.resample_poly(samples_q_np, up, down)
            logging.info(f"Resampling complete. Original samples: {len(samples_i_np)}, New samples: {len(resampled_i)}")

            # Update info with resampled data (convert back to lists)
            # Need to clamp and convert back to int list for downstream processing
            max_val, min_val = 32767, -32768
            info['samples_i'] = [max(min_val, min(max_val, int(round(s)))) for s in resampled_i]
            info['samples_q'] = [max(min_val, min(max_val, int(round(s)))) for s in resampled_q]
            info['sampling_rate'] = final_sampling_rate # Update the 'effective' rate of the data

        except Exception as e:
            logging.error(f"Failed to resample WAV data: {e}. Falling back to using original samples at target rate metadata (timing may be incorrect).")
            # Reset sampling rate to indicate original rate still in use internally for samples
            info['sampling_rate'] = input_sr # Revert if resampling failed
            resampling_needed = False # Mark as not resampled
    elif resampling_needed and not SCIPY_AVAILABLE:
         logging.warning("SciPy library not found. Cannot perform resampling. Using original samples - timing will be incorrect if sample rates differ.")
         resampling_needed = False # Cannot proceed


    # --- 2. Generate or Format IQ Sequence ---
    iq_sequence: List[Tuple[int, int]] = []

    if info.get('file_type') == '.sub':
        if 'raw_durations' not in info or not info['raw_durations']:
             logging.error(f"No RAW durations found to process in {input_file}.")
             sys.exit(-1)
        # Synthesize using the final target sampling rate
        iq_sequence = durations_to_iq_sequence(info['raw_durations'], final_sampling_rate, intermediate_freq, amplitude_percent)

    elif info.get('file_type') in ['.wav', '.iq', '.bin']:
        if 'samples_i' not in info or 'samples_q' not in info:
             logging.error(f"Internal error: Parsed samples not found for {info.get('file_type')} file.")
             sys.exit(-1)
        # Build sequence from (potentially resampled) I/Q data
        iq_sequence = build_iq_sequence_from_samples(info['samples_i'], info['samples_q'])
        log_msg = "Formatted" if not resampling_needed else "Formatted resampled"
        logging.info(f"{log_msg} {len(iq_sequence)} IQ samples.")
    else:
        logging.error("Could not determine processing path.")
        sys.exit(-1)

    # --- Check sequence validity ---
    if not iq_sequence:
        logging.error(f"Processing resulted in an empty IQ sequence for {input_file}. Check input data and parameters.")
        if not os.path.isdir(args.get('file', '')): sys.exit(-1)
        else: logging.warning(f"Skipping output for {input_file} due to empty sequence."); return

    # --- 3. Convert to buffer and Write Output ---
    buffer = sequence_to_16le_buffer(iq_sequence)

    if not buffer:
         logging.warning(f"Resulting buffer is empty for {input_file}. Skipping file writing.")
         return

    # Always write metadata with the TARGET sampling rate
    write_hrf_files(output_base_path, buffer, final_frequency, final_sampling_rate)


# =============================================================================
# Command Line Interface
# =============================================================================

def parse_args() -> Dict[str, Any]:
    parser = argparse.ArgumentParser(
        description="Convert signal files (.sub, .wav, .iq, .bin) to C16 IQ format.\n"
                    "Optionally resamples .wav files if SciPy is installed and target SR differs.", # Added note
        formatter_class=argparse.RawTextHelpFormatter)

    parser.add_argument('file', help="Input file path or a folder containing supported files.")
    parser.add_argument('-o', '--output', help="Output base path/directory.")
    parser.add_argument('--auto', action='store_true', help='Auto-detect parameters (SR from WAV, Freq from SUB).')

    param_group = parser.add_argument_group('Manual Parameter Control (Overrides Auto/Defaults)')
    param_group.add_argument('-sr', '--sampling_rate', type=int,
                             help=f"Target sampling rate (Hz) for the output C16 file.\n"
                                  f"Required for .iq/.bin. Overrides/triggers resampling for .wav if different.\n"
                                  f"(Default: {DEFAULT_SAMPLING_RATE} or from --auto)")
    param_group.add_argument('-f', '--frequency', type=int,
                             help=f"Target center frequency (Hz) for metadata.\n(Default: {DEFAULT_FREQUENCY} or from --auto)")
    param_group.add_argument('-if', '--intermediate_freq', type=int,
                             help=f"Intermediate frequency (Hz) for .sub synthesis.\n(Default: {DEFAULT_INTERMEDIATE_FREQ} or from --auto)")
    param_group.add_argument('-a', '--amplitude', type=int, choices=range(1, 101), metavar="[1-100]",
                             help=f"Amplitude percentage (1-100) for .sub synthesis.\n(Default: {DEFAULT_AMPLITUDE})")

    parser.add_argument('--no-resample', action='store_true', # NEW option
                        help='Disable automatic resampling even if sample rates differ and SciPy is available.')
    parser.add_argument('-v', '--verbose', action='store_true', help='Enable verbose DEBUG logging.')

    parsed_args = vars(parser.parse_args())
    if parsed_args['amplitude'] is None: parsed_args['amplitude'] = DEFAULT_AMPLITUDE
    if not SCIPY_AVAILABLE and not parsed_args['no_resample']:
        logging.warning("SciPy not found. Resampling capability is disabled.")
    elif parsed_args['no_resample']:
        logging.info("Automatic resampling explicitly disabled by user.")


    return parsed_args

# Global args dict
args: Dict[str, Any] = {}

def main():
    global args
    args = parse_args()

    if args['verbose']: logging.getLogger().setLevel(logging.DEBUG)
    logging.debug(f"Parsed arguments: {args}")
    if not SCIPY_AVAILABLE:
        logging.info("Note: SciPy library not installed. WAV file resampling is unavailable.")

    input_path = os.path.abspath(args['file'])
    output_path = args['output']

    # Determine target parameters (User override > Auto > Default)
    p_sr, p_freq, p_if, p_amp = None, None, None, args['amplitude']

    if args['auto']:
        logging.info("--- Auto-detecting parameters ---")
        detected_params = None
        if os.path.isfile(input_path):
             try: detected_params = auto_detect_parameters(input_path)
             except Exception as e: logging.error(f"Error during auto-detection for {input_path}: {e}. Proceeding with defaults.")
        elif os.path.isdir(input_path):
             logging.warning("Auto-detect in directory mode uses generic defaults. Run per-file for specific detection.")
             # Set defaults for directory mode auto
             detected_params = {'sampling_rate': DEFAULT_SAMPLING_RATE, 'frequency': DEFAULT_FREQUENCY,
                                 'intermediate_freq': min(DEFAULT_FREQUENCY // 100, DEFAULT_INTERMEDIATE_FREQ),
                                 'amplitude': DEFAULT_AMPLITUDE}
        else: logging.error(f"Input path not found: {input_path}"); sys.exit(1)

        if detected_params:
             p_sr = detected_params['sampling_rate']
             p_freq = detected_params['frequency']
             p_if = detected_params['intermediate_freq']
             # p_amp is usually default in auto_detect, but could assign if logic changes
        logging.info("--- Auto-detection finished ---")

    # Apply manual overrides
    # Use || operator precedence logic carefully, manual args take priority
    target_sr = args['sampling_rate'] if args['sampling_rate'] is not None else p_sr
    target_freq = args['frequency'] if args['frequency'] is not None else p_freq
    target_if = args['intermediate_freq'] if args['intermediate_freq'] is not None else p_if
    target_amp = args['amplitude'] # Always has a value (default or user)

    # If still None after auto and overrides, apply defaults
    target_sr = target_sr or DEFAULT_SAMPLING_RATE
    target_freq = target_freq or DEFAULT_FREQUENCY
    target_if = target_if or DEFAULT_INTERMEDIATE_FREQ

    logging.info(f"Final Target Parameters -> SR: {target_sr} Hz, Freq: {target_freq} Hz, IF: {target_if} Hz, Amp: {target_amp}%")

    # --- Process File(s) ---
    process_func = process_file # Reference the function

    # Modify process_func if resampling is disabled
    if args['no_resample']:
        # Wrap the original function to force input_sr = target_sr logic path
        # or simply skip the resampling check within process_file (Simpler)
        # Let's modify the logic inside process_file based on 'no_resample' arg directly.
        # This requires passing the args dict or the 'no_resample' flag down.
        # For simplicity, let's pass the flag.
        # process_func = lambda *f_args, **f_kwargs: process_file(*f_args, **f_kwargs, disable_resampling=True)
        # RETHINK: Modifying process_file is cleaner than lambda wrapper. Check 'no_resample' flag there.
         pass # The check is now inside process_file

    if os.path.isdir(input_path):
        # (Directory processing logic remains the same, calls process_file)
        target_output_dir = os.path.abspath(output_path) if output_path else input_path
        if not os.path.exists(target_output_dir):
            try: os.makedirs(target_output_dir); logging.info(f"Created output directory: {target_output_dir}")
            except Exception as e: logging.error(f"Failed to create output directory {target_output_dir}: {e}"); sys.exit(1)
        elif not os.path.isdir(target_output_dir): logging.error(f"Output path {target_output_dir} exists but is not a directory."); sys.exit(1)

        logging.info(f"Processing files in directory: {input_path}")
        logging.info(f"Outputting to directory: {target_output_dir}")
        files_to_process = [f for f in os.listdir(input_path) if f.lower().endswith(('.sub', '.wav', '.iq', '.bin'))]

        if not files_to_process: logging.warning(f"No supported files found in {input_path}"); sys.exit(0)

        logging.info(f"Found {len(files_to_process)} files to process.")
        processed_count, skipped_count = 0, 0
        for filename in files_to_process:
            current_input_file = os.path.join(input_path, filename)
            base_name = os.path.splitext(filename)[0]
            current_output_base = os.path.join(target_output_dir, base_name)

            logging.info(f"--- Processing file: {filename} ---")
            try:
                # Pass target parameters calculated once for the batch
                # The resampling logic inside will check args['no_resample']
                process_file(current_input_file, current_output_base,
                             target_sr, target_freq, target_if, target_amp, args['verbose'])
                processed_count += 1
            except SystemExit as e:
                if e.code != 0: logging.error(f"Failed processing {filename}. Skipping."); skipped_count += 1
            except Exception as e:
                logging.error(f"Unexpected error processing {filename}: {e}", exc_info=args['verbose']) # Show traceback if verbose
                skipped_count += 1
            logging.info(f"--- Finished file: {filename} ---")

        logging.info(f"Batch processing complete. Processed: {processed_count}, Skipped/Failed: {skipped_count}")

    elif os.path.isfile(input_path):
        # (Single file processing logic remains the same, calls process_file)
        target_output_base = output_path if output_path else os.path.splitext(input_path)[0]
        output_dir = os.path.dirname(target_output_base)
        if output_dir and not os.path.exists(output_dir):
             try: os.makedirs(output_dir); logging.info(f"Created directory for output file: {output_dir}")
             except Exception as e: logging.error(f"Failed to create directory {output_dir} for output: {e}"); sys.exit(1)

        logging.info(f"Processing single file: {input_path}")
        logging.info(f"Output base name: {target_output_base}")
        process_file(input_path, target_output_base,
                     target_sr, target_freq, target_if, target_amp, args['verbose'])
        logging.info("Processing complete.")
    else:
        logging.error(f"Input path not found or invalid: {input_path}")
        sys.exit(1)


# Modify process_file slightly to accept the no_resample flag from args
# Add it to the function signature (easier than modifying all calls)

def process_file(input_file: str, output_base_path: str,
                 target_sampling_rate: int, target_frequency: Optional[int], # Target output params
                 intermediate_freq: int, amplitude_percent: int, # Only for SUB synthesis
                 verbose: bool): # Remove the 'disable_resampling' arg here, check global 'args' directly inside

    # Existing logic from above ...

    # --- Handle Sample Rate and Potential Resampling ---
    input_sr = info.get('sampling_rate') # Original SR if known (from WAV)
    final_sampling_rate = target_sampling_rate # Target SR specified by user/auto/default

    # Check if resampling is needed, possible, and enabled
    resampling_possible = SCIPY_AVAILABLE and info.get('file_type') == '.wav' and input_sr is not None and final_sampling_rate is not None and input_sr != final_sampling_rate
    resampling_enabled = not args.get('no_resample', False) # Check global args for the flag
    resampling_needed = resampling_possible and resampling_enabled

    # Inform user if resampling *could* happen but is disabled
    if resampling_possible and not resampling_enabled:
        logging.warning(f"Input sample rate ({input_sr} Hz) differs from target ({final_sampling_rate} Hz), but resampling is disabled via --no-resample. Timing may be incorrect.")
        # Ensure metadata matches target SR, but samples are original
        final_sampling_rate = target_sampling_rate # Metadata rate
        # internal data sample rate remains input_sr, effectively
    elif info.get('file_type') in ['.iq', '.bin']:
         # Logic as before, check target_sr exists, set final_sr
        if final_sampling_rate is None:
             logging.error("Target sample rate must be specified for .iq/.bin files.")
             sys.exit(-1)
        logging.info(f"Using user-specified sample rate {final_sampling_rate} Hz for IQ/BIN file.")
        # internal data has this effective rate now
    elif info.get('file_type') == '.sub':
         logging.info(f"Using target sample rate {final_sampling_rate} Hz for .sub synthesis.")
         # internal generated data has this rate

    # Perform resampling only if needed, possible, and enabled
    resampling_actually_done = False # Track if we modify samples
    if resampling_needed: # implies resampling_possible and resampling_enabled
        logging.info(f"Input sample rate ({input_sr} Hz) differs from target ({final_sampling_rate} Hz). Resampling required.")
        try:
            # ... (rest of resampling try-except block using signal.resample_poly as before)
            samples_i_np = np.array(info['samples_i'], dtype=np.float32)
            samples_q_np = np.array(info['samples_q'], dtype=np.float32)
            common = _greatest_common_divisor(int(final_sampling_rate), int(input_sr))
            up = int(final_sampling_rate // common)
            down = int(input_sr // common)
            logging.info(f"Resampling from {input_sr} Hz to {final_sampling_rate} Hz (up={up}, down={down})...")
            resampled_i = signal.resample_poly(samples_i_np, up, down)
            resampled_q = signal.resample_poly(samples_q_np, up, down)
            logging.info(f"Resampling complete. Original samples: {len(samples_i_np)}, New samples: {len(resampled_i)}")
            max_val, min_val = 32767, -32768
            info['samples_i'] = [max(min_val, min(max_val, int(round(s)))) for s in resampled_i]
            info['samples_q'] = [max(min_val, min(max_val, int(round(s)))) for s in resampled_q]
            info['sampling_rate'] = final_sampling_rate # Update the effective rate
            resampling_actually_done = True # Mark as done

        except Exception as e:
            logging.error(f"Failed to resample WAV data: {e}. Falling back to using original samples. Metadata will use target rate ({final_sampling_rate} Hz), so timing may be incorrect.")
            # Data samples remain original, metadata uses target_rate
            info['sampling_rate'] = input_sr # Revert effective internal rate if resampling failed
            resampling_actually_done = False
    elif resampling_possible and not SCIPY_AVAILABLE:
         logging.warning("SciPy library not found. Cannot perform resampling. Using original samples. Metadata will use target rate ({final_sampling_rate} Hz), so timing may be incorrect.")
         # Keep original samples, metadata uses target_rate

    # --- 2. Generate or Format IQ Sequence ---
    # ... (Rest of the function is mostly the same)
    iq_sequence: List[Tuple[int, int]] = []
    if info.get('file_type') == '.sub':
        if 'raw_durations' not in info or not info['raw_durations']: logging.error(...); sys.exit(-1)
        iq_sequence = durations_to_iq_sequence(info['raw_durations'], final_sampling_rate, intermediate_freq, amplitude_percent)
    elif info.get('file_type') in ['.wav', '.iq', '.bin']:
        if 'samples_i' not in info or 'samples_q' not in info: logging.error(...); sys.exit(-1)
        iq_sequence = build_iq_sequence_from_samples(info['samples_i'], info['samples_q'])
        log_msg = "Formatted resampled" if resampling_actually_done else "Formatted"
        logging.info(f"{log_msg} {len(iq_sequence)} IQ samples.")
    # ... (rest of sequence check, buffer creation)

    # --- 3. Convert to buffer and Write Output ---
    # Always write metadata with the TARGET sampling rate
    buffer = sequence_to_16le_buffer(iq_sequence)
    if not buffer: logging.warning(...); return
    write_hrf_files(output_base_path, buffer, final_frequency, final_sampling_rate)


if __name__ == "__main__":
    main()
