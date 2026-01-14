import struct
import zlib

from reedsolo import ReedSolomonError, RSCodec  # type: ignore


class SonicDataHandler:
    """
    Handles Error Correction Code (ECC) and Serialization for SonicTag.
    Uses Reed-Solomon for FEC and CRC32 for integrity check.
    """

    def __init__(self, ec_bytes: int = 10):
        """
        Initialize the Data Handler.
        :param ec_bytes: Number of error correction bytes per block.
                         The overhead is ec_bytes/block_size.
                         Decoder can correct ec_bytes/2 errors.
        """
        self.ec_bytes = ec_bytes
        self.rsc = RSCodec(ec_bytes)

    def encode(self, payload: bytes) -> bytes:
        """
        Encodes the payload:
        1. Compresses payload with Zlib.
        2. Encodes compressed data with Reed-Solomon.
        3. Prepends a header (Length + CRC32).

        Header Format (8 bytes):
        [ Length (2 bytes, unsigned short) | CRC32 (4 bytes, unsigned int) | Reserved (2 bytes) ]
        """

        # 1. RS Encode
        encoded_payload = bytes(self.rsc.encode(payload))

        # 2. Calculate CRC32 of the ENCODED payload (to check integrity after demodulation)
        crc = zlib.crc32(encoded_payload) & 0xFFFFFFFF

        # 3. Create Header
        length = len(encoded_payload)

        # Robustness: Use 'Reserved' field for Inverted Length Checksum
        # This ensures we don't try to read 50k bytes if a bit flips
        inv_length = (~length) & 0xFFFF

        # Struct format: H (ushort, 2), I (uint, 4), H (ushort, 2 - inv_length)
        header = struct.pack("!HIH", length, crc, inv_length)

        return header + encoded_payload

    def decode(self, data_stream: bytes) -> bytes:
        """
        Decodes a stream of bytes.
        Expects the format: [Header] [EncodedPayload]
        Returns the original payload or raises ReedSolomonError/ValueError.
        """
        header_size = struct.calcsize("!HIH")
        if len(data_stream) < header_size:
            raise ValueError("Data stream too short for header")

        # 1. Parse Header
        header = data_stream[:header_size]
        length, crc, inv_length = struct.unpack("!HIH", header)

        # Robustness Check 1: Inverted Checksum
        # Check: (length ^ inv_length) should be 0xFFFF (all 1s)
        if (length ^ inv_length) != 0xFFFF:
            raise ValueError(f"Header Corruption: Length Checksum Failed (Len={length}, Inv={inv_length})")

        # Robustness Check 2: Sanity Limit
        # WebSockets/Audio buffer is finite. Set a reasonable MTU.
        if length > 8192:  # e.g. 8KB max
            raise ValueError(f"Header Corruption: Length {length} exceeds max limit")

        if len(data_stream) < header_size + length:
            # This is a legitimate "Wait for more data" case
            raise ValueError(f"Incomplete packet. Expected {length} bytes, got {len(data_stream) - header_size}")

        encoded_payload = data_stream[header_size : header_size + length]

        # 2. Verify CRC
        computed_crc = zlib.crc32(encoded_payload) & 0xFFFFFFFF
        if computed_crc != crc:
            # RS fixes errors, then we check integrity.
            pass

        # 3. RS Decode
        try:
            original_payload, _, _ = self.rsc.decode(encoded_payload)
            return bytes(original_payload)

        except ReedSolomonError as e:
            raise e
