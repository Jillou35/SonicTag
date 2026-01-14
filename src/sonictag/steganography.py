import math
import random
import struct

import numpy as np
from scipy import signal

from .transceiver import SonicReceiver, SonicTransmitter


class SonicScanner:
    """
    Analyzes audio to find high-energy masking windows.
    Shared by Encoder (to find spots) and Decoder (to find spots).
    """

    def __init__(
        self,
        sample_rate: int = 48000,
        window_duration: float = 0.3,
        start_freq: int = 17500,
        end_freq: int = 20500,
    ):
        self.fs = sample_rate
        self.window_samples = int(window_duration * self.fs)
        self.start_freq = start_freq
        self.end_freq = end_freq

    def find_windows(
        self, host_audio: np.ndarray, top_n: int | None = None, threshold_rms: float = 0.05
    ) -> list[tuple]:
        """
        Scans audio and returns list of indices for suitable windows.
        Returns [(channel, start, end), ...]
        If top_n is provided, returns best N matches globally.
        """

        # Unify input to (N, Channels)
        if host_audio.ndim == 1:
            work_audio = host_audio[:, np.newaxis]
        else:
            work_audio = host_audio

        n_samples, n_channels = work_audio.shape
        step = self.window_samples // 2

        all_candidates = []  # (RMS, channel, start, end)

        # Scan each channel
        for ch in range(n_channels):
            channel_data = work_audio[:, ch]

            # --- Pre-filter (Ultrasonic Detection) ---
            sos = signal.butter(
                4,
                [self.start_freq, self.end_freq],
                btype="bandpass",
                fs=self.fs,
                output="sos",
            )
            ultrasonic_layer = signal.sosfilt(sos, channel_data)

            if len(channel_data) < self.window_samples:
                continue

            # Scan Loop
            for i in range(0, len(channel_data) - self.window_samples + 1, step):
                window = channel_data[i : i + self.window_samples]
                us_window = ultrasonic_layer[i : i + self.window_samples]

                # Broadband Loudness
                rms_broadband = np.sqrt(np.mean(window**2))

                # Ultrasonic Interference
                rms_interference = np.sqrt(np.mean(us_window**2))

                if rms_interference > 0.05:
                    continue

                all_candidates.append((rms_broadband, ch, i, i + self.window_samples))

        # Sort Globally by RMS
        all_candidates.sort(key=lambda x: x[0], reverse=True)

        # Select Top N (filtering overlaps per channel)
        selected_windows = []
        occupied_masks = [np.zeros(n_samples, dtype=bool) for _ in range(n_channels)]
        gap = int(0.1 * self.fs)

        for rms, ch, start_idx, end_idx in all_candidates:
            # Check threshold (since list is sorted, we can stop if we drop below)
            if top_n is None and rms < threshold_rms:
                break

            # Check Overlap in SPECIFIC Channel
            mask = occupied_masks[ch]
            region_start = max(0, start_idx - gap)
            region_end = min(n_samples, end_idx + gap)

            if np.any(mask[region_start:region_end]):
                continue

            # Valid Selection
            selected_windows.append((ch, start_idx, end_idx))
            mask[region_start:region_end] = True

            if top_n is not None and len(selected_windows) >= top_n:
                break

        # Sort chronologically by Start Time
        selected_windows.sort(key=lambda x: x[1])

        return selected_windows


