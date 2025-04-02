# Signal File Converter for HackRF PortaPack  
### Convert `.sub`, `.wav`, `.iq`, `.bin` files into `.c16` format  
> ⚠️ *Currently under development — almost fully functional, needs real world testing!.*

---

## 🚀 Project Overview

This tool converts a variety of signal formats into `.c16` files compatible with HackRF PortaPack, along with `.txt` metadata files. Originally a fork of broken code, this version was debugged and restructured using AI assistance and is actively being improved.

Supports conversion from Flipper Zero `.sub` files (RAW) and basic SDR formats including WAV, IQ, and BIN. The output is a HackRF-compatible `.c16` IQ stream and metadata file.

> Created by: **RockGod**

---

## 🛠️ Features

- **Multi-format Input Support**  
  - `.sub` (Flipper Zero RAW SubGhz files)  
  - `.wav` (Mono, 16-bit PCM audio files)  
  - `.iq` (int16 interleaved IQ samples)  
  - `.bin` (uint8 interleaved IQ samples)

- **Output Formats**  
  - `.c16`: Little-endian interleaved `int16` IQ stream  
  - `.txt`: Metadata file with sample rate and center frequency

- **Customizable Parameters**  
  - Sampling rate, center frequency, intermediate frequency, amplitude

- **Auto-Detection**  
  - Auto extracts sample rate from `.wav` headers  
  - Auto uses defaults for `.sub` if needed

- **Batch Processing**  
  - Converts all supported files in a directory

- **Verbose Logging**  
  - Enable debugging info for troubleshooting

---

## 📦 Installation

### Requirements
- **Python 3.6+**
- **Dependencies:**  
```bash
pip install numpy
```

> Other libraries used: `os`, `argparse`, `math`, `wave`, `logging`, `sys`, `typing` — all standard.

---

## 💻 Usage

### Basic Command
```bash
python signal_converter.py [options] <input_file_or_directory>
```

### Examples

```bash
# Convert a single .sub file with auto parameters
python signal_converter.py my_signal.sub --auto
```

```bash
# Convert a .wav file and specify frequency
python signal_converter.py input.wav -o output_iq -f 915000000
```

```bash
# Convert raw .iq file (manual SR/freq required)
python signal_converter.py data.iq -sr 2000000 -f 433920000
```

```bash
# Convert all supported files in a folder
python signal_converter.py ./input/ -o ./output/ --auto
```

---

## ⚙️ Command-Line Arguments

| Argument               | Description                                                                 |
|------------------------|-----------------------------------------------------------------------------|
| `file`                 | (Required) Input file path or directory containing `.sub`, `.wav`, `.iq`, or `.bin`. |
| `-o`, `--output`       | Output path or directory. Auto-derived if omitted.                          |
| `--auto`               | Auto-detect sample rate and frequency (uses defaults if not found).         |
| `-sr`, `--sampling_rate` | Sample rate in Hz. Required for `.iq` and `.bin`. Overrides `.wav` rate.     |
| `-f`, `--frequency`    | Center frequency in Hz. Overrides `.sub` file frequency if provided.        |
| `-if`, `--intermediate_freq` | Intermediate frequency for tone generation (only for `.sub`).              |
| `-a`, `--amplitude`    | Amplitude % (1–100) for `.sub` tone generation.                             |
| `-v`, `--verbose`      | Enable debug logging.                                                       |

---

## 🔍 Conversion Logic Details

### `.sub` Files
- Converts pulse durations to IQ tones or silence.
- Positive duration → tone at `intermediate_freq`
- Negative duration → zero samples
- Requires: `sampling_rate`, `intermediate_freq`, `amplitude`

### `.wav` Files
- Mono 16-bit PCM
- Treats audio as I component; sets Q = 0
- Uses WAV header sample rate unless overridden

### `.iq` Files
- Interleaved `int16` IQ data
- Rewrites as `.c16` format (pass-through)
- Requires manual `-sr` and `-f`

### `.bin` Files
- Interleaved `uint8` IQ samples
- Converts to `int16` centered at 0
- Requires manual `-sr` and `-f`

---

## ⚠️ Notes & Limitations

- ✅ Only **mono 16-bit WAV** supported.
- ❌ No sample rate conversion (SR mismatches lead to incorrect timing).
- ⚙️ Raw file assumptions:
  - `.iq`: Interleaved `int16` (I, Q), little-endian
  - `.bin`: Interleaved `uint8` centered at 128
- 🔍 Auto parameters use fallback values:
  - Sample Rate: `1000000`
  - Frequency: `433920000 Hz`
  - Intermediate Freq: `Freq / 100`

---

## 📬 Contributing

Pull requests welcome! If you’ve fixed a bug, added a feature, or improved the logic — feel free to submit a PR or open an issue.

---

## 📜 License

> Add your preferred license here (e.g. MIT, Apache 2.0)

---

## 🧠 Credit

Inspired by the JS version: [rascafr/sub-to-c16](https://github.com/rascafr/sub-to-c16)  
Thanks to [RocketGod](https://github.com/RocketGod-git) for the original `.sub` signal files and HackRF content.

![RocketGod Banner](https://github.com/RocketGod-git/flipper-sub-to-hackrf-portapack-c16-converter/assets/57732082/acaadb30-214c-4b42-b893-33de68230083)
