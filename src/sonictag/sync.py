import numpy as np
from scipy import signal
from .logger import logger

class SonicSync:
    """
    Handles synchronization preamble generation and detection.
    Uses a linear chirp for robust detection against noise and multipath.
    """
    def __init__(self, sample_rate: int = 48000, start_freq: int = 18500, end_freq: int = 19500, duration: float = 0.01):
        self.fs = sample_rate
        self.start_freq = start_freq
        self.end_freq = end_freq
        self.duration = duration
        
        # Generate the reference chirp
        t = np.linspace(0, self.duration, int(self.fs * self.duration), endpoint=False)
        self.preamble = signal.chirp(t, f0=self.start_freq, f1=self.end_freq, t1=self.duration, method='linear')
        
        # Normalize preamble
        self.preamble /= np.max(np.abs(self.preamble))
        
        # Apply Window to prevent clicks at start/end of preamble
        # Tukey window with alpha=0.1 (10% taper)
        window = signal.windows.tukey(len(self.preamble), alpha=0.1)
        self.preamble *= window
        
        # Pre-compute time-reversed preamble for convolution (correlation)
        # Correlation is Convolution with time-reversed signal.
        self.matched_filter = self.preamble[::-1]
        
        # Calculate theoretical max peak (Autocorrelation at 0 lag)
        # This is strictly sum(sample^2) if using direct correlation
        self.max_peak = np.sum(self.preamble ** 2)

    def generate_preamble(self) -> np.ndarray:
        return self.preamble

    def detect(self, audio_chunk: np.ndarray, min_peak: float = 4.0, min_snr: float = 3.0) -> int:
        """
        Finds the sample index where the preamble STARTS.
        Returns start index of preamble, or -1 if not found.
        param min_peak: Absolute threshold (for compatibility/strong signals)
        param min_snr: Signal-to-Noise ratio threshold (Peak / Median)
        """
        if len(audio_chunk) < len(self.preamble):
            return -1

        # Cross Correlate
        # mode='valid' means the output consists only of those elements that do not rely on zero-padding.
        # Length of result = len(audio_chunk) - len(preamble) + 1
        # Index i corresponds to alignment of preamble starting at audio_chunk[i]
        corr = signal.correlate(audio_chunk, self.preamble, mode='valid')
        corr_mag = np.abs(corr)
        
        # Find max peak
        peak_idx = np.argmax(corr_mag)
        peak_val = corr_mag[peak_idx]
        
        # Calculate SNR (Emergence)
        # Use 33th percentile as noise floor to ignore multipath/echo clutter
        noise_floor = np.percentile(corr_mag, 33)
        if noise_floor == 0: noise_floor = 1e-9
        
        snr = peak_val / noise_floor
        
        # Calculate Percentage (Quality) - mostly for debug
        quality = (peak_val / self.max_peak) * 100 if hasattr(self, 'max_peak') else 0
        
        # Debug: Log peak to see signal quality
        if quality > 2.0: # Log if > 2% signal strength
             logger.debug(f"Sync Check | Peak: {peak_val:.2f} | SNR: {snr:.1f} | Thr: P>{min_peak} or S>{min_snr}")
        
        # Detection Logic: Combined Absolute OR Relative (Emergence)
        is_found = False
        
        # 1. Absolute Threshold (Strong signal)
        if peak_val > min_peak:
            is_found = True
            
        # 2. Emergence Threshold (Weak signal but clear above noise)
        # Ensure we have at least SOME absolute signal (0.3) to avoid silence/rounding errors triggering
        elif snr > min_snr and peak_val > 0.3:
             is_found = True
        
        if is_found:
            logger.debug(f"Sync FOUND | Peak: {peak_val:.2f} ({quality:.1f}%) | SNR: {snr:.1f} at idx {peak_idx}")
            return peak_idx
            
        return -1
