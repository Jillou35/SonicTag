import numpy as np
from scipy import signal
from .data import SonicDataHandler, ReedSolomonError
from .ofdm import SonicOFDM
from .sync import SonicSync
from .logger import logger

class SonicTransmitter:
    """
    Transmitter class for generating audio frames with OFDM modulation.
    """
    def __init__(self, sample_rate: int = 48000):
        self.fs = sample_rate
        self.data_handler = SonicDataHandler()
        self.ofdm = SonicOFDM(sample_rate=self.fs)
        self.sync = SonicSync(sample_rate=self.fs)

    def create_audio_frame(self, payload: bytes) -> np.ndarray:
        """
        Creates a full audio frame:
        [Preamble] [OFDM Modulated Data]
        """
        # 1. Encode Data (ECC + Header)
        encoded_bytes = self.data_handler.encode(payload)
        
        # 2. Convert to Bits
        bits = self.ofdm.bits_from_bytes(encoded_bytes)
        
        # WARM UP SYMBOL: Prepend a full symbol of 1s.
        # This causes the Modulator to repeat the Reference Symbol Phase (since 1 -> No Change).
        # This stabilizes the filter/channel before the real header bits.
        warmup_bits = np.ones(self.ofdm.bits_per_symbol, dtype=int)
        bits = np.concatenate([warmup_bits, bits])
        
        # 3. Modulate (OFDM)
        ofdm_signal = self.ofdm.modulate(bits)
        
        # 4. Generate Preamble
        preamble = self.sync.generate_preamble()
        
        # 5. Concatenate
        # Add a silence gap (Guard Interval) to prevent Preamble filter ringing/reverb
        # from interfering with the Reference Symbol.
        gap_len = int(0.02 * self.fs) # 20ms gap
        gap = np.zeros(gap_len, dtype=np.float32)
        
        raw_signal = np.concatenate([preamble, gap, ofdm_signal])
        
        # 6. Apply Bandpass Filter to smooth discontinuities
        # The raw concatenation of OFDM symbols creates step discontinuities.
        # These appear as broadband noise (clicks) at the symbol rate (~88Hz).
        sos = signal.butter(4, [17000, 21000], btype='bandpass', fs=self.fs, output='sos')
        full_signal = signal.sosfiltfilt(sos, raw_signal)
        # full_signal = raw_signal # BYPASS
        
        # Final normalize
        max_val = np.max(np.abs(full_signal))
        if max_val > 0:
            full_signal /= max_val
            
        # Apply a tiny fade in/out to the ENTIRE frame to ensure it starts/ends at 0
        # This prevents the "click" when the audio hardware starts playing a non-zero sample.
        taper_len = int(0.005 * self.fs) # 5ms taper
        if len(full_signal) > 2 * taper_len:
            # Fade In
            full_signal[:taper_len] *= np.linspace(0, 1, taper_len)
            # Fade Out
            full_signal[-taper_len:] *= np.linspace(1, 0, taper_len)

        return full_signal


class SonicReceiver:
    """
    Receiver class for demodulating audio frames with OFDM modulation.
    """
    def __init__(self, sample_rate: int = 48000):
        self.fs = sample_rate
        self.data_handler = SonicDataHandler()
        self.ofdm = SonicOFDM(sample_rate=self.fs)
        self.sync = SonicSync(sample_rate=self.fs)
        
        # Design Filter
        # Highpass Butterworth at 3kHz
        # Lower order (2) to minimize phase distortion
        nyquist = 0.5 * self.fs
        normal_cutoff = 17000 / nyquist
        # Ensure cutoff < 1.0 (3k < 24k)
        self.b, self.a = signal.butter(2, normal_cutoff, btype='high', analog=False)

    def filter_signal(self, audio_chunk: np.ndarray) -> np.ndarray:
        """
        Applies cleaning filters (Bandpass/Highpass).
        """
        if len(audio_chunk) == 0:
            return audio_chunk
            
        # 1. High-pass to remove DC/Hum (Critical for FFT)
        # 500Hz cutoff is safe for 1kHz+ carriers -> 16kHz for Ultrasonic
        sos = signal.butter(2, 16000, 'hp', fs=self.fs, output='sos')
        filtered = signal.sosfilt(sos, audio_chunk)
        
        # 2. Band-pass (Keep only 2k - 10k) 
        # Restoring with wider band to filter out low-freq noise/hum and high-freq aliasing
        # Ultrasonic 17k-21k
        sos_bp = signal.butter(4, [17000, 21000], 'bp', fs=self.fs, output='sos')
        filtered = signal.sosfilt(sos_bp, filtered)
        
        return filtered

    def decode_frame(self, audio_chunk: np.ndarray) -> tuple[bytes | None, int]:
        """
        Attempts to decode a single frame from the audio chunk.
        
        Returns:
            (payload, samples_consumed)
            - payload: bytes if success, None if fail/no-sync
            - samples_consumed: Number of samples to remove from start of buffer
        """
        # Try Normal AND Inverted Polarity
        # Some mics/browsers invert the phase, which might break reference tracking in DBPSK 
        # (though DBPSK is theoretically robust, reference initialization matters).
        
        candidates = [(audio_chunk, "Normal"), (-audio_chunk, "Inverted")]
        
        for signal_candidate, polarity in candidates:
             # 1. Filter
             filtered_chunk = self.filter_signal(signal_candidate)
             
             # 2. Sync Detect
             # Increase threshold to avoid false positives on noise
             start_idx = self.sync.detect(filtered_chunk, min_peak=5.0)
             
             if start_idx == -1:
                 continue # Try next polarity or fail
                 
             # Found Preamble
             preamble_len = len(self.sync.generate_preamble())
             gap_len = int(0.02 * self.fs) # Must match Transmitter gap
             
             # Sync Jitter loop
             offsets = [0, -1, 1, -2, 2, -3, 3, -4, 4]
             
             logger.debug(f"Sync Locked ({polarity}) at {start_idx}. Exploring offsets...")
             
             for offset in offsets:
                 try:
                     packet_start = start_idx + preamble_len + gap_len + offset
                     
                     if packet_start < 0: continue
                     if packet_start >= len(filtered_chunk):
                         continue
                     
                     raw_signal = filtered_chunk[packet_start:]
                     
                     # Demodulate
                     all_bits = self.ofdm.demodulate(raw_signal)
                     
                     # Discard Warm Up Symbol
                     if len(all_bits) > self.ofdm.bits_per_symbol:
                         bits = all_bits[self.ofdm.bits_per_symbol:]
                     else:
                         bits = all_bits # Should not happen if long enough
                          
                     decoded_bytes = self.ofdm.bytes_from_bits(bits)
                     payload = self.data_handler.decode(decoded_bytes)
                     
                     # Success!
                     logger.info(f"Rx Success ({polarity})! Len: {len(payload)}")
                     return payload, len(audio_chunk) # Consume
                     
                 except (ValueError, ReedSolomonError) as e:
                     if "too short" in str(e) or "Incomplete packet" in str(e):
                          return None, 0           
                     logger.debug(f"Receiver Failed: {e}")
                     return None, 500 # Fallback consumption
        return None, 0
