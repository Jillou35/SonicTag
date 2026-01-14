import argparse
import logging
from pathlib import Path

import numpy as np
import soundfile as sf  # Use soundfile for better format support

from sonictag.steganography import SonicStegoEncoder

# Configure Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("StealthAudio")


def create_stealth_file(
    input_path: Path,
    output_path: Path | None,
    payload_str: str,
    force_splits: int = None,
):
    # 0. Validate Output Format
    # MP3 destroys ultrasonic content due to psychoacoustic compression.
    if output_path is None:
        output_path = input_path.with_name(input_path.stem + "_stego.wav")
        logger.info(f"No output path specified. Using {output_path}")
    out_ext = output_path.suffix.lower()
    if out_ext not in [".wav", ".flac"]:
        logger.error(
            f"Output must be a lossless format (.wav, .flac). {out_ext} compression will destroy the hidden data."
        )
        return

    # 1. Load Audio
    logger.info(f"Loading host audio: {input_path}")
    try:
        # returns data, samplerate
        data, fs = sf.read(input_path)
        logger.info(f"Loaded audio: {data.shape}, dtype={data.dtype}, range=[{np.min(data):.3f}, {np.max(data):.3f}]")
    except Exception as e:
        logger.error(f"Failed to read input file: {e}")
        return

    logger.info(f"Loaded audio: {data.shape}, dtype={data.dtype}, range=[{np.min(data):.3f}, {np.max(data):.3f}]")

    # Use High-Level Encoder
    encoder = SonicStegoEncoder(sample_rate=fs)

    logger.info("Encoding stealth payload...")
    try:
        # Encoder handles Scanning, Fragmentation, Injection, and Normalization
        stego_audio = encoder.encode(data, payload_str, force_splits=force_splits)
    except Exception as e:
        logger.error(f"Encoding failed: {e}")
        return

    # 6. Save
    logger.info(f"Saving to {output_path}")
    sf.write(output_path, stego_audio, fs)
    logger.info("Done.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Embed secret message into audio file (Steganography)")
    parser.add_argument("input", type=Path, help="Input wav file")
    parser.add_argument("--output", "-o", type=Path, help="Output wav file", default=None)
    parser.add_argument("--data", "-d", type=str, help="Secret message string", default="Test Message")
    parser.add_argument("--splits", "-s", type=int, help="Force N splits (Optional)", default=None)

    args = parser.parse_args()

    create_stealth_file(args.input, args.output, args.data, args.splits)
