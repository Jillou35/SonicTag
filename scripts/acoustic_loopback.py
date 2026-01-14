import argparse
import json
import logging
import time
from pathlib import Path

import numpy as np
import scipy.io.wavfile as wav
import sounddevice as sd

from sonictag.transceiver import SonicReceiver, SonicTransmitter

WAV_FOLDER = Path(__file__).parent.parent / "data"
WAV_FOLDER.mkdir(exist_ok=True, parents=True)

# Configure Logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("AcousticTest")
# Ensure library logs are visible
logging.getLogger("sonictag").setLevel(logging.DEBUG)


def run_acoustic_test(fs: int = 48000, device_in: int | None = None, device_out: int | None = None):
    # Configuration
    DURATION_SILENCE = 0.5

    logger.info("\n--- Audio Device List ---")
    logger.info(sd.query_devices())

    # Determine devices for logging
    used_in = device_in if device_in is not None else sd.default.device[0]
    used_out = device_out if device_out is not None else sd.default.device[1]

    logger.info(f"Using Input Device: {used_in} | Output Device: {used_out}")
    logger.info("-------------------------\n")

    logger.info(f"--- SonicTag Acoustic Loopback (fs={fs}) ---")

    # 1. Generate Signal
    tx = SonicTransmitter(sample_rate=fs)
    payload = {"text": "Hello Loopback!", "timestamp": time.time()}
    json_bytes = json.dumps(payload).encode("utf-8")

    audio_frame = tx.create_audio_frame(json_bytes)

    # Add silence padding
    silence = np.zeros(int(fs * DURATION_SILENCE), dtype=np.float32)
    tx_signal = np.concatenate([silence, audio_frame, silence])

    wav.write(WAV_FOLDER / "tx_test.wav", fs, tx_signal)

    # 2. Play and Record (Synchronous)
    logger.info("Starting Playback & Recording (Blocking)...")

    try:
        # playrec is the most robust way to do loopback
        # device argument: (input, output). None means default.
        recording = sd.playrec(
            tx_signal,
            samplerate=fs,
            channels=1,
            dtype="float32",
            blocking=True,
            device=(device_in, device_out),
        )

        rx_signal = recording.flatten()
        wav.write(WAV_FOLDER / "rx_test.wav", fs, rx_signal)
        logger.info(f"Recorded {len(rx_signal)} samples. Max Amp: {np.max(np.abs(rx_signal)):.4f}")

        # Normalize
        max_val = np.max(np.abs(rx_signal))
        if max_val > 0:
            rx_signal /= max_val
            logger.info("Normalized signal.")

        # 3. Decode
        rx = SonicReceiver(sample_rate=fs)
        decoded_payload, consumed = rx.decode_frame(rx_signal)

        if decoded_payload:
            try:
                msg = json.loads(decoded_payload.decode("utf-8"))
                logger.info(f"SUCCESS! Decoded Message: {msg}")
            except Exception:
                logger.info(f"SUCCESS! Decoded Raw: {decoded_payload!r}")
        else:
            logger.error("FAILURE: Could not decode.")

    except Exception as e:
        logger.error(f"Error: {e}")


if __name__ == "__main__":
    argparser = argparse.ArgumentParser(description="SonicTag Acoustic Loopback Test")
    argparser.add_argument("--fs", "-f", type=int, default=48000, help="Sample Rate")
    argparser.add_argument("--device-in", "-i", type=int, default=None, help="Input Device Index")
    argparser.add_argument("--device-out", "-o", type=int, default=None, help="Output Device Index")
    args = argparser.parse_args()

    # Pass device args to run function (need to update run_acoustic_test signature first)
    # But first, let's update the signature in the next step or do it all here given the tool limit?
    # I can't update run_acoustic_test signature in this block if it's far away.
    # The file is small, I can replace the main block and `run_acoustic_test` call instructions.

    # Wait, I need to update run_acoustic_test definition too.
    # I'll do this in multiple steps or a larger replace specific to the function call.
    # Actually, I can just update the call here and then update the function.
    run_acoustic_test(fs=args.fs, device_in=args.device_in, device_out=args.device_out)
