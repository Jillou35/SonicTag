
import sys
import os
import numpy as np
import scipy.signal
sys.path.append(os.path.abspath("src"))

from sonictag.deepseal import DeepSeal

def flush_print(msg):
    print(msg)
    sys.stdout.flush()

def debug_speed_test_replication():
    ds = DeepSeal(chip_rate=512)
    
    duration = 60000
    audio = np.zeros(duration)
    watermark_id = 112233
    
    flush_print("Embedding...")
    watermarked = ds.embed(audio, watermark_id)
    
    # Simulate 2% speed-up (pitch shift + time compression)
    speed_factor = 1.02
    new_len = int(len(watermarked) / speed_factor)
    flush_print(f"Resampling to {new_len}...")
    resampled_audio = scipy.signal.resample(watermarked, new_len)
    
    # Try with speed search
    flush_print("Extracting with speed search...")
    extracted = ds.extract(resampled_audio, speed_search=True)
    
    flush_print(f"Extracted: {extracted} (Expected {watermark_id})")
    
    if extracted == watermark_id:
        flush_print("SUCCESS")
    else:
        flush_print("FAILURE")
        
        # Analyze why
        # Should have found 1.02 speed (factor ~ 0.98)
        # Check internal state via hacks or just assume it failed.

if __name__ == "__main__":
    debug_speed_test_replication()
