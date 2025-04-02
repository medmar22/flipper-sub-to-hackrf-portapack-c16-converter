import os
import argparse
import math
from typing import List, Tuple, Dict, Any, Optional
import numpy as np
import wave
import logging
import sys # Import sys for exit

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

SUPPORTED_PROTOCOLS = ['RAW', 'BinRAW']
DEFAULT_FREQUENCY = 433920000 # Default Hz (e.g., 433.92 MHz)
DEFAULT_SAMPLING_RATE = 1000000 # Default samples/sec (e.g., 1 MSps)
DEFAULT_INTERMEDIATE_FREQ = 50000 # Default Hz for SUB synthesis
DEFAULT_AMPLITUDE = 100 # Default % for SUB synthesis

# =============================================================================
# Parsing Functions (Read data from input files)
# =============================================================================

def parse_sub(file: str) -> Dict[str, Any]:
    """Parses Flipper Zero .sub files (RAW protocol)."""
    logging.info(f"Parsing SUB file: {file}")
    info: Dict[str, Any] = {'file_type': '.sub', 'frequency': None, 'protocol': None}
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
            # Handle case where data starts on the same line
            data_part = line[len('RAW_Data:'):].strip()
            if data_part:
                data_lines.append(data_part)
        elif data_started:
            data_lines.append(line)
        elif ':' in line:
            k, v = line.split(':', 1)
            info[k.strip().lower()] = v.strip()
        else:
            # Ignore any other lines before data starts
            continue

    # Validate protocol
    if info.get('protocol') not in SUPPORTED_PROTOCOLS:
        logging.error(f'Failed to parse {file}: Supported protocols are {", ".join(SUPPORTED_PROTOCOLS)} (found: {info.get("protocol")})')
        logging.warning("Proceeding anyway, but results may be unexpected.")
        # Allow processing even if protocol is unknown, maybe user knows best
        # sys.exit(-1)

    # Try to parse frequency
    try:
        if info.get('frequency'):
             # Remove potential trailing "Hz" etc.
            freq_str = ''.join(filter(str.isdigit, info['frequency']))
            if freq_str:
                 info['frequency'] = int(freq_str)
            else:
                 info['frequency'] = None
    except ValueError:
        logging.warning(f"Could not parse frequency '{info.get('frequency')}' in {file}. Using default or user value.")
        info['frequency'] = None


    # Parse the RAW_Data lines
    durations: List[int] = []
    for line in data_lines:
        for value in line.strip().split():
            if not value: continue
            try:
                # Flipper format uses signed integers for durations (us)
                durations.append(int(value))
            except ValueError:
                logging.error(f"Invalid non-integer value '{value}' found in RAW_Data section of {file}.")
                sys.exit(-1)

    if not durations:
        logging.error(f"No RAW_Data found or parsed in {file}.")
        sys.exit(-1)

    info['raw_durations'] = durations # Store the parsed durations
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
                logging.warning(f"WAV file {file} has {nchannels} channels. Only the first channel will be used.")
                # Read frames and extract the first channel if necessary
                # For simplicity here, we'll error out, but could be adapted.
                # If adapting: data = np.frombuffer(wf.readframes(nframes), dtype=...)
                # data = data[::nchannels] # Take every Nth sample
                logging.error(f"Multi-channel WAV ({nchannels}) processing not implemented. Please use a mono WAV.")
                sys.exit(-1)

            if sampwidth != 2: # 2 bytes = 16 bits
                logging.error(f"WAV file {file} has sample width {sampwidth*8}-bit. Only 16-bit WAV files are supported.")
                sys.exit(-1)

            logging.info(f"WAV properties: Rate={framerate} Hz, Channels={nchannels}, Width={sampwidth*8}-bit")

            audio_data = wf.readframes(nframes)
            # Data is already int16 PCM bytes
            samples = np.frombuffer(audio_data, dtype=np.int16).tolist()

            info = {
                'file_type': '.wav',
                'sampling_rate': framerate, # Key information from WAV header
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
            # Assume data is interleaved int16 (I0, Q0, I1, Q1, ...)
            samples = np.frombuffer(iq_data, dtype=np.int16)

            if len(samples) % 2 != 0:
                logging.warning(f"IQ file {file} has an odd number of int16 values ({len(samples)}). The last value will be discarded.")
                samples = samples[:-1]

            if len(samples) == 0:
                logging.error(f"No valid IQ data found in file {file}.")
                sys.exit(-1)

            # De-interleave
            samples_i = samples[0::2].tolist()
            samples_q = samples[1::2].tolist()

            info = {
                'file_type': '.iq',
                'samples_i': samples_i,
                'samples_q': samples_q,
                'sampling_rate': None, # Cannot know from raw file
                'frequency': None      # Cannot know from raw file
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
            # Assume data is interleaved uint8 (I0, Q0, I1, Q1, ...)
            samples_u8 = np.frombuffer(bin_data, dtype=np.uint8)

            if len(samples_u8) % 2 != 0:
                logging.warning(f"BIN file {file} has an odd number of bytes ({len(samples_u8)}). The last byte will be discarded.")
                samples_u8 = samples_u8[:-1]

            if len(samples_u8) == 0:
                logging.error(f"No valid data found in file {file}.")
                sys.exit(-1)

            # Convert uint8 (0..255) to int16 (-32k..+32k), centered around 0
            # Assumes original signal was centered at 128 in uint8 range
            samples_int16 = ((samples_u8.astype(np.float32) - 128.0) * 256.0).astype(np.int16)

            # De-interleave
            samples_i = samples_int16[0::2].tolist()
            samples_q = samples_int16[1::2].tolist()

            info = {
                'file_type': '.bin',
                'samples_i': samples_i,
                'samples_q': samples_q,
                'sampling_rate': None, # Cannot know from raw file
                'frequency': None      # Cannot know from raw file
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
    if duration_us <= 0:
        return []

    num_samples = int(sampling_rate * duration_us / 1_000_000)
    if num_samples == 0:
        # Duration is too short for the given sampling rate
        return []

    if not level:
        # Signal is LOW (off), output zero samples
        return [(0, 0)] * num_samples

    # Signal is HIGH (on)
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
    if not durations:
        return []
    logging.info(f"Synthesizing IQ sequence: SR={sampling_rate}Hz, IF={intermediate_freq}Hz, Ampl={amplitude_percent}%")
    sequence = []
    for duration_us in durations:
        is_high_level = duration_us > 0
        abs_duration_us = abs(duration_us)
        samples = us_to_sin(is_high_level, abs_duration_us, sampling_rate, intermediate_freq, amplitude_percent)
        sequence.extend(samples)

    logging.info(f"Synthesized {len(sequence)} IQ samples.")
    # Log min/max for debugging synthesis
    if sequence:
        min_i = min(s[0] for s in sequence)
        max_i = max(s[0] for s in sequence)
        min_q = min(s[1] for s in sequence)
        max_q = max(s[1] for s in sequence)
        logging.info(f'Synthesized IQ Range -> Min I: {min_i}, Max I: {max_i}, Min Q: {min_q}, Max Q: {max_q}')

    return sequence

# =============================================================================
# Output Functions
# =============================================================================

def build_iq_sequence_from_samples(samples_i: List[int], samples_q: List[int]) -> List[Tuple[int, int]]:
    """Combines I and Q sample lists into an IQ sequence."""
    if len(samples_i) != len(samples_q):
         logging.error(f"Internal error: I ({len(samples_i)}) and Q ({len(samples_q)}) sample lists have different lengths.")
         sys.exit(-1)
    # Ensure values are within int16 range, clamp if necessary (safety measure)
    # This shouldn't happen with correct parsing/synthesis, but good defense.
    max_val = 32767
    min_val = -32768
    return [
        (max(min_val, min(max_val, i)), max(min_val, min(max_val, q)))
        for i, q in zip(samples_i, samples_q)
    ]

def sequence_to_16le_buffer(sequence: List[Tuple[int, int]]) -> bytes:
    """Converts a list of (I, Q) int tuples into a little-endian int16 byte buffer."""
    if not sequence:
        return b''
    # Use numpy for efficient conversion and explicit little-endian ('<i2')
    iq_array = np.array(sequence, dtype=np.int16)
    # Ensure it's little endian for standard C16/HackRF format
    buffer = iq_array.astype('<i2').tobytes()
    return buffer

def generate_meta_string(frequency: Optional[int], sampling_rate: int) -> str:
    """Generates the metadata string for the .txt file."""
    freq_str = str(frequency) if frequency is not None else 'UNKNOWN'
    sr_str = str(sampling_rate)
    meta = [
        ['sample_rate', sr_str],
        ['center_frequency', freq_str]
        # Add other relevant metadata here if needed
        # ['gain', '...'], ['device', '...']
    ]
    return '\n'.join(' = '.join(map(str, r)) for r in meta) # Use ' = ' separator common in meta files

def write_hrf_files(output_base_path: str, buffer: bytes, frequency: Optional[int], sampling_rate: int) -> List[str]:
    """Writes the C16 IQ data and the TXT metadata file."""
    c16_path = f'{output_base_path}.c16'
    txt_path = f'{output_base_path}.txt'
    paths = [c16_path, txt_path]

    try:
        logging.info(f"Writing IQ data to: {c16_path} ({len(buffer)/1024:.2f} kiB)")
        with open(c16_path, 'wb') as f:
            f.write(buffer)

        logging.info(f"Writing metadata to: {txt_path}")
        meta_content = generate_meta_string(frequency, sampling_rate)
        with open(txt_path, 'w') as f:
            f.write(meta_content)

    except Exception as e:
        logging.error(f'Cannot write output file(s) starting with "{output_base_path}": {e}')
        sys.exit(-1)

    duration_seconds = (len(buffer) / 4) / sampling_rate if sampling_rate > 0 else 0 # Each IQ pair is 4 bytes
    logging.info(f'Written {len(buffer) / 1024:.2f} kiB, representing {duration_seconds:.3f} seconds of IQ data.')
    return paths

# =============================================================================
# Main Processing Logic
# =============================================================================

def auto_detect_parameters(file: str) -> Dict[str, Any]:
    """Attempts to detect parameters (primarily sampling rate) based on file type."""
    file_ext = os.path.splitext(file)[1].lower()
    params = {'sampling_rate': None, 'frequency': None, 'intermediate_freq': None, 'amplitude': None }

    logging.info(f"Auto-detecting parameters for file: {file}")

    # Attempt to parse partially to get header info if possible
    partial_info: Optional[Dict[str, Any]] = None
    try:
        if file_ext == '.sub':
            # Parse fully to get frequency if available
             partial_info = parse_sub(file) # Need freq from here
             params['frequency'] = partial_info.get('frequency')
        elif file_ext == '.wav':
             # Only need header info
             with wave.open(file, 'r') as wf:
                 params['sampling_rate'] = wf.getframerate()
    except Exception as e:
        logging.warning(f"Could not auto-detect parameters from {file}: {e}")
        # Continue with defaults

    # Apply defaults where needed
    params['sampling_rate'] = params['sampling_rate'] or DEFAULT_SAMPLING_RATE
    params['frequency'] = params['frequency'] or DEFAULT_FREQUENCY # Use overall default if not in sub
    params['intermediate_freq'] = min(params['frequency'] // 100 if params['frequency'] else DEFAULT_INTERMEDIATE_FREQ, DEFAULT_INTERMEDIATE_FREQ)
    params['amplitude'] = DEFAULT_AMPLITUDE

    logging.info(f"Auto-detected parameters -> Sampling Rate: {params['sampling_rate']}, Frequency: {params['frequency']}, "
                 f"IF (for .sub): {params['intermediate_freq']}, Amplitude (for .sub): {params['amplitude']}")
    return params

def process_file(input_file: str, output_base_path: str,
                 sampling_rate: int, frequency: Optional[int], # Always needed for output
                 intermediate_freq: int, amplitude_percent: int, # Only needed for SUB synthesis
                 verbose: bool):
    """Parses an input file and converts it to C16/TXT format."""

    if verbose:
        logging.getLogger().setLevel(logging.DEBUG) # Enable debug logging if verbose
        logging.debug(f'Processing: {input_file} -> {output_base_path}.[c16,txt]')
        logging.debug(f'Parameters: SR={sampling_rate}, Freq={frequency}, IF={intermediate_freq}, Amp={amplitude_percent}')

    file_ext = os.path.splitext(input_file)[1].lower()
    info: Dict[str, Any] = {}
    final_sampling_rate = sampling_rate # Use provided SR by default
    final_frequency = frequency # Use provided Freq by default

    # --- 1. Parse the input file ---
    if file_ext == '.sub':
        info = parse_sub(input_file)
        # Use frequency from SUB file if available and not overridden by user
        if info.get('frequency') is not None and frequency is None:
             final_frequency = info['frequency']
             logging.info(f"Using frequency from .sub file: {final_frequency} Hz")
        elif frequency is not None:
             final_frequency = frequency # User override
             logging.info(f"Using user-provided frequency: {final_frequency} Hz")
        else:
             final_frequency = DEFAULT_FREQUENCY # Fallback
             logging.warning(f"Frequency not found in .sub and not provided, using default: {final_frequency} Hz")

    elif file_ext == '.wav':
        info = parse_wav(input_file)
        # Use sampling rate from WAV file if available and not overridden by user
        if info.get('sampling_rate') is not None:
             if sampling_rate is None: # User did not specify SR, use WAV's
                 final_sampling_rate = info['sampling_rate']
                 logging.info(f"Using sampling rate from .wav file: {final_sampling_rate} Hz")
             elif sampling_rate != info['sampling_rate']:
                 final_sampling_rate = sampling_rate # User override
                 logging.warning(f"User SR ({sampling_rate}Hz) overrides WAV SR ({info['sampling_rate']}Hz). No resampling is performed.")
             else:
                 final_sampling_rate = sampling_rate # They match
                 logging.info(f"Using specified sampling rate: {final_sampling_rate} Hz (matches WAV)")

        if frequency is not None: # User specified frequency
             final_frequency = frequency
        else: # Use default if not specified
             final_frequency = DEFAULT_FREQUENCY
             logging.warning(f"Frequency not specified for WAV conversion, using default: {final_frequency} Hz")

    elif file_ext == '.iq':
        info = parse_iq(input_file)
        # Requires user SR
        if sampling_rate is None:
             logging.error(f"Sampling rate must be provided ('-sr' or '--auto') for .iq files.")
             sys.exit(-1)
        final_sampling_rate = sampling_rate
        if frequency is not None: final_frequency = frequency
        else: final_frequency = DEFAULT_FREQUENCY; logging.warning(f"Freq not specified, using default: {final_frequency}Hz")


    elif file_ext == '.bin':
        info = parse_bin(input_file)
         # Requires user SR
        if sampling_rate is None:
             logging.error(f"Sampling rate must be provided ('-sr' or '--auto') for .bin files.")
             sys.exit(-1)
        final_sampling_rate = sampling_rate
        if frequency is not None: final_frequency = frequency
        else: final_frequency = DEFAULT_FREQUENCY; logging.warning(f"Freq not specified, using default: {final_frequency}Hz")


    else:
        logging.error(f'Unsupported file format: {file_ext} for file {input_file}')
        sys.exit(-1) # Use sys.exit here

    if verbose:
        # Avoid logging huge sample lists
        log_info = {k: v for k, v in info.items() if not k.startswith('samples_') and not k.startswith('raw_')}
        logging.debug(f'Parsed info: {log_info}')

    # --- 2. Generate or Format IQ Sequence ---
    iq_sequence: List[Tuple[int, int]] = []

    if info.get('file_type') == '.sub':
        if 'raw_durations' not in info or not info['raw_durations']:
             logging.error(f"No RAW durations found to process in {input_file}.")
             sys.exit(-1) # Exit if SUB parsing failed to get durations
        # Use synthesis parameters only for SUB
        iq_sequence = durations_to_iq_sequence(info['raw_durations'], final_sampling_rate, intermediate_freq, amplitude_percent)
    elif info.get('file_type') in ['.wav', '.iq', '.bin']:
        if 'samples_i' not in info or 'samples_q' not in info:
             logging.error(f"Internal error: Parsed samples not found for {info.get('file_type')} file.")
             sys.exit(-1)
        # Just format the existing samples
        iq_sequence = build_iq_sequence_from_samples(info['samples_i'], info['samples_q'])
        logging.info(f"Formatted {len(iq_sequence)} existing IQ samples.")
    else:
        logging.error("Could not determine processing path.") # Should not happen
        sys.exit(-1)

    # Check if sequence generation failed or resulted in empty sequence
    if not iq_sequence:
        logging.error(f"Processing resulted in an empty IQ sequence for {input_file}. Check input data and parameters (e.g., durations vs sampling rate for .sub).")
        # Don't write empty files, maybe just warn and continue if in batch mode?
        # For now, let's exit for a single file. In batch mode, this could skip the file.
        # Consider adding a check in main loop if processing multiple files.
        # Note: If running on a directory, the script will currently exit entirely here.
        # A more robust batch mode would log the error and continue with the next file.
        if not os.path.isdir(args.get('file', '')): # Check if input was a single file
             sys.exit(-1)
        else:
             logging.warning(f"Skipping output for {input_file} due to empty sequence.")
             return # Skip writing for this file in batch mode


    # --- 3. Convert to buffer and Write Output ---
    buffer = sequence_to_16le_buffer(iq_sequence)

    if not buffer:
         logging.warning(f"Resulting buffer is empty for {input_file}. Skipping file writing.")
         return # Skip if buffer is empty

    write_hrf_files(output_base_path, buffer, final_frequency, final_sampling_rate)

# =============================================================================
# Command Line Interface
# =============================================================================

def parse_args() -> Dict[str, Any]:
    parser = argparse.ArgumentParser(
        description="Convert various signal file formats (.sub, .wav, .iq, .bin) to HackRF C16 IQ format.",
        formatter_class=argparse.RawTextHelpFormatter) # Keep newline formatting

    parser.add_argument('file',
                        help="Input file path (.sub, .wav, .iq, .bin) or a folder containing such files.")
    parser.add_argument('-o', '--output',
                        help="Output base path. \n"
                             " - If input is a file 'input.sub', output is 'output.c16' / 'output.txt'. \n"
                             " - If input is a folder 'in_dir', output files go into 'output' folder (or 'in_dir' if -o omitted).\n"
                             "If omitted, input filename (without ext) / input folder name is used.")
    parser.add_argument('--auto', action='store_true',
                        help='Attempt to automatically detect parameters (like SR from WAV, Freq from SUB).\n'
                             f'Uses defaults if detection fails (SR={DEFAULT_SAMPLING_RATE}, Freq={DEFAULT_FREQUENCY}).')

    param_group = parser.add_argument_group('Manual Parameter Control (Overrides Auto/Defaults)')
    param_group.add_argument('-sr', '--sampling_rate', type=int,
                             help="Sampling rate (samples/sec) for the output C16 file.\n"
                                  f"Required for .iq/.bin unless --auto. Overrides .wav header SR if set.\n"
                                  f"Used for synthesis for .sub files. (Default: {DEFAULT_SAMPLING_RATE} or from --auto)")
    param_group.add_argument('-f', '--frequency', type=int,
                             help="Center frequency (Hz) for the output metadata (.txt file).\n"
                                  f"Overrides frequency from .sub file if set. (Default: {DEFAULT_FREQUENCY} or from --auto)")
    param_group.add_argument('-if', '--intermediate_freq', type=int,
                             help="Intermediate frequency (Hz) for IQ synthesis **(ONLY for .sub files)**.\n"
                                  f"(Default: {DEFAULT_INTERMEDIATE_FREQ} or derived from Freq/SR by --auto)")
    param_group.add_argument('-a', '--amplitude', type=int, choices=range(1, 101), metavar="[1-100]",
                             help="Amplitude percentage (1-100) for IQ synthesis **(ONLY for .sub files)**.\n"
                                  f"(Default: {DEFAULT_AMPLITUDE})")

    parser.add_argument('-v', '--verbose', action='store_true',
                        help='Enable verbose DEBUG logging.')

    parsed_args = vars(parser.parse_args())

    # Set default amplitude if not provided and not auto (or if auto is not implemented for it)
    # Note: 'auto' currently sets amplitude to default anyway.
    if parsed_args['amplitude'] is None:
        parsed_args['amplitude'] = DEFAULT_AMPLITUDE

    return parsed_args

# Store args globally or pass it around; let's store for simplicity in this structure
args: Dict[str, Any] = {}

def main():
    global args # Allow modification of global args dict
    args = parse_args()

    if args['verbose']:
        logging.getLogger().setLevel(logging.DEBUG)
        logging.debug("Verbose logging enabled.")
        logging.debug(f"Parsed arguments: {args}")

    input_path = os.path.abspath(args['file'])
    output_path = args['output'] # Can be None

    # Determine parameters: Start with None, then apply auto, then manual overrides
    p_sr, p_freq, p_if, p_amp = None, None, None, args['amplitude'] # Amplitude has default/choice

    if args['auto']:
        logging.info("--- Auto-detecting parameters ---")
        # Auto-detect might need to read the file, handle potential errors
        if os.path.isfile(input_path):
             try:
                 detected_params = auto_detect_parameters(input_path)
                 p_sr = detected_params['sampling_rate']
                 p_freq = detected_params['frequency']
                 p_if = detected_params['intermediate_freq']
                 # p_amp is already set or taken from detected_params if needed later
             except Exception as e:
                 logging.error(f"Error during auto-detection for {input_path}: {e}. Cannot proceed without parameters.")
                 sys.exit(1)
        elif os.path.isdir(input_path):
             # For directory mode with auto, we might use generic defaults,
             # or try to detect for the *first* file? Let's use generics.
             logging.warning("Auto-detect in directory mode uses generic defaults. Parameters might not be optimal for all files.")
             p_sr = DEFAULT_SAMPLING_RATE
             p_freq = DEFAULT_FREQUENCY
             p_if = min(p_freq // 100, DEFAULT_INTERMEDIATE_FREQ)
        else:
             logging.error(f"Input path not found: {input_path}")
             sys.exit(1)
        logging.info("--- Auto-detection finished ---")


    # Apply manual overrides
    if args['sampling_rate'] is not None:
        p_sr = args['sampling_rate']
        logging.info(f"User override: Sampling Rate = {p_sr} Hz")
    if args['frequency'] is not None:
        p_freq = args['frequency']
        logging.info(f"User override: Frequency = {p_freq} Hz")
    if args['intermediate_freq'] is not None:
        p_if = args['intermediate_freq']
        logging.info(f"User override: Intermediate Frequency = {p_if} Hz (for .sub)")
    # Amplitude is directly taken from args or default

    # Final check for required parameters based on *potential* file types
    # SR is needed for IQ/BIN unless already auto-detected/overridden.
    # We handle the strict requirement inside process_file based on actual type.
    # Ensure IF has a value if it's needed (i.e., processing SUB)
    p_if = p_if or DEFAULT_INTERMEDIATE_FREQ


    # --- Process Single File or Directory ---
    if os.path.isdir(input_path):
        target_output_dir = os.path.abspath(output_path) if output_path else input_path
        if not os.path.exists(target_output_dir):
            try:
                 os.makedirs(target_output_dir)
                 logging.info(f"Created output directory: {target_output_dir}")
            except Exception as e:
                 logging.error(f"Failed to create output directory {target_output_dir}: {e}")
                 sys.exit(1)
        elif not os.path.isdir(target_output_dir):
             logging.error(f"Output path {target_output_dir} exists but is not a directory.")
             sys.exit(1)

        logging.info(f"Processing files in directory: {input_path}")
        logging.info(f"Outputting to directory: {target_output_dir}")
        files_to_process = [f for f in os.listdir(input_path) if f.lower().endswith(('.sub', '.wav', '.iq', '.bin'))]

        if not files_to_process:
             logging.warning(f"No supported files (.sub, .wav, .iq, .bin) found in {input_path}")
             sys.exit(0)

        logging.info(f"Found {len(files_to_process)} files to process.")
        processed_count = 0
        skipped_count = 0
        for filename in files_to_process:
            current_input_file = os.path.join(input_path, filename)
            base_name = os.path.splitext(filename)[0]
            current_output_base = os.path.join(target_output_dir, base_name)

            logging.info(f"--- Processing file: {filename} ---")
            try:
                # Note: Re-running auto-detect per file *could* be better for directory mode
                # if parameters vary significantly, but adds overhead. Current approach uses
                # params derived initially (either from first file, defaults, or overrides).
                # For now, stick with the parameters determined above for the whole batch.
                # Pass a copy of potentially modifiable params if needed later: p_sr, p_freq etc.
                 process_file(current_input_file, current_output_base,
                              p_sr, p_freq, p_if, p_amp, args['verbose'])
                 processed_count += 1
            except SystemExit as e: # Catch exits from process_file
                if e.code != 0: # Only log if it was an error exit
                    logging.error(f"Failed processing {filename}. Skipping.")
                    skipped_count += 1
                # If code is 0, it might be a non-error exit (less likely here)
            except Exception as e:
                logging.error(f"Unexpected error processing {filename}: {e}")
                skipped_count += 1
            logging.info(f"--- Finished file: {filename} ---")

        logging.info(f"Batch processing complete. Processed: {processed_count}, Skipped/Failed: {skipped_count}")

    elif os.path.isfile(input_path):
        target_output_base = output_path if output_path else os.path.splitext(input_path)[0]
        # Ensure the directory for the output file exists
        output_dir = os.path.dirname(target_output_base)
        if output_dir and not os.path.exists(output_dir):
             try:
                  os.makedirs(output_dir)
                  logging.info(f"Created directory for output file: {output_dir}")
             except Exception as e:
                  logging.error(f"Failed to create directory {output_dir} for output: {e}")
                  sys.exit(1)

        logging.info(f"Processing single file: {input_path}")
        logging.info(f"Output base name: {target_output_base}")
        process_file(input_path, target_output_base,
                     p_sr, p_freq, p_if, p_amp, args['verbose'])
        logging.info("Processing complete.")
    else:
        logging.error(f"Input path not found or invalid: {input_path}")
        sys.exit(1)

if __name__ == "__main__":
    main()
