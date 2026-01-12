import unittest
import numpy as np
from unittest.mock import patch
from sonictag.transceiver import SonicTransmitter, SonicReceiver
from sonictag.data import SonicDataHandler


class TestTransceiver(unittest.TestCase):
    def setUp(self):
        self.fs = 48000
        self.tx = SonicTransmitter(sample_rate=self.fs)
        self.rx = SonicReceiver(sample_rate=self.fs)

    def test_create_audio_frame_structure(self):
        """Test physical properties of the generated frame."""
        payload = b"test"
        frame = self.tx.create_audio_frame(payload)

        # Check normalization (max amplitude <= 1.0)
        self.assertLessEqual(np.max(np.abs(frame)), 1.0)

        # Check fade in/out (start and end should be near 0)
        self.assertAlmostEqual(frame[0], 0, delta=0.1)
        self.assertAlmostEqual(frame[-1], 0, delta=0.1)

    def test_full_chain_normal(self):
        """Test standard transmit-receive loop."""
        payload = b"Hello World"
        frame = self.tx.create_audio_frame(payload)

        # Add padding for receive
        padding = np.zeros(4800, dtype=np.float32)
        rx_input = np.concatenate([padding, frame, padding])

        decoded, consumed = self.rx.decode_frame(rx_input)
        self.assertEqual(decoded, payload)
        self.assertGreater(consumed, 0)

    def test_full_chain_inverted_polarity(self):
        """Test receiver robustness to inverted signal."""
        payload = b"Inverted World"
        frame = self.tx.create_audio_frame(payload)

        # Invert signal
        frame = -frame

        padding = np.zeros(1000, dtype=np.float32)
        rx_input = np.concatenate([padding, frame, padding])

        decoded, consumed = self.rx.decode_frame(rx_input)
        self.assertEqual(decoded, payload)

    def test_decode_silence(self):
        """Test decoding silence returns nothing."""
        silence = np.zeros(48000, dtype=np.float32)
        decoded, consumed = self.rx.decode_frame(silence)
        self.assertIsNone(decoded)
        self.assertEqual(consumed, 0)

    def test_decode_noise(self):
        """Test decoding random noise returns nothing."""
        noise = np.random.normal(0, 0.01, 48000).astype(np.float32)
        decoded, consumed = self.rx.decode_frame(noise)
        self.assertIsNone(decoded)
        self.assertGreaterEqual(consumed, 0)

    def test_decode_corrupted_rs_failure(self):
        """
        Test that ReedSolomonError is caught and handled.
        Migrated from corner cases to be closer to transceiver logic.
        """
        data_handler = SonicDataHandler()

        # 1. Manually create frame with corrupt payload
        payload = b"Corrupt Me"
        encoded = data_handler.encode(payload)

        # Corrupt > ec_bytes/2
        corrupted = bytearray(encoded)
        # Offset 8 (header)
        for i in range(15):
            corrupted[8 + i] ^= 0xFF

        # 2. Modulate
        bits = self.tx.ofdm.bits_from_bytes(bytes(corrupted))
        warmup = np.ones(self.tx.ofdm.n_subcarriers, dtype=int)
        bits = np.concatenate([warmup, bits])
        ofdm_sig = self.tx.ofdm.modulate(bits)

        # 3. Assemble
        preamble = self.tx.sync.generate_preamble()
        gap = np.zeros(int(0.02 * self.fs), dtype=np.float32)
        padding = np.zeros(1000, dtype=np.float32)

        frame = np.concatenate([preamble, gap, ofdm_sig, padding])

        # 4. Decode
        decoded, consumed = self.rx.decode_frame(frame)
        self.assertIsNone(decoded)
        # Should report consumed > 0 because sync was found
        self.assertGreater(consumed, 0)

    def test_filter_signal_empty(self):
        """Test filter handles empty input gracefully."""
        res = self.rx.filter_signal(np.array([], dtype=np.float32))
        self.assertEqual(len(res), 0)

    def test_decode_truncated_packet(self):
        """Test decoding a packet cut off in the middle."""
        payload = b"Cut Me Off"
        frame = self.tx.create_audio_frame(payload)

        # Cut off the last 20% (Tail) to ensure Header is intact but Payload is incomplete
        truncated = frame[: int(len(frame) * 0.8)]

        # Padding only at start to allow sync
        padding = np.zeros(1000, dtype=np.float32)
        rx_input = np.concatenate([padding, truncated])

        decoded, consumed = self.rx.decode_frame(rx_input)
        self.assertIsNone(decoded)

        # Should NOT return error, but simply None, 0 (indicating wait for more data)
        # because it catches "Incomplete packet" or "too short"
        self.assertEqual(consumed, 0)

    def test_decode_packet_start_out_of_bounds(self):
        """
        Test condition where packet_start (calculated with offsets)
        exceeds buffer length loop.
        Matches line 152: if packet_start >= len(filtered_chunk)
        """
        # Create a dummy chunk
        rx_input = np.zeros(500, dtype=np.float32)

        # Mock sync.detect to return start of buffer (0)
        # But buffer is small (500).
        # Packet start calculation adds PreambleLen(~480) + Gap(~960) > 1400.
        # So 1400 > 500.
        # Should hit line 152 continue.

        with patch.object(self.rx.sync, "detect", return_value=0):
            decoded, consumed = self.rx.decode_frame(rx_input)

        self.assertIsNone(decoded)
        # Should NOT consume because no valid frame found (loop finished)
        self.assertEqual(consumed, 0)

    def test_decode_warmup_only_symbol_path(self):
        """
        Test condition where decoded bits <= n_subcarriers.
        Matches line 163: else: bits = all_bits

        We explicitly construct a signal that demodulates to exactly 1 symbol.
        And we Force Sync Detect to point to it.
        """
        # 1. Build minimal OFDM signal (Ref + 1 Symbol)
        # Use bits_per_symbol to ensure we generate exactly 1 symbol
        n_bits = self.tx.ofdm.bits_per_symbol
        warmup_bits = np.ones(n_bits, dtype=int)
        ofdm_sig = self.tx.ofdm.modulate(warmup_bits)

        # 2. Construct Frame directly (NO Preamble needed if we mock detect!)
        # Mock detect will say "Preamble found at X".
        # We place our signal at "X + Preamble + Gap".

        preamble_len = len(self.rx.sync.generate_preamble())
        gap_len = int(0.02 * self.fs)

        # We need buffer large enough.
        # Let's say we pretend sync found at 100.
        sync_idx = 100
        padding_start = np.zeros(sync_idx + preamble_len + gap_len, dtype=np.float32)

        # Add ofdm_sig + some tail padding
        rx_input = np.concatenate(
            [padding_start, ofdm_sig, np.zeros(100, dtype=np.float32)]
        )

        # 3. Decode with Mock
        # Logic:
        # packet_start = start_idx(100) + preamble_len + gap_len + offset(0).
        # = len(padding_start).
        # So we start reading `ofdm_sig` exactly.

        # We need to ensure offset 0 is tried and works.
        # Logic loops offsets [-4..4].
        # For offset 0: packet_start = correct.
        # For others: shift slightly. Demod might still work or fail.
        # But offset 0 should hit "Line 163" condition.
        # And then raise Exception in data_handler.

        # NOTE: With default settings, n_subcarriers=32 bits = 4 bytes.
        # Header is 8 bytes. So data_handler.decode will normally raise "too short".
        # This causes transceiver to return (None, 0).
        # To verify we HIT the decode logic (Line 163), we mock data_handler.decode
        # to raise a specific error that results in consumption (e.g. Header Corruption).

        with patch.object(self.rx.sync, "detect", return_value=sync_idx), patch.object(
            self.rx, "filter_signal", side_effect=lambda x: x
        ), patch.object(
            self.rx.data_handler, "decode", side_effect=ValueError("Header Corruption")
        ):
            decoded, consumed = self.rx.decode_frame(rx_input)

        self.assertIsNone(decoded)

        # Exception should be raised (Header Corruption) -> last_error set -> returns 500
        self.assertGreater(consumed, 0)
