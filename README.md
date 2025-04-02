# .sub, .wav, .iq, .bin to .c16 Converter for HackRF PortaPack (not currently working)

Made by RockGod, trying to be fixed by "me" (AI). This project contains a Python script that helps convert .sub (and possibily .wav, .iq, .bin)  files (Flipper SubGhz RAW File) to .c16 files for use with HackRF PortaPack. This project is a fork from broken code and has been fixed and improved. I fixed this using chatgpt, I know nothing. Supports two protocols: RAW and BinRAW.

# Signal File Converter (SUB/WAV/IQ/BIN to C16)

This Python script converts various signal file formats into the interleaved 16-bit integer IQ format (.c16) commonly used by Software Defined Radios (SDRs) like HackRF, along with a corresponding metadata text file (.txt).

## Overview

The primary goal is to take signal data, which might be represented as timing durations (like in Flipper Zero .sub files) or raw samples (like in WAV, IQ, or BIN files), and transform it into a standard complex baseband IQ representation suitable for transmission or analysis tools that expect the C16 format.

## Features

*   **Multiple Input Formats:** Supports conversion from:
    *   `.sub` (Flipper Zero RAW SubGhz files)
    *   `.wav` (Mono, 16-bit PCM audio files)
    *   `.iq` (Raw interleaved int16 IQ sample files)
    *   `.bin` (Raw interleaved uint8 IQ sample files)
*   **Standard Output:** Generates:
    *   `.c16` files: Interleaved 16-bit signed integer, Little-Endian complex IQ data (I0, Q0, I1, Q1, ...).
    *   `.txt` files: Metadata containing sample rate and center frequency.
*   **Flexible Parameters:** Allows manual specification of Sampling Rate, Center Frequency, Intermediate Frequency (for `.sub`), and Amplitude (for `.sub`).
*   **Auto-Detection:** Can attempt to auto-detect parameters like sampling rate (from WAV headers) or frequency (from `.sub` metadata), falling back to sensible defaults.
*   **Batch Processing:** Can process all supported files within a specified directory.
*   **Verbose Output:** Optional verbose logging for debugging.

## Supported Formats

*   **Input:**
    *   `.sub`: Flipper Zero RAW protocol files containing positive/negative pulse durations in microseconds. *Assumes `RAW_Data:` format.*
    *   `.wav`: Standard RIFF WAVE files. *Requires mono, 16-bit Signed Integer PCM format.*
    *   `.iq`: Raw binary files containing interleaved 16-bit signed integers (I, Q, I, Q...). *Assumes Little-Endian.*
    *   `.bin`: Raw binary files containing interleaved 8-bit unsigned integers (I, Q, I, Q...). *Assumes data centered around 128.*
*   **Output:**
    *   `.c16`: Raw binary file of interleaved `int16` (Little-Endian) IQ samples.
    *   `.txt`: Plain text metadata file (key = value format).

## Installation

1.  **Python:** Requires Python 3.6 or later.
2.  **Dependencies:** Needs the `numpy` library.
    ```bash
    pip install numpy
    ```
    (Other libraries used like `os`, `argparse`, `math`, `wave`, `logging`, `sys`, `typing` are typically included with Python).

## Usage

```bash
python signal_converter.py [options] <input_file_or_directory>
```

# Examples:

Convert a single .sub file with auto parameters:

python signal_converter.py my_signal.sub --auto
# Output: my_signal.c16, my_signal.txt
IGNORE_WHEN_COPYING_START
content_copy
download
Use code with caution.
Bash
IGNORE_WHEN_COPYING_END

Convert a .wav file, specifying output name and frequency:

python signal_converter.py input.wav -o output_iq -f 915000000
# Output: output_iq.c16, output_iq.txt (SR detected from WAV)
IGNORE_WHEN_COPYING_START
content_copy
download
Use code with caution.
Bash
IGNORE_WHEN_COPYING_END

Convert a raw .iq file (requires manual SR and Freq):

python signal_converter.py data.iq -sr 2000000 -f 433920000
# Output: data.c16, data.txt
IGNORE_WHEN_COPYING_START
content_copy
download
Use code with caution.
Bash
IGNORE_WHEN_COPYING_END

Convert all supported files in a directory, outputting to another directory:

python signal_converter.py ./input_signals/ -o ./output_c16_files/ --auto
# Processes *.sub, *.wav, *.iq, *.bin in ./input_signals/
# Outputs corresponding *.c16/*.txt files into ./output_c16_files/
IGNORE_WHEN_COPYING_START
content_copy
download
Use code with caution.
Bash
IGNORE_WHEN_COPYING_END

## Command-Line Arguments:

