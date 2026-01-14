import numpy as np


class SonicOFDM:
    """
    OFDM Modulator and Demodulator data into audio signals.
    Target band: 17.5kHz - 20.5kHz.
    """

    def __init__(
        self,
        sample_rate: int = 48000,
        n_fft: int = 1024,
        cp_len: int = 384,
        start_freq: int = 17500,
        end_freq: int = 20500,
        bin_step: int = 2,
    ):
        self.fs = sample_rate
        self.n_fft = n_fft
        self.cp_len = cp_len
        self.start_freq = start_freq
        self.end_freq = end_freq
        self.bin_step = bin_step

        # Calculate active bins
        self.bin_resolution = self.fs / self.n_fft
        self.start_bin = int(self.start_freq / self.bin_resolution)
        self.end_bin = int(self.end_freq / self.bin_resolution)

        # Ensure we don't exceed Nyquist
        max_bin = self.n_fft // 2
        self.end_bin = min(self.end_bin, max_bin - 1)

        self.active_bins = np.arange(self.start_bin, self.end_bin + 1, self.bin_step)
        self.n_subcarriers = len(self.active_bins)

        # For DBPSK, 1 bit per subcarrier
        self.bits_per_symbol = self.n_subcarriers

    def modulate(self, bits: np.ndarray) -> np.ndarray:
        """
        Modulate bits into an OFDM time-domain signal using Differential BPSK (DBPSK).
        Robust against phase rotation and channel distortion.
        """
        # 1. Pad bits
        n_bits = len(bits)
        padding = (self.bits_per_symbol - (n_bits % self.bits_per_symbol)) % self.bits_per_symbol
        if padding > 0:
            bits = np.concatenate([bits, np.zeros(padding, dtype=int)])

        n_symbols = len(bits) // self.bits_per_symbol

        time_signal = []

        # 2. Reference Symbol
        # Active values state: init to 1.0 (complex)
        current_state = np.ones(self.n_subcarriers, dtype=complex)

        # Generate Reference Time Domain
        ref_freq_data = np.zeros(self.n_fft, dtype=complex)
        ref_freq_data[self.active_bins] = current_state
        # Conjugate symmetry for Real output
        for idx, bin_idx in enumerate(self.active_bins):
            ref_freq_data[self.n_fft - bin_idx] = np.conj(current_state[idx])

        ref_time = np.fft.ifft(ref_freq_data)
        ref_time = np.real(ref_time)
        # Add CP
        ref_with_cp = np.concatenate([ref_time[-self.cp_len :], ref_time])
        time_signal.append(ref_with_cp)

        # 3. Differential Modulation
        for i in range(n_symbols):
            chunk = bits[i * self.bits_per_symbol : (i + 1) * self.bits_per_symbol]

            # BPSK Mapping: 0 -> -1, 1 -> 1
            # Differential Encoding: NewState = OldState * Symbol
            # If bit 1 (1): New = Old * 1 = Old (No Change)
            # If bit 0 (-1): New = Old * -1 = -Old (Phase Flip)
            # This is standard differential encoding logic.

            data_symbols = 2 * chunk - 1  # Map 0,1 to -1,1

            # Update State
            current_state = current_state * data_symbols

            # Create Freq Data
            freq_data = np.zeros(self.n_fft, dtype=complex)
            freq_data[self.active_bins] = current_state

            # Hermitian Symmetry
            for idx, bin_idx in enumerate(self.active_bins):
                freq_data[self.n_fft - bin_idx] = np.conj(current_state[idx])

            # IFFT
            symbol_time = np.fft.ifft(freq_data)
            symbol_time = np.real(symbol_time)

            # Add CP
            with_cp = np.concatenate([symbol_time[-self.cp_len :], symbol_time])
            time_signal.append(with_cp)

        full_signal = np.concatenate(time_signal)

        # Normalize
        max_val = np.max(np.abs(full_signal))
        if max_val > 0:
            full_signal /= max_val

        return full_signal

    def demodulate(self, signal: np.ndarray) -> np.ndarray:
        """
        Demodulate DBPSK OFDM signal.
        """
        symbol_len = self.n_fft + self.cp_len
        n_symbols_total = len(signal) // symbol_len

        if n_symbols_total < 2:
            return np.array([], dtype=int)  # Need at least reference + 1 symbol

        all_bits = []

        # 1. Extract Reference Symbol
        # Skip CP
        ref_start = self.cp_len
        ref_end = symbol_len
        ref_chunk = signal[ref_start:ref_end]
        ref_fft = np.fft.fft(ref_chunk, n=self.n_fft)
        prev_response = ref_fft[self.active_bins]

        # 2. Loop Data Symbols
        # Start from index 1 (0 was reference)
        for i in range(1, n_symbols_total):
            start = i * symbol_len + self.cp_len
            end = (i + 1) * symbol_len
            chunk = signal[start:end]

            # FFT
            fft_data = np.fft.fft(chunk, n=self.n_fft)
            curr_response = fft_data[self.active_bins]

            # DBPSK Demodulation
            # diff = curr * conj(prev)
            # If phase didn't change (1): curr ~= prev => curr * conj(prev) ~= |prev|^2 (Real Positive)
            # If phase flipped (-1): curr ~= -prev => curr * conj(prev) ~= -|prev|^2 (Real Negative)

            diff = curr_response * np.conj(prev_response)

            # Bit Decision: Real > 0 -> 1, Real < 0 -> 0
            # (Recall mapping: 1->1, 0->-1)
            bits = (np.real(diff) > 0).astype(int)
            all_bits.append(bits)

            # Update reference
            prev_response = curr_response

        return np.concatenate(all_bits)

    def bits_from_bytes(self, payload: bytes) -> np.ndarray:
        """Helper to convert bytes to bit array"""
        # using numpy unpackbits, explicit big endian (MSB first)
        byte_array = np.frombuffer(payload, dtype=np.uint8)
        return np.unpackbits(byte_array, bitorder="big")

    def bytes_from_bits(self, bits: np.ndarray) -> bytes:
        """Helper to convert bit array to bytes"""
        return np.packbits(bits, bitorder="big").tobytes()
