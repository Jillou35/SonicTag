import argparse
import logging
from pathlib import Path

import soundfile as sf

from sonictag.steganography import SonicStegoDecoder

# Configure Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("StealthDecoder")


def decode_stealth_file(input_path: str):
    # 1. Load Audio
    logger.info(f"Loading audio: {input_path}")
    try:
        data, fs = sf.read(input_path)
    except Exception as e:
        logger.error(f"Failed to read file: {e}")
        return

    # Use High-Level Decoder
    logger.info("Attempting to decode stealth message...")
    decoder = SonicStegoDecoder(sample_rate=fs)

    msg_str = decoder.decode(data)

    if msg_str:
        logger.info("------------------------------------------------")
        logger.info(f'SUCCESS! Reassembled Message: "{msg_str}"')
        logger.info("------------------------------------------------")
    else:
        logger.warning("No fragments detected or reassembly failed.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extract secret message from stealth audio")
    parser.add_argument("input", type=Path, help="Input wav file")

    args = parser.parse_args()

    decode_stealth_file(args.input)