Argument	Description	Notes
file	(Required) Path to the input file (.sub, .wav, .iq, .bin) or a directory containing such files.	
-o, --output	Output base path/directory. If omitted, derived from input file/directory name.	For directory input, creates output dir if it doesn't exist.
--auto	Attempt to auto-detect parameters (SR from WAV, Freq from SUB). Uses defaults if detection fails.	Convenient but may not be optimal for all signals.
-sr, --sampling_rate	Sampling Rate (Hz) for the output .c16 file.	Required for .iq/.bin unless --auto. Overrides WAV SR.
-f, --frequency	Center Frequency (Hz) for the output .txt metadata.	Overrides frequency from .sub file if set.
-if, --intermediate_freq	Intermediate Frequency (Hz) used for synthesizing IQ data (ONLY for .sub files). Determines the tone frequency when the signal is 'ON'.	Ignored for .wav, .iq, .bin.
-a, --amplitude	Amplitude percentage (1-100) used for synthesizing IQ data (ONLY for .sub files). Controls the maximum amplitude of the synthesized tone.	Ignored for .wav, .iq, .bin.
-v, --verbose	Enable verbose DEBUG logging output.	Useful for troubleshooting.
## Conversion Logic Details

The script applies different logic based on the input file type:

.sub Files:

Reads the positive/negative microsecond durations from RAW_Data.

Synthesizes an IQ signal representing On-Off Keying (OOK) or Amplitude-Shift Keying (ASK).

A positive duration creates a sinusoidal tone (I/Q samples) at the specified intermediate_freq and amplitude for the calculated number of samples at the target sampling_rate.

A negative duration creates zero-value (I=0, Q=0) samples for the calculated number of samples.

Requires sampling_rate, intermediate_freq, and amplitude parameters (can be auto/default ). Uses frequency for metadata.

.wav Files:

Reads the 16-bit mono PCM samples.

Treats the audio samples directly as the I (In-phase) component.

Sets the Q (Quadrature) component to zero for all samples.

Uses the Sampling Rate specified in the WAV header unless overridden by -sr.

Requires frequency for metadata (user-specified or default). intermediate_freq and amplitude are ignored.

.iq Files:

Reads the raw interleaved int16 binary data.

De-interleaves the data into separate I and Q streams.

Re-interleaves the I and Q streams into the output .c16 format (effectively a pass-through of the sample data).

Requires sampling_rate and frequency to be specified (via args or --auto) for the output metadata. intermediate_freq and amplitude are ignored.

.bin Files:

Reads the raw interleaved uint8 binary data.

Converts each uint8 sample (range 0-255) to int16 (range approx -32k to +32k) using the formula: int16_sample = (uint8_sample - 128.0) * 256.0. This assumes the original signal was centered around 128.

De-interleaves the resulting int16 data into separate I and Q streams.

Re-interleaves the I and Q streams into the output .c16 format.

Requires sampling_rate and frequency to be specified (via args or --auto) for the output metadata. intermediate_freq and amplitude are ignored.

## Important Notes & Limitations

WAV Format: Only supports Mono, 16-bit Signed Integer PCM .wav files. Other WAV formats (stereo, float, different bit depths) will cause errors.

IQ/BIN Assumptions: Assumes raw IQ/BIN files contain interleaved samples (I, Q, I, Q...). .iq assumes int16 Little-Endian. .bin assumes uint8 centered around 128. If your raw file format differs, the script will misinterpret the data.

No Resampling: The script does not perform any sample rate conversion. If you provide a -sr different from a .wav file's native rate, the output .c16 file will simply contain the original samples, but the metadata .txt will claim the rate specified by -sr, leading to incorrect playback speed/timing if used directly.

Auto Parameter Limitations: The --auto feature uses defaults (like 1 MSps for SR, 433.92 MHz for Freq) if it cannot detect specific values. The intermediate_freq derived by --auto is a simple heuristic (like Freq / 100) and might not be optimal. Always verify parameters for critical applications.

Contributing / Issues

Feel free to open an issue on the repository for bug reports or feature requests. Pull requests are also welcome.

License

(Optional: Add license information here, e.g., MIT License)

IGNORE_WHEN_COPYING_START
content_copy
download
Use code with caution.
IGNORE_WHEN_COPYING_END




# ORIGINAL README - WAS LABELED AS "BROKEN"


Welcome to the flipper-sub-to-hackrf-portapack-c16-converter repository. This project aims to convert .sub files to HackRF Portapack .c16 files using a Python script.

The primary script used here is heavily inspired by the JS files found at this [repository](https://github.com/rascafr/sub-to-c16). 
Thanks François for the initial work!

The main goal of this project is to convert all .sub files from [https://github.com/RocketGod-git/Flipper_Zero](https://github.com/RocketGod-git/Flipper_Zero) 
and load them into the HackRF repository [https://github.com/RocketGod-git/HackRF-Treasure-Chest](https://github.com/RocketGod-git/HackRF-Treasure-Chest).

If you have the time and skills to help improve this project, please don't hesitate to contribute. 
Feel free to PR fixes or additions.

RocketGod

![RocketGod](https://github.com/RocketGod-git/flipper-sub-to-hackrf-portapack-c16-converter/assets/57732082/acaadb30-214c-4b42-b893-33de68230083)

