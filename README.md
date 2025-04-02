# Signal File Converter for HackRF PortaPack
### Convert `.sub`, `.wav`, `.iq`, `.bin` files into `.c16` format
> ⚠️ *Actively developed — generally functional, but real-world testing & feedback are valuable!*

---

## 🚀 Project Overview

This tool converts a variety of signal file formats into `.c16` files compatible with HackRF PortaPack, along with corresponding `.txt` metadata files. Initially developed by debugging and significantly enhancing earlier code with AI assistance, this script aims to provide a reliable conversion path for different signal representations.

Supports conversion from Flipper Zero `.sub` files (RAW protocol) and common SDR formats like WAV, IQ (int16), and BIN (uint8). The output is a standard HackRF-compatible `.c16` IQ data file and a metadata `.txt` file. **Includes optional sample rate conversion for WAV files.**

> Maintainer: **RockGod** (Enhancements based on earlier work and community needs)

---

## 🛠️ Features

- **Multi-format Input Support**
  - `.sub` (Flipper Zero RAW SubGhz files)
  - `.wav` (Mono, 16-bit PCM audio files)
  - `.iq` (int16 interleaved IQ samples)
  - `.bin` (uint8 interleaved IQ samples)

- **Output Formats**
  - `.c16`: Little-endian interleaved `int16` IQ stream
  - `.txt`: Metadata file with target sample rate and center frequency

- **Sample Rate Conversion (Optional)**
  - **NEW:** Automatically resamples `.wav` files if the target `-sr` differs from the source rate.
  - Requires the `scipy` library to be installed.
  - Can be disabled using the `--no-resample` flag.

- **Customizable Parameters**
  - Target Sampling rate, center frequency, intermediate frequency (for `.sub`), amplitude (for `.sub`).

- **Auto-Detection**
  - Extracts sample rate from `.wav` headers.
  - Extracts frequency from `.sub` metadata (if present).
  - Uses sensible defaults if detection fails or isn't applicable.

- **Batch Processing**
  - Converts all supported files in a directory.

- **Verbose Logging**
  - Enable detailed debug information using `-v` for troubleshooting.

---

## 📦 Installation

### Requirements
- **Python 3.6+**
- **NumPy:**
  ```bash
  pip install numpy
  ```
- **SciPy (Optional - for WAV resampling):**
  ```bash
  pip install scipy
  ```
  > Resampling will be automatically disabled if SciPy is not found.

> Other libraries used: `os`, `argparse`, `math`, `wave`, `logging`, `sys`, `typing` — all usually included with Python.

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

# Convert a .wav file recorded at 48kHz to 1MHz C16, specifying frequency
# (Requires SciPy for resampling to occur)
python signal_converter.py input_48k.wav -o output_1M -sr 1000000 -f 915000000

# Convert a .wav file but prevent automatic resampling even if rates differ
python signal_converter.py input_48k.wav -sr 96000 --no-resample

# Convert raw .iq file (manual SR/freq required)
python signal_converter.py data.iq -sr 2000000 -f 433920000

# Convert all supported files in a folder, outputting to ./output/
python signal_converter.py ./input_signals/ -o ./output/ --auto
```

---

## ⚙️ Command-Line Arguments

| Argument                 | Description                                                                                     | Notes                                                             |
| :----------------------- | :---------------------------------------------------------------------------------------------- | :---------------------------------------------------------------- |
| `file`                   | **(Required)** Input file path or directory (`.sub`, `.wav`, `.iq`, `.bin`).                       |                                                                   |
| `-o`, `--output`         | Output base path/directory. Auto-derived if omitted.                                            |                                                                   |
| `--auto`                 | Auto-detect SR (WAV) & Freq (SUB). Uses defaults if not found.                                    |                                                                   |
| `-sr`, `--sampling_rate` | Target sample rate (Hz). Required for `.iq`/`.bin`. **Triggers resampling for `.wav` if different.** | See `--no-resample`.                                              |
| `-f`, `--frequency`      | Target center frequency (Hz) for metadata. Overrides `.sub` file freq if set.                    |                                                                   |
| `-if`, `--intermediate_freq`| Intermediate frequency (Hz) for `.sub` synthesis tone generation.                             | Only used for `.sub` files.                                       |
| `-a`, `--amplitude`      | Amplitude % (1-100) for `.sub` synthesis tone generation.                                       | Only used for `.sub` files.                                       |
| `--no-resample`          | **NEW:** Disable automatic resampling for `.wav` files, even if SciPy is available and rates differ. | Useful if you want mismatched SR metadata without changing samples. |
| `-v`, `--verbose`        | Enable detailed debug logging output.                                                           |                                                                   |

---

## 🔍 Conversion Logic Details

### `.sub` Files
- Synthesizes IQ samples based on pulse durations.
- Positive duration → sine wave tone at `intermediate_freq`.
- Negative duration → zero samples (silence).
- Uses the target `-sr`, `-if`, and `-a` parameters for generation.

### `.wav` Files (Mono, 16-bit PCM)
- Treats audio samples as the **I** component. Sets **Q** component to **0**.
- **Resampling:** If the target `-sr` differs from the WAV header rate, and SciPy is installed, and `--no-resample` is **not** used, the samples are automatically resampled to the target rate.
- If resampling doesn't occur, the original samples are used, but the metadata reflects the target `-sr` (potentially leading to timing mismatches if rates differ).

### `.iq` Files (Interleaved `int16`)
- Reads raw samples, assuming (I, Q, I, Q...) order.
- Performs a pass-through, writing the same sample data to the `.c16` file.
- **Requires** user to specify the correct `-sr` and `-f` for the data. No resampling occurs.

### `.bin` Files (Interleaved `uint8`)
- Reads raw `uint8` samples (I, Q...).
- Converts `uint8` (0-255) to `int16` (approx -32k to +32k), assuming centering around 128.
- Writes the converted `int16` data to the `.c16` file.
- **Requires** user to specify the correct `-sr` and `-f` for the data. No resampling occurs.

---

## ⚠️ Notes & Limitations

- ✅ Only **Mono, 16-bit Signed Integer PCM** `.wav` files supported for conversion.
- ✅ Resampling capability for `.wav` requires the **`scipy`** library to be installed.
- ⚙️ Raw file assumptions: `.iq` (interleaved `int16`, Little-Endian), `.bin` (interleaved `uint8` centered at 128). Incorrect formats will yield garbage data.
- 🔍 `--auto` parameters use fallback default values if detection fails (e.g., SR: 1 MHz, Freq: 433.92 MHz). Always verify parameters for critical signals.

---

## 📬 Contributing

Pull requests are welcome! If you encounter bugs, have feature ideas, improve the documentation, or optimize the code, feel free to open an issue or submit a PR.

---

## 📜 License

[CHECK ORIGINAL CODE FOR LICENSE](https://github.com/RocketGod-git/flipper-sub-to-hackrf-portapack-c16-converter/assets/57732082/acaadb30-214c-4b42-b893-33de68230083)

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

---

## 🧠 Credit & Inspiration

Inspired by the JS version: [rascafr/sub-to-c16](https://github.com/rascafr/sub-to-c16)  
Greatly thankful to [RocketGod](https://github.com/RocketGod-git) for the initial Python script foundation and their valuable contributions to the HackRF community.

*(Consider keeping or removing the banner based on preference)*
![RocketGod Banner](https://github.com/RocketGod-git/flipper-sub-to-hackrf-portapack-c16-converter/assets/57732082/acaadb30-214c-4b42-b893-33de68230083)

```
