import unittest

import numpy as np

from sonictag.steganography import SonicScanner, SonicStegoDecoder, SonicStegoEncoder
from sonictag.transceiver import SonicReceiver, SonicTransmitter


class TestSteganography(unittest.TestCase):
    def setUp(self):
        self.fs = 48000
        self.scanner = SonicScanner(sample_rate=self.fs)
        self.tx = SonicTransmitter(sample_rate=self.fs)
        self.receiver = SonicReceiver(sample_rate=self.fs)

        # High-level orchestrators
        self.encoder = SonicStegoEncoder(sample_rate=self.fs)
        self.decoder = SonicStegoDecoder(sample_rate=self.fs)

    def test_fragmentation_logic(self):
        """Test that encoder correctly splits bytes and adds headers (internal method)."""
        payload = b"A" * 100
        n_frags = 5

        # Access internal helper
        fragments = self.encoder._fragment_payload(payload, n_fragments=n_frags)

        self.assertEqual(len(fragments), n_frags)

        # Verify headers
        # [MsgID, Index, Total]
        first_frag = fragments[0]
        self.assertEqual(first_frag[1], 0)  # Index 0
        self.assertEqual(first_frag[2], n_frags)  # Total 5

    def test_encode_no_audio(self):
        """Test that encoder fails with no audio."""
        with self.assertRaises(ValueError):
            self.encoder.encode(np.zeros(100, dtype=np.float32), "test")

    def test_decode_no_audio(self):
        """Test that decoder fails with no audio."""
        self.assertIsNone(self.decoder.decode(np.zeros(100, dtype=np.float32)))

    def test_end_to_end_orchestration(self):
        """Test the full loop using Encoder and Decoder."""
        # 1. Host Audio
        duration = 2.5
        host_audio = np.zeros(int(self.fs * duration), dtype=np.float32)

        # Add a "loud" burst to act as a masking window
        start = int(0.5 * self.fs)
        end = int(1.0 * self.fs)
        host_audio[start:end] = 0.5 * np.sin(2 * np.pi * 440 * np.linspace(0, 0.5, end - start))

        payload = "SecretMessage"

        # 2. Encode with auto splits
        stego_audio = self.encoder.encode(host_audio, payload)
        assert stego_audio.shape == host_audio.shape

        # 3. Decode
        decoded_msg = self.decoder.decode(stego_audio)

        self.assertEqual(decoded_msg, payload)

    def test_end_to_end_orchestration_multichannel(self):
        """Test the full loop using Encoder and Decoder."""
        # 1. Host Audio
        duration = 2.0
        host_audio = np.zeros((int(self.fs * duration), 2), dtype=np.int16)

        # Add a "loud" burst to act as a masking window
        start = int(0.5 * self.fs)
        end = int(1.0 * self.fs)
        host_audio[start:end, 0] = 32767 * 0.5 * np.sin(2 * np.pi * 440 * np.linspace(0, 0.5, end - start))

        payload = "SecretMessage"

        # 2. Encode
        stego_audio = self.encoder.encode(host_audio, payload, force_splits=1)
        assert stego_audio.shape == host_audio.shape

        # 3. Decode
        decoded_msg = self.decoder.decode(stego_audio)

        self.assertEqual(decoded_msg, payload)

    def test_decode_non_utf8(self):
        """Test that decoder fails with non-UTF-8 payload."""
        data = b"\xff\xff\xff"
        duration = 1.0
        audio = 0.5 * np.ones((int(self.fs * duration), 1), dtype=np.float32)
        fragment = self.tx.create_audio_frame(data)
        audio = self.encoder._inject(audio, [fragment], [(0, 0, len(fragment))])
        payload = self.decoder.decode(audio)
        self.assertEqual(payload, data)

    def test_scanner_windows(self):
        # Create synthetic audio with loud bursts
        duration = 5.0  # seconds
        audio = np.random.normal(0, 0.01, int(self.fs * duration))  # Quiet noise

        # Make a loud burst at 1.0s - 1.5s
        start = int(1.0 * self.fs)
        end = int(1.5 * self.fs)
        start2 = int(2.0 * self.fs)
        end2 = int(2.5 * self.fs)
        t = np.linspace(0, (end - start) / self.fs, end - start)
        t2 = np.linspace(0, (end2 - start2) / self.fs, end2 - start2)
        burst = 0.5 * np.sin(2 * np.pi * 440 * t)
        ultrasonics = 0.5 * np.sin(2 * np.pi * 18000 * t2)
        audio[start:end] = burst
        audio[start2:end2] += ultrasonics

        # Reshape to 2D (N, 1) so Scanner returns (ch, start, end)
        audio = audio[:, np.newaxis]

        windows = self.scanner.find_windows(audio)
        self.assertEqual(len(windows), 1)

        w_ch, w_start, w_end = windows[0]
        self.assertGreaterEqual(w_start, start - 1000)
        self.assertLess(w_end, end + 1000)
        self.assertEqual(w_ch, 0)

    def test_injector_mix(self):
        """Test internal injection logic."""
        host = 0.2 * np.ones((int(self.fs * 1.0), 1), dtype=np.float32)
        # Create a dummy audio fragment
        frag_bytes = b"dummy"
        frag_audio = self.tx.create_audio_frame(frag_bytes)

        windows = [(0, 1000, 1000 + len(frag_audio))]

        mixed = self.encoder._inject(host, [frag_audio], windows)

        # Check peak normalization (host is silent, frag is amplified then normalized)
        self.assertAlmostEqual(np.max(np.abs(mixed)), 0.2, places=2)

    def test_fragmenter_limits(self):
        payload = b"short"
        with self.assertRaises(ValueError):
            self.encoder._fragment_payload(payload, 0)
        with self.assertRaises(ValueError):
            self.encoder._fragment_payload(payload, 256)

    def test_scanner_no_windows(self):
        quiet = np.zeros(self.fs * 2)
        windows = self.scanner.find_windows(quiet, threshold_rms=0.1)
        self.assertEqual(len(windows), 0)

    def test_injector_bounds(self):
        host = np.zeros((100, 1))
        frag = np.ones(50)
        windows = [(0, 80, 130)]  # 80+50 = 130 > 100
        mixed = self.encoder._inject(host, [frag], windows)
        self.assertEqual(np.max(mixed), 0.0)

    def test_scanner_multichannel(self):
        """Test scanning on stereo audio."""
        duration = 1.0
        stereo = np.zeros((int(self.fs * duration), 2))

        # Channel 0: Burst at 0.1s
        s1 = int(0.1 * self.fs)
        e1 = int(0.2 * self.fs)
        stereo[s1:e1, 0] = 0.5 * np.sin(2 * np.pi * 440 * np.linspace(0, 0.1, e1 - s1))

        # Channel 1: Burst at 0.5s
        s2 = int(0.5 * self.fs)
        e2 = int(0.6 * self.fs)
        stereo[s2:e2, 1] = 0.5 * np.sin(2 * np.pi * 440 * np.linspace(0, 0.1, e2 - s2))

        windows = self.scanner.find_windows(stereo, top_n=None)

        self.assertGreaterEqual(len(windows), 2)
        ch0_windows = [w for w in windows if w[0] == 0]
        ch1_windows = [w for w in windows if w[0] == 1]

        self.assertTrue(len(ch0_windows) > 0)
        self.assertTrue(len(ch1_windows) > 0)

    def test_injector_multichannel(self):
        host = 0.5 * np.ones((int(self.fs * 0.5), 2), dtype=np.float32)
        frag = np.ones(100, dtype=np.float32)
        windows = [(1, 0, 100)]
        mixed = self.encoder._inject(host, [frag], windows)

        self.assertEqual(mixed.shape, host.shape)
        # Ch0 silent
        self.assertEqual(np.max(np.abs(mixed[:, 0])), 0.4)
        # Ch1 active
        self.assertEqual(np.max(np.abs(mixed[:, 1])), 0.5)

    def test_scanner_short_audio(self):
        short_audio = np.zeros(1000)
        windows = self.scanner.find_windows(short_audio)
        self.assertEqual(len(windows), 0)

    def test_injector_invalid_channel(self):
        host = np.zeros((1000, 2))
        frag = np.ones(100)
        windows = [(5, 0, 100)]
        mixed = self.encoder._inject(host, [frag], windows)
        self.assertEqual(np.max(np.abs(mixed)), 0.0)
