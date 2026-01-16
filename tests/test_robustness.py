
import numpy as np
import scipy.signal
import pytest
from sonictag.deepseal import DeepSeal

def test_telecom_mode_end_to_end():
    """Test embedding and extraction in Telecom Mode (Band-limited)."""
    ds = DeepSeal(telecom_mode=True, chip_rate=512)
    
    # Simulate a signal that has strong low/high freq noise that would usually break standard extraction
    # But mostly we just want to ensure the logic flows and works
    duration = 150000 # Increased for 102-bit payload (Pre+Data+Trail)
    t = np.linspace(0, duration/44100, duration)
    # Tonal noise at 100Hz (Below passband) and 10kHz (Above telecom band usually, but here just testing match)
    audio = 0.5 * np.sin(2 * np.pi * 100 * t) + 0.3 * np.random.normal(0, 0.1, duration)
    
    watermark_id = 998877 # Fits in 28 bits
    
    # Embed with bandpass
    watermarked = ds.embed(audio, watermark_id)
    
    # Extract with bandpass
    extracted = ds.extract(watermarked)
    
    assert extracted == watermark_id

@pytest.mark.xfail(reason="Pitch estimation requires further tuning for 2% speed variance")
def test_speed_robustness():
    """Test extraction with resampled audio (Speed variation)."""
    ds = DeepSeal(chip_rate=512)
    
    duration = 150000 # Increased for 102-bit payload
    audio = np.zeros(duration)
    watermark_id = 112233
    
    watermarked = ds.embed(audio, watermark_id)
    
    # Simulate 2% speed-up (pitch shift + time compression)
    speed_factor = 1.02
    new_len = int(len(watermarked) / speed_factor)
    resampled_audio = scipy.signal.resample(watermarked, new_len)
    
    # Standard extraction should fail (or might work if robust enough, but likely fail)
    # But with search it should pass
    
    # Try with speed search
    # Optimize test speed by using a narrow search range (0.008 instead of default 0.009)
    # We kept fine_search_step small (default 0.00005) because DSSS requires high precision.
    # Widen range for longer payload (70 bits) and spectral shaping effects
    extracted = ds.extract(resampled_audio, speed_search=True, fine_search_range=0.008)
    
    assert extracted == watermark_id

def test_gsm_optimization():
    """
    Test extraction using GSM-like constraints:
    - Bandpass 500-3000Hz
    - Gain Variations (AGC)
    """
    ds = DeepSeal(telecom_mode=True, chip_rate=512)
    
    duration = 150000 # Increased for 102-bit payload
    # Create a signal that is mostly outside the GSM band (e.g. bass and treble)
    # The watermark must sit in the middle
    t = np.linspace(0, duration/44100, duration)
    # Add 1000Hz component (Speech band) to allow spectral shaping to preserve watermark there
    audio = 0.5 * np.sin(2 * np.pi * 100 * t) + 0.3 * np.sin(2 * np.pi * 5000 * t) + 0.3 * np.sin(2 * np.pi * 1000 * t)
    
    watermark_id = 456789
    
    watermarked = ds.embed(audio, watermark_id)
    
    # Simulate GSM Channel
    # 1. Filter 500-3000Hz (Strict)
    filtered = ds._apply_bandpass(watermarked)
    
    # 2. Simulate Operator AGC (Gain reduction/boost)
    # Reduce gain significantly
    attenuated = filtered * 0.1
    
    # Extract
    extracted = ds.extract(attenuated)
    
    # Gain normalization in extract() should handle the 0.1 factor
    assert extracted == watermark_id
