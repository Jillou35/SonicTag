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


## Architecture

1. **SonicDataHandler**: Encodes raw bytes into packets with Length, CRC32, and Reed-Solomon parity.
2. **SonicOFDM**: Maps bits to frequency subcarriers and generates time-domain OFDM symbols.
3. **SonicSync**: Generates and detects linear chirps for frame synchronization.
4. **SonicTransceiver**: Combines these modules to provide a high-level `transmit` / `receive` API.

## Testing

Run the test suite with:

```bash
pip install .[test]
pytest tests/
```

## License

MIT
