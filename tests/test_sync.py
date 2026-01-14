import unittest

import numpy as np

from sonictag.sync import SonicSync


class TestSonicSync(unittest.TestCase):
    def setUp(self):
        self.sync = SonicSync(duration=0.01)

    def test_preamble_generation(self):
        preamble = self.sync.generate_preamble()
        expected_len = int(self.sync.fs * self.sync.duration)
        self.assertEqual(len(preamble), expected_len)
        self.assertTrue(np.max(np.abs(preamble)) <= 1.0)

    def test_detection_ideal(self):
        preamble = self.sync.generate_preamble()

        # Embed preamble in silence
        silence_before = np.zeros(100)
        silence_after = np.zeros(200)
        signal = np.concatenate([silence_before, preamble, silence_after])

        start_idx = self.sync.detect(signal)

        # Should detect start at 100
        # Allow small jitter? Ideal should be exact or +/- 1
        self.assertAlmostEqual(start_idx, 100, delta=1)

    def test_detection_with_offset(self):
        # Test just preamble
        preamble = self.sync.generate_preamble()
        start_idx = self.sync.detect(preamble)
        self.assertAlmostEqual(start_idx, 0, delta=1)

    def test_detection_with_emergence(self):
        # Test just preamble
        preamble = self.sync.generate_preamble()
        noise = np.random.normal(0, 0.05, 1000)
        signal = noise

        # Inject faint preamble
        preamble = self.sync.generate_preamble() * 0.005
        noise_before = np.random.normal(0, 0.0001, 100)
        noise_after = np.random.normal(0, 0.0001, 200)
        signal = np.concatenate([noise_before, preamble, noise_after])

        start_idx = self.sync.detect(signal)

        self.assertAlmostEqual(start_idx, 100, delta=1)

    def test_too_short_signal(self):
        # Test just preamble
        preamble = self.sync.generate_preamble()
        signal = preamble[: int(len(preamble) * 0.9)]
        start_idx = self.sync.detect(signal)
        self.assertEqual(start_idx, -1)

    def test_no_detection_silence(self):
        silence = np.zeros(1000)
        start_idx = self.sync.detect(silence, min_peak=10)  # Set reasonable threshold
        # Should return -1 or raise error? Implementation returns -1 if peak < min_peak
        # My implementation returns -1 if peak < min_peak
        # But wait, correlation of 0s is 0.
        self.assertEqual(start_idx, -1)

    def test_sync_low_snr_rejection(self):
        """Test that sync rejects weak peaks."""
        # Preamble energy is high (N/2 ~ 240).
        # To fail detection (min_peak=4.0), we need factor < 4/240 ~ 0.016
        # Let's use 0.01

        noise = np.random.normal(0, 0.001, 1000)
        signal = noise
        # Inject faint preamble
        # Peak response is ~240 * scale.
        # We need Peak < 0.3 for detection to fail even if SNR is high.
        # scale < 0.3 / 240 = 0.00125
        preamble = self.sync.generate_preamble() * 0.001
        start = 500
        signal[start : start + len(preamble)] += preamble

        # Should fail detect due to low peak (<0.3)
        idx = self.sync.detect(signal, min_peak=4.0)
        self.assertEqual(idx, -1)
