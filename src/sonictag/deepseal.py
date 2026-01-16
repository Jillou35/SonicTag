
import numpy as np
import scipy.signal
import scipy.ndimage
import hashlib
from typing import Tuple, Optional


from sonictag.fec import SystematicFEC

print("DEBUG: LOADED DEEPSEAL MODULE FROM SRC")

class DeepSeal:
    """
    Audio watermarking module using Direct Sequence Spread Spectrum (DSSS)
    and psychoacoustic masking for invisible and robust data embedding.
    Standardized with FEC (Hamming 7,4) and CRC-8.
    """

    def __init__(self, seed: int = None, key: str = None, chip_rate: int = 256, sample_rate: int = 44100, telecom_mode: bool = False):
        """
        Initialize the DeepSeal watermarker.

        Args:
            seed: Explicit seed (overrides key). Default None.
            key: Secret key string to derive seed. If None and seed is None, uses public default.
            chip_rate: Number of PN chips (samples) per data bit.
            sample_rate: Audio sampling rate.
            telecom_mode: IF True, applies band-pass filtering (400-3400Hz) for robustness against 
                          telephony systems and aggressive compression.
        """
        if seed is None:
            if key:
                # [Phase 8: Security] Derive seed from SHA-256 of key
                hash_bytes = hashlib.sha256(key.encode('utf-8')).digest()
                # Take first 4 bytes as int
                self.seed = int.from_bytes(hash_bytes[:4], 'big')
            else:
                self.seed = 42 # Public Default
        else:
            self.seed = seed
            
        self.chip_rate = chip_rate
        self.sample_rate = sample_rate
        self.telecom_mode = telecom_mode
        self.fec = SystematicFEC()
        
        # Preamble for synchronization (16 bits)
        # Using Barker Code 13 for optimal autocorrelation: + + + + + - - + + - + - +
        # Padded with 3 zeros to make 16 bits
        self.preamble_bits = np.array([1, 1, 1, 1, 1, 0, 0, 1, 1, 0, 1, 0, 1, 0, 0, 0], dtype=int)
        
        self.rng = np.random.RandomState(self.seed)

    def generate_pn_sequence(self, length: int) -> np.ndarray:
        """
        Generate a pseudo-random sequence (white noise) of +1 and -1.
        
        Args:
            length: Length of the sequence to generate.
            
        Returns:
            np.ndarray: Sequence of +1.0 and -1.0.
        """
        # Using a fixed separate state for generation to avoid side effects if this method is called multiple times
        # effectively, we want deterministic output for the same length and seed.
        local_rng = np.random.RandomState(self.seed)
        noise = local_rng.randint(0, 2, size=length) * 2 - 1  # 0->-1, 1->1
        return noise.astype(float)

    def _int_to_bits(self, val: int, num_bits: int) -> np.ndarray:
        """Convert an integer to a bit array."""
        return np.array([(val >> i) & 1 for i in range(num_bits - 1, -1, -1)], dtype=int)

    def _bits_to_int(self, bits: np.ndarray) -> int:
        """Convert a bit array to an integer."""
        val = 0
        for bit in bits:
            val = (val << 1) | int(bit > 0.5)
        return val

    def _compute_masking_threshold(self, audio: np.ndarray, window_size: int = 1024) -> np.ndarray:
        """
        Calculate the psychoacoustic masking threshold using RMS envelope.
        
        Args:
            audio: Input audio signal.
            window_size: Size of the window for RMS calculation.
            
        Returns:
            np.ndarray: Masking envelope same size as audio.
        """
        # Calculate RMS envelope
        # We handle this by squaring, smoothing with a window, and taking sqrt
        squared_audio = audio ** 2
        window = np.ones(window_size) / window_size
        # Use valid convolution and pad or same convolution
        envelope = np.sqrt(scipy.signal.convolve(squared_audio, window, mode='same'))
        
        # Avoid zeros
        envelope = np.maximum(envelope, 1e-9)
        
        # Threshold: -25dB below the signal energy
        # [Robustness] In Telecom Mode, we need more energy to survive the channel.
        # -15dB is louder but acceptable for "phone quality".
        threshold_db = -15.0 if self.telecom_mode else -25.0
        
        scale_factor = 10 ** (threshold_db / 20.0)
        
        return envelope * scale_factor

    def _apply_bandpass(self, audio: np.ndarray) -> np.ndarray:
        """Apply 500Hz - 3000Hz bandpass filter for GSM/AMR robustness."""
        low_cut = 500.0
        high_cut = 3000.0
        nyquist = 0.5 * self.sample_rate
        low = low_cut / nyquist
        high = high_cut / nyquist
        
        # 2nd order Butterworth bandpass
        b, a = scipy.signal.butter(2, [low, high], btype='band')
        return scipy.signal.lfilter(b, a, audio)
    
    def _normalize_signal(self, audio: np.ndarray) -> np.ndarray:
        """
        Normalize signal to zero mean and unit variance (Z-score).
        Crucial for robustness against operator AGC.
        """
        if len(audio) == 0: return audio
        std_val = np.std(audio)
        if std_val < 1e-9: return audio - np.mean(audio)
        return (audio - np.mean(audio)) / std_val

    def _shape_spectrum(self, noise: np.ndarray, audio: np.ndarray) -> np.ndarray:
        """
        [Phase 6] Spectral Shaping (Frequency Domain Masking).
        Shapes the noise spectrum to match the audio spectrum (roughly),
        making it hide under the signal's frequency peaks.
        """
        if len(noise) != len(audio):
            return noise
            
        # Compute FFTs (use next power of 2 for speed)
        n_fft = 1 << (len(audio) - 1).bit_length()
        
        audio_fft = np.fft.rfft(audio, n=n_fft)
        noise_fft = np.fft.rfft(noise, n=n_fft)
        
        # Calculate Audio Magnitude
        audio_mag = np.abs(audio_fft)
        
        # Smooth the envelope (Simple Moving Average)
        window_size = n_fft // 64
        if window_size < 1: window_size = 1
        smoothed_mag = scipy.ndimage.uniform_filter1d(audio_mag, size=window_size)
        
        # Normalize
        peak = np.max(smoothed_mag)
        if peak > 1e-9:
            smoothed_mag /= peak
            
        # [Robustness Fix] Enforce a minimum floor (whiteness)
        # To prevent reducing DSSS processing gain to zero on tonal signals.
        # 0.2 means noise floor is at least 20% of peak spectrum.
        smoothed_mag = np.maximum(smoothed_mag, 0.2)
            
        # Apply shaping
        shaped_noise_fft = noise_fft * smoothed_mag
        
        # IFFT
        shaped_noise = np.fft.irfft(shaped_noise_fft, n=n_fft)
        
        return shaped_noise[:len(audio)]

    def embed(self, audio: np.ndarray, watermark_id: int) -> np.ndarray:
        """
        Inject a 32-bit ID into the audio signal.
        Uses FEC: Payload(32) + CRC(8) -> Hamming(70 encoded bits).
        
        Args:
            audio: Host audio signal (mono).
            watermark_id: 32-bit integer to embed.
            
        Returns:
            np.ndarray: Watermarked audio.
        """
        # [Phase 5: Protocol]
        if watermark_id >= 2**28:
            raise ValueError("Watermark ID exceeds 28 bits capacity (reserved for versioning).")
            
        version = 1
        final_id = (version << 28) | watermark_id
        
        # 1. Prepare Data
        # Raw Payload
        payload_bits = self._int_to_bits(final_id, 32)
        
        # CRC-8 (Calculated on the finalized ID)
        payload_bytes = int(final_id).to_bytes(4, byteorder='big')
        crc_val = self.fec.crc8(payload_bytes)
        crc_bits = self._int_to_bits(crc_val, 8)
        
        data_to_encode = np.concatenate([payload_bits, crc_bits]) # 40 bits
        
        # Hamming Encode
        encoded_bits = self.fec.encode_hamming(data_to_encode) # 70 bits
        
        # Interleaving
        interleaver_rng = np.random.RandomState(0xDEADBEEF)
        perm_indices = interleaver_rng.permutation(len(encoded_bits))
        interleaved_bits = encoded_bits[perm_indices]
        
        # [Phase 7] Preamble Sandwich: Start + Payload + Trailer (Start repeated)
        full_message_bits = np.concatenate([self.preamble_bits, interleaved_bits, self.preamble_bits])
        
        total_chips = len(full_message_bits) * self.chip_rate
        
        # 2. Generate PN Sequence 
        pn_sequence = self.generate_pn_sequence(total_chips)
        
        # 3. Spread Spectrum Modulation
        expanded_bits = np.repeat(full_message_bits, self.chip_rate)
        modulated_bits = expanded_bits * 2 - 1
        spread_signal = modulated_bits * pn_sequence
        
        if self.telecom_mode:
            spread_signal = self._apply_bandpass(spread_signal)
        
        # 4. Psychoacoustic Masking
        if len(audio) < len(spread_signal):
             raise ValueError(f"Audio file is too short. Needed: {len(spread_signal)}, Got: {len(audio)}")

        # [Phase 6] Frequency Domain Masking (Spectral Shaping)
        # Shape the spread signal to match the audio's spectral envelope
        shaped_signal = self._shape_spectrum(spread_signal, audio[:len(spread_signal)])
        
        # Normalize shaped signal energy to avoid volume drop
        std_shaped = np.std(shaped_signal)
        if std_shaped > 1e-9:
             shaped_signal /= std_shaped
             
        masking_envelope = self._compute_masking_threshold(audio[:len(spread_signal)])
        weighted_watermark = shaped_signal * masking_envelope
        
        # 5. Injection
        watermarked_audio = audio.copy()
        watermarked_audio[:len(spread_signal)] += weighted_watermark
        
        return watermarked_audio

    def _attempt_sync(self, audio_chunk: np.ndarray, reference_preamble: np.ndarray) -> Tuple[int, float]:
        """
        Attempt to synchronize with the given audio chunk.
        
        Returns:
            Tuple[int, float]: (best_shift_index, signed_peak_value)
        """
        # Cross-correlate
        correlation = scipy.signal.correlate(
            audio_chunk, 
            reference_preamble, 
            mode='valid'
        )
        peak_idx = np.argmax(np.abs(correlation))
        # Return SIGNED value to detect polarity inversion
        peak_val = correlation[peak_idx]
        return peak_idx, peak_val

    def extract(self, audio: np.ndarray, speed_search: bool = False, fine_search_step: float = 0.00005, fine_search_range: float = 0.009) -> Optional[int]:
        """
        Extract the 32-bit ID from the watermarked audio.
        Verifies CRC and corrects errors.
        """
        # 0. Pre-processing
        if self.telecom_mode:
            processed_audio = self._apply_bandpass(audio)
            processed_audio = self._normalize_signal(processed_audio)
        else:
            processed_audio = scipy.signal.lfilter([1, -0.95], [1], audio)
        
        # 1. Synchronization Setup
        # Encoded length is 70 bits (Hamming 7,4 on 40 bits data)
        encoded_payload_len = 70
        preamble_len_chips = len(self.preamble_bits) * self.chip_rate
        full_pn_sequence = self.generate_pn_sequence(preamble_len_chips + encoded_payload_len * self.chip_rate)
        
        preamble_pn = full_pn_sequence[:preamble_len_chips]
        expanded_preamble = np.repeat(self.preamble_bits, self.chip_rate) * 2 - 1
        reference_preamble = expanded_preamble * preamble_pn
        
        if self.telecom_mode:
            reference_preamble = self._apply_bandpass(reference_preamble)
        else:
            # Apply same pre-emphasis to reference
            reference_preamble = scipy.signal.lfilter([1, -0.95], [1], reference_preamble)

        search_len = preamble_len_chips * 2 + 44100 * 2
        search_window = processed_audio[:min(len(processed_audio), search_len)]

        # 1a. Find Start Preamble
        start_idx, start_val = self._attempt_sync(search_window, reference_preamble)
        
        # 1b. Find End Preamble (Trailer) to estimate Speed
        # Nominal distance between Start and End Preamble starts
        # Structure: [Preamble (16)] [Payload (70)] [Trailer (16)]
        # Distance from Preamble Start to Trailer Start = (16 + 70) * chip_rate
        
        # Iterative Speed Correction (2 Passes)
        current_audio = processed_audio
        total_speed_adjustment = 1.0
        
        final_audio = current_audio
        final_start_index = start_idx
        polarity_sign = 1.0 if start_val > 0 else -1.0
        
        for pass_num in range(2): # 2 passes is usually enough
            # Search parameters
            if pass_num == 0:
                 # Pass 1: Use original start_idx and nominal distance
                 s_idx = start_idx
                 # Note: In Pass 0, current_audio is original processed_audio
            else:
                 # Pass 1+: Find Start again on the resampled audio
                 # Search around expected location (0? No, we mapped it)
                 # Actually, better to just search the whole window again or narrow window
                 # Let's search narrow window around mapped start
                 expected_start = int(start_idx * total_speed_adjustment)
                 radius = 2048
                 s_start = max(0, expected_start - radius)
                 s_end = min(len(current_audio), expected_start + radius + preamble_len_chips)
                 s_win = current_audio[s_start : s_end]
                 rel, val = self._attempt_sync(s_win, reference_preamble)
                 # Let's search narrow window around mapped start
                 expected_start = int(start_idx * total_speed_adjustment)
                 radius = 2048
                 s_start = max(0, expected_start - radius)
                 s_end = min(len(current_audio), expected_start + radius + preamble_len_chips)
                 s_win = current_audio[s_start : s_end]
                 rel, val = self._attempt_sync(s_win, reference_preamble)
                 s_idx = s_start + rel
                 
                 final_start_index = s_idx
                 polarity_sign = 1.0 if val > 0 else -1.0
            
            # [Optimize] Coarse/Fine Strategy
            # Pass 0: Use short reference (center 50%) to be robust against speed distortion
            # Pass 1+: Use full reference for precision
            search_ref = reference_preamble
            ref_offset = 0
            if pass_num == 0:
                mid = len(search_ref) // 2
                half_width = len(search_ref) // 4
                search_ref = reference_preamble[mid - half_width : mid + half_width]
                ref_offset = mid - half_width
            
            # Find Trailer
            nominal_dist = (16 + encoded_payload_len) * self.chip_rate
            expected_trailer = s_idx + nominal_dist
            
            # Pass 0: Wide search (10%). Pass 1: Narrow search (1%).
            radius_factor = 0.1 if pass_num == 0 else 0.01
            radius = int(nominal_dist * radius_factor)
            
            t_start = max(0, expected_trailer - radius)
            t_end = min(len(current_audio), expected_trailer + radius + preamble_len_chips)
            
            pass_speed = 1.0
            if t_end > t_start + len(search_ref): # check fit
                t_win = current_audio[t_start : t_end]
                rel, t_val = self._attempt_sync(t_win, search_ref)
                
                # Check peak
                if abs(t_val) > abs(start_val) * 0.1: # Threshold: lowered to 10%
                    # Correct for ref_offset since peak is relative to sliced ref start
                    # Actually _attempt_sync returns index of match start relative to chunk.
                    # If we matched the middle part, the 'start' of the trailer is earlier.
                    # True Trailer Start = found_idx - ref_offset
                    found_trailer_idx = t_start + rel - ref_offset
                    
                    actual_dist = found_trailer_idx - s_idx
                    pass_speed = nominal_dist / actual_dist
                    print(f"DEBUG: Pass {pass_num} Speed: {pass_speed:.5f}")
            
            if abs(pass_speed - 1.0) < 0.0001:
                # Converged
                break
                
            # Perform Resampling
            old_len = len(current_audio)
            new_len = int(old_len * pass_speed)
            x_old = np.linspace(0, 1, old_len)
            x_new = np.linspace(0, 1, new_len)
            current_audio = np.interp(x_new, x_old, current_audio)
            
            total_speed_adjustment *= pass_speed
            final_audio = current_audio
            
            # If Pass 0, update start_idx mapping for next pass?
            # Actually next pass finds new start.
            
        # Final Sync Check (already done in loop iteration or last step)
        # If loop finished, final_audio is valid. final_start_index is valid.
        
        # One last check on Start Sync to be sure
        # We need final_start_index to be precise.
        if True: # Always resync one last time or rely on loop
             pred_start = int(start_idx * total_speed_adjustment)
             radius = 1024
             s_start = max(0, pred_start - radius)
             s_end = min(len(final_audio), pred_start + radius + preamble_len_chips)
             s_win = final_audio[s_start : s_end]
             rel, val = self._attempt_sync(s_win, reference_preamble)
             final_start_index = s_start + rel
             polarity_sign = 1.0 if val > 0 else -1.0
            
        # 2. Demodulation
        payload_start_chip = len(self.preamble_bits) * self.chip_rate
        total_payload_chips = encoded_payload_len * self.chip_rate
        
        if final_start_index + payload_start_chip + total_payload_chips > len(final_audio):
             return None
        
        payload_audio = final_audio[final_start_index + payload_start_chip : final_start_index + payload_start_chip + total_payload_chips]
        payload_pn = full_pn_sequence[payload_start_chip : payload_start_chip + total_payload_chips]

        
        if self.telecom_mode:
            payload_pn = self._apply_bandpass(payload_pn)
        else:
             payload_pn = scipy.signal.lfilter([1, -0.95], [1], payload_pn)

        # Demodulate
        # Demodulate
        # Apply polarity correction
        demodulated_chips = payload_audio * payload_pn * polarity_sign
        
        raw_bits = []
        for i in range(encoded_payload_len):
            chunk = demodulated_chips[i * self.chip_rate : (i + 1) * self.chip_rate]
            bit_val = np.sum(chunk)
            raw_bits.append(1 if bit_val > 0 else 0)
            
        raw_bits = np.array(raw_bits, dtype=int)
        
        # 3. De-Interleave
        interleaver_rng = np.random.RandomState(0xDEADBEEF)
        perm_indices = interleaver_rng.permutation(len(raw_bits))
        # Inverse permutation
        inv_indices = np.argsort(perm_indices)
        deinterleaved_bits = raw_bits[inv_indices]
        
        # 4. Decode FEC
        decoded_bits = self.fec.decode_hamming(deinterleaved_bits) # Should return 40 bits
        
        if len(decoded_bits) != 40:
            return None # Should ensure FEC matches expected length
            
        payload_bits = decoded_bits[:32]
        crc_bits = decoded_bits[32:]
        
        extracted_id = self._bits_to_int(payload_bits)
        extracted_crc = self._bits_to_int(crc_bits)
        
        # 5. Verify CRC
        payload_bytes = int(extracted_id).to_bytes(4, byteorder='big')
        calc_crc = self.fec.crc8(payload_bytes)
        
        if calc_crc == extracted_crc:
            # [Phase 5: Protocol] Strip Version
            # Extracted ID is 32 bits. Top 4 are version.
            version = (extracted_id >> 28) & 0xF
            content_id = extracted_id & 0x0FFFFFFF
            
            # (Optional) Validate Version == 1?
            # For now just return content_id
            return content_id
        else:
            return None # Integrity Check Failed
