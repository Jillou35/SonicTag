import unittest
import struct
from sonictag.data import SonicDataHandler, ReedSolomonError

class TestSonicDataHandler(unittest.TestCase):
    def setUp(self):
        self.handler = SonicDataHandler(ec_bytes=10)

    def test_encode_decode_integrity(self):
        payload = b"Hello, SonicTag!"
        encoded = self.handler.encode(payload)
        decoded = self.handler.decode(encoded)
        self.assertEqual(payload, decoded)

    def test_error_correction(self):
        payload = b"Robust Communication"
        encoded = bytearray(self.handler.encode(payload))
        
        # Corrupt some bytes in the payload part
        # Header size is 2+4+2 = 8 bytes
        # Let's corrupt the 9th, 10th, 11th bytes (which are part of the RS block)
        encoded[8] ^= 0xFF
        encoded[9] ^= 0xFF
        encoded[10] ^= 0xFF
        
        decoded = self.handler.decode(bytes(encoded))
        self.assertEqual(payload, decoded)

    def test_too_many_errors(self):
        payload = b"Fragile Data"
        encoded = bytearray(self.handler.encode(payload))
        
        # Corrupt more bytes than EC capability (ec_bytes=10, can correct 5)
        # Corrupt 6 bytes
        for i in range(6):
            encoded[10 + i] ^= 0xFF
            
        with self.assertRaises(ReedSolomonError):
            self.handler.decode(bytes(encoded))

    def test_data_decode_short_stream(self):
        """Test decoding stream shorter than header."""
        with self.assertRaisesRegex(ValueError, "stream too short"):
            self.handler.decode(b'\x00\x00')

    def test_data_decode_invalid_checksum(self):
        """Test decoding with corrupted length checksum."""
        # Header: Len(2), CRC(4), InvLen(2)
        # Create a fake header
        length = 10
        crc = 0xDEADBEEF
        inv_length = 0xFFFF # Wrong check (should be ~length)
        header = struct.pack('!HIH', length, crc, inv_length)
        payload = b'x' * 10
        
        with self.assertRaisesRegex(ValueError, "Header Corruption"):
            self.handler.decode(header + payload)

    def test_data_decode_oversized_payload(self):
        """Test decoding payload exceeding size limit."""
        length = 9000 # > 8192
        inv_length = (~length) & 0xFFFF
        header = struct.pack('!HIH', length, 0, inv_length)
        
        with self.assertRaisesRegex(ValueError, "exceeds max limit"):
            # Provide enough data so it doesn't fail on "incomplete packet" first
            self.handler.decode(header + b'x' * 9000)

    def test_data_decode_incomplete_packet(self):
        """Test decoding when data is less than expected length."""
        length = 50
        inv_length = (~length) & 0xFFFF
        header = struct.pack('!HIH', length, 0, inv_length)
        # Only provide 10 bytes
        with self.assertRaisesRegex(ValueError, "Incomplete packet"):
            self.handler.decode(header + b'x'*10)

