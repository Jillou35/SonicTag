# SonicTag

**Ultrasonic Data Transmission over Audio**

SonicTag is a Python package that enables data transmission between devices using ultrasonic audio signals (17kHz - 20kHz). It uses **OFDM** (Orthogonal Frequency-Division Multiplexing) and **Reed-Solomon** error correction to provide robust, near-audible data transfer through standard microphones and speakers.

![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)
![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)
![Version](https://img.shields.io/badge/version-0.1.0-blue.svg)
![Tests](https://img.shields.io/badge/tests-passing-green.svg)

## Features

*   **OFDM Modulation**: Uses 1024-point FFT with differential BPSK for robust data encoding.
*   **Error Correction**: Reed-Solomon ECC handles bursts of errors and acoustic noise.
*   **Ultrasonic Band**: Operates in the 17.5kHz - 20.5kHz range, making it mostly inaudible to adults.
*   **Robust Sync**: Chirp-based synchronization and robust header validation.
*   **Steganography (Fragmented Insertion)**: Splits payloads into small fragments and stealthily injects them into high-energy ("loud") windows of a host audio file (e.g., music), using auditory masking to hide the data.
*   **Cross-Platform**: Works on any system with Python and audio hardware.

## Installation

```bash
pip install sonictag
```

Or install from source:

```bash
git clone https://github.com/jillou35/SonicTag.git
cd SonicTag
pip install .
```

## Quick Start

### Transmitter

```python
import sounddevice as sd
from sonictag import SonicTransmitter

tx = SonicTransmitter(sample_rate=48000)
payload = b"Hello, World!"
audio_frame = tx.create_audio_frame(payload)

# Play audio
sd.play(audio_frame, samplerate=48000)
sd.wait()
```

### Receiver

```python
import sounddevice as sd
from sonictag import SonicReceiver

rx = SonicReceiver(sample_rate=48000)

def audio_callback(indata, frames, time, status):
    # Process audio chunk
    decoded, consumed = rx.decode_frame(indata[:, 0])
    if decoded:
        print(f"Received: {decoded}")

with sd.InputStream(callback=audio_callback, channels=1, samplerate=48000):
    print("Listening...")

    while True:
        pass
```

### Steganography

**Encoder (Hiding Data)**

```python
import soundfile as sf
from sonictag import SonicStegoEncoder

# 1. Load Host Audio
host_audio, fs = sf.read("music.wav")

# 2. Encode
encoder = SonicStegoEncoder(sample_rate=fs)
stego_audio = encoder.encode(host_audio, "Secret Payload")

# 3. Save
sf.write("stego_output.wav", stego_audio, fs)
```

**Decoder (Extracting Data)**

```python
import soundfile as sf
from sonictag import SonicStegoDecoder

# 1. Load Stego Audio
stego_audio, fs = sf.read("stego_output.wav")

# 2. Decode
decoder = SonicStegoDecoder(sample_rate=fs)
message = decoder.decode(stego_audio)

print(f"Decoded: {message}")
```

## Web App Demo

To run the full web application demo (Frontend + Backend):

### 1. Backend Setup

1. Navigate to the backend directory:
```bash
    cd web_app/backend
```
2. Install requirements:
```bash
    pip install -r requirements.txt
```
3. Start the FastAPI server:
```bash
    uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### 2. Frontend Setup

1. Navigate to the frontend directory:
```bash
    cd web_app/frontend
```
2. Install dependencies:
```bash
    npm install
```
3. Start the development server:
```bash
    npm run dev
```

### 3. Usage

1. Open the URL shown in the frontend terminal (usually `https://localhost:5173`).
2. Grant microphone permissions when prompted.
3. Use the interface to transmit and receive data between devices or tabs.

## Scripts

### Acoustic Loopback Test

The `scripts/acoustic_loopback.py` script verifies the entire acoustic chain (Speaker -> Microphone) on your local machine. It creates a signal, plays it, records it immediately, and attempts to decode it.

**Usage:**

```bash
python scripts/acoustic_loopback.py --fs 48000
```

**Options:**

*   `--fs`: Sample rate (default: 48000).
*   `--device-in`: Input device index (see `python -m sounddevice`).
*   `--device-out`: Output device index.

### Stealth Audio (Steganography)

The `scripts/create_stealth_audio.py` script allows you to inject a hidden message into an existing audio file significantly louder than the message itself (masking). It uses fragmented insertion to split the payload into small bursts that fit into "loud" windows of the host audio.

**Key Features:**
*   **Multi-Channel Support**: Natively handles stereo/multi-channel files without downmixing.
*   **Stereo Preservation**: Injects fragments into specific channels where masking is effective, while preserving the original stereo image and relative volume balance via global normalization.
*   **Smart Splitting**: Automatically determines the optimal number of fragments based on payload size and available masking windows.

**Usage:**

***Encoder (Hiding Data)***

```bash
python scripts/create_stealth_audio.py input.mp3 -o output.wav -d "Secret Message"
```
**Options:**

*   `input`: Path to the input WAV file (host audio).
*   `--output`, `-o`: (Optional) Path to save the steganographic audio.
*   `--data`, `-d`: (Optional) The string message to encode.
*   `--splits`, `-s`: (Optional) Force the message to be split into N fragments. By default, the script automatically detects available masking windows.

> **Note**: The output **MUST** be saved as `.wav` or `.flac`. Saving as `.mp3` or other lossy formats will destroy the hidden ultrasonic data.

***Decoder (Extracting Data)***

```bash
python scripts/decode_stealth_audio.py input.wav
```
**Options:**

*   `input`: Path to the input WAV file (host audio).


## Architecture

1. **SonicDataHandler**: Encodes raw bytes into packets with Length, CRC32, and Reed-Solomon parity.
2. **SonicOFDM**: Maps bits to frequency subcarriers and generates time-domain OFDM symbols.
3. **SonicSync**: Generates and detects linear chirps for frame synchronization.
4. **SonicTransceiver**: Combines these modules to provide a high-level `transmit` / `receive` API.
5. **SonicStegoEncoder / SonicStegoDecoder**: Orchestrates the scanning, fragmentation, and injection of hidden payloads into host audio files.

## Testing

Run the test suite with:

```bash
pip install .[test]
pytest tests/
```

## License

MIT
