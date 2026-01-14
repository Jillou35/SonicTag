import unittest

import numpy as np

from sonictag.ofdm import SonicOFDM


class TestSonicOFDM(unittest.TestCase):
    def setUp(self):
        self.ofdm = SonicOFDM(n_fft=128, cp_len=16, start_freq=1000, end_freq=2000)

    def test_modulation_demodulation_loopback(self):
        # Create random bits
        n_bits = self.ofdm.bits_per_symbol * 5  # 5 symbols worth
        original_bits = np.random.randint(0, 2, n_bits)

        # Modulate
        signal = self.ofdm.modulate(original_bits)

        # Check signal properties
        self.assertTrue(np.max(np.abs(signal)) <= 1.0)

        # Demodulate (Ideal Loopback)
        decoded_bits = self.ofdm.demodulate(signal)

        # In ideal loopback, bits should match perfectly
        np.testing.assert_array_equal(original_bits, decoded_bits)

    def test_bit_byte_conversion(self):
        payload = b"Test"
        bits = self.ofdm.bits_from_bytes(payload)
        reconstructed_payload = self.ofdm.bytes_from_bits(bits)
        self.assertEqual(payload, reconstructed_payload)

    def test_ofdm_modulate_padding(self):
        """Test modulation with bit count not matching symbol alignment."""
        # bits_per_symbol depends on active bins. Default ~340.
        # Let's force a mismatch.
        n_bits = self.ofdm.bits_per_symbol + 1  # 1 full symbol + 1 bit
        bits = np.ones(n_bits, dtype=int)

        signal = self.ofdm.modulate(bits)
        # Should produce: 1 Ref + 1 Sym + 1 Sym (padded) = 3 symbols total
        symbol_len = self.ofdm.n_fft + self.ofdm.cp_len
        expected_len = 3 * symbol_len
        self.assertEqual(len(signal), expected_len)

    def test_ofdm_demodulate_too_short(self):
        """Test demodulation with insufficient samples."""
        symbol_len = self.ofdm.n_fft + self.ofdm.cp_len
        # Create signal shorter than 2 symbols
        short_signal = np.zeros(symbol_len + 10)
        # Needs Ref (1) + Data (1) = 2 symbols minimal

        bits = self.ofdm.demodulate(short_signal)
        self.assertEqual(len(bits), 0)