class SonicStegoEncoder:
    """
    High-level orchestration for embedding payloads into audio.
    Handling scanning, fragmentation, and injection.
    """

    def __init__(self, sample_rate: int = 48000):
        self.fs = sample_rate
        self.scanner = SonicScanner(sample_rate=sample_rate)
        self.tx = SonicTransmitter(sample_rate=sample_rate)

    def encode(self, host_audio: np.ndarray, payload: str, force_splits: int | None = None) -> np.ndarray:
        """
        Encodes a string payload into the host audio.
        Returns the modified audio array.
        """
        payload_bytes = payload.encode("utf-8")

        # Unified Mono/Multi handling
        was_mono = False
        if host_audio.ndim == 1:
            was_mono = True
            work_audio = host_audio[:, np.newaxis].astype(np.float32).copy()
        else:
            work_audio = host_audio.astype(np.float32).copy()

        if host_audio.dtype == np.int16:
            work_audio = work_audio / 32767.0

        # 1. Determine Splits / Find Windows
        if force_splits:
            target_splits = force_splits
        else:
            # Heuristic: Minimum 2 bytes per fragment
            MIN_FRAG_SIZE = 2
            target_splits = max(1, len(payload_bytes) // MIN_FRAG_SIZE)

        # Scan
        windows = self.scanner.find_windows(work_audio, top_n=target_splits, threshold_rms=0.01)

        n_splits = len(windows)

        if n_splits == 0:
            raise ValueError("No suitable masking windows found in audio.")

        # 2. Fragment Payload
        raw_fragments = self._fragment_payload(payload_bytes, n_fragments=n_splits)

        # 3. Create Audio Packets (Modulation)
        audio_fragments = []
        for raw_frag in raw_fragments:
            frame = self.tx.create_audio_frame(raw_frag)
            audio_fragments.append(frame)

        # 4. Inject
        stego_audio = self._inject(work_audio, audio_fragments, windows)

        if was_mono:
            stego_audio = stego_audio[:, 0]

        return stego_audio

    def _fragment_payload(self, payload: bytes, n_fragments: int) -> list[bytes]:
        """Splits payload and adds steg headers."""
        if n_fragments < 1:
            raise ValueError("n_fragments must be >= 1")

        if n_fragments > 255:
            raise ValueError("Max 255 fragments supported")

        total_len = len(payload)
        chunk_size = math.ceil(total_len / n_fragments)

        fragments_bytes = []
        msg_id = random.randint(0, 255)

        for i in range(n_fragments):
            start = i * chunk_size
            end = min(start + chunk_size, total_len)
            chunk = payload[start:end]

            # Header: [MsgID, Index, Total]
            header = struct.pack("BBB", msg_id, i, n_fragments)
            full_payload = header + chunk

            fragments_bytes.append(full_payload)

        return fragments_bytes

    def _inject(
        self,
        host_audio: np.ndarray,
        fragments: list[np.ndarray],
        windows: list[tuple],
        apply_headroom: bool = True,
        normalize_output: bool = True,
    ) -> np.ndarray:
        """Internal injection logic."""

        n_samples, n_channels = host_audio.shape

        # Headroom
        if apply_headroom:
            current_max = np.max(np.abs(host_audio))
            if current_max > 0:
                target_host_peak = 0.8
                scaling_factor = target_host_peak / max(current_max, 1e-9)
                host_audio *= scaling_factor

        fade_len = int(0.005 * self.fs)
        fragment_amp = 0.2

        for fragment, window_tuple in zip(fragments, windows, strict=True):
            ch, start, end = window_tuple

            if ch >= n_channels:
                continue

            frag_len = len(fragment)
            if start + frag_len > n_samples:
                continue

            scaled_frag = fragment * fragment_amp

            # Fade
            if frag_len > 2 * fade_len:
                scaled_frag[:fade_len] *= np.linspace(0, 1, fade_len)
                scaled_frag[-fade_len:] *= np.linspace(1, 0, fade_len)

            host_audio[start : start + frag_len, ch] += scaled_frag

        # Normalize to initial max
        if normalize_output:
            final_peak = np.max(np.abs(host_audio))
            if final_peak > 0:
                host_audio *= current_max / final_peak

        return host_audio


class SonicStegoDecoder:
    """
    High-level orchestration for extracting payloads from audio.
    """

    def __init__(self, sample_rate: int = 48000):
        self.fs = sample_rate
        self.scanner = SonicScanner(sample_rate=sample_rate)
        self.rx = SonicReceiver(sample_rate=sample_rate)

    def decode(self, stego_audio: np.ndarray) -> str | bytes | None:
        """
        Attempts to find and decode a hidden payload from the audio.
        """
        windows = self.scanner.find_windows(stego_audio, top_n=None, threshold_rms=0.01)

        if stego_audio.ndim == 1:
            read_audio = stego_audio[:, np.newaxis]
        else:
            read_audio = stego_audio

        pad = int(0.1 * self.fs)

        for w in windows:
            ch, start, end = w

            start_idx = max(0, start - pad)
            end_idx = min(len(read_audio), end + pad)

            chunk = read_audio[start_idx:end_idx, ch]
            payload_bytes, _ = self.rx.decode_frame(chunk)

            if payload_bytes:
                full_msg = self.rx.reassemble(payload_bytes)
                if full_msg:
                    try:
                        return full_msg.decode("utf-8")
                    except UnicodeDecodeError:
                        return full_msg

        return None
