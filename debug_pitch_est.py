
import sys
import os
import numpy as np
import scipy.signal

sys.path.append(os.path.abspath("src"))
from sonictag.deepseal import DeepSeal

def debug_pitch():
    print("DEBUG: Pitch Estimation Start")
    ds = DeepSeal(chip_rate=512)
    
    # 1. Embed
    duration = 150000 
    audio = np.zeros(duration)
    # Add noise
    audio += np.random.normal(0, 0.01, duration)
    
    watermark_id = 112233
    watermarked = ds.embed(audio, watermark_id)
    
    factors = [0.98, 1.02]
    for speed_factor in factors:
        print(f"\n--- Testing Speed {speed_factor} ---")
        new_len = int(len(watermarked) / speed_factor)
        resampled_audio = scipy.signal.resample(watermarked, new_len)
        
        # Extract
        try:
            extracted = ds.extract(resampled_audio, speed_search=True)
            print(f"Extracted: {extracted}")
            if extracted == watermark_id:
                print("SUCCESS")
            else:
                print("FAILURE")
        except Exception as e:
            print(f"EXCEPTION: {e}")

if __name__ == "__main__":
    import sys
    sys.stderr.write("DEBUG START\n")
    debug_pitch()
