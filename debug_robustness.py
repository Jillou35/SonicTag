
import sys
import os
import numpy as np
import scipy.signal
sys.path.append(os.path.abspath("src"))

from sonictag.deepseal import DeepSeal

def flush_print(msg):
    print(msg)
    sys.stdout.flush()

def debug_telecom_failure():
    ds = DeepSeal(telecom_mode=True, chip_rate=512)
    
    duration = 50000
    t = np.linspace(0, duration/44100, duration)
    # Tonal noise at 100Hz and 10kHz + Random noise
    audio = 0.5 * np.sin(2 * np.pi * 100 * t) + 0.3 * np.random.normal(0, 0.1, duration)
    
    watermark_id = 998877
    
    flush_print("Embedding (Telecom Mode)...")
    watermarked = ds.embed(audio, watermark_id)
    
    flush_print("Extracting...")
    extracted = ds.extract(watermarked)
    
    flush_print(f"Extracted: {extracted}")
    
    if extracted == watermark_id:
        flush_print("SUCCESS in Debug Script!")
    else:
        flush_print("FAILURE in Debug Script.")
        _analyze_telecom_failure(ds, watermarked)

def _analyze_telecom_failure(ds, watermarked):
    # Check signal after filter
    processed = ds._apply_bandpass(watermarked)
    rms_proc = np.sqrt(np.mean(processed**2))
    flush_print(f"RMS of Processed Audio: {rms_proc}")
    
    # Check Sync
    preamble_len_chips = len(ds.preamble_bits) * ds.chip_rate
    full_pn = ds.generate_pn_sequence(preamble_len_chips + 32 * ds.chip_rate)
    preamble_pn = full_pn[:preamble_len_chips]
    expanded_preamble = np.repeat(ds.preamble_bits, ds.chip_rate) * 2 - 1
    reference = expanded_preamble * preamble_pn
    
    corr = scipy.signal.correlate(processed[:min(len(processed), 100000)], reference, mode='valid')
    peak_idx = np.argmax(np.abs(corr))
    peak_val = np.abs(corr[peak_idx])
    mean_val = np.mean(np.abs(corr))
    
    flush_print(f"Sync Peak Index: {peak_idx}")
    flush_print(f"Sync Peak Value: {peak_val}")
    flush_print(f"Mean Correlation: {mean_val}")
    flush_print(f"SNR (Peak/Mean): {peak_val/mean_val}")
    
    # Try correlating with FILTERED reference?
    # If we filter the reference to match the band, maybe it helps?
    ref_filtered = ds._apply_bandpass(reference)
    corr2 = scipy.signal.correlate(processed[:min(len(processed), 100000)], ref_filtered, mode='valid')
    peak2 = np.max(np.abs(corr2))
    mean2 = np.mean(np.abs(corr2))
    flush_print(f"Filtered Ref SNR: {peak2/mean2}")

if __name__ == "__main__":
    debug_telecom_failure()
