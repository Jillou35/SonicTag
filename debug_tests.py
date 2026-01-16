
import sys
import os
import numpy as np
import traceback

sys.path.append(os.path.abspath("src"))
from sonictag.deepseal import DeepSeal

def test_perfect():
    print("Test Perfect...")
    ds = DeepSeal(chip_rate=512) 
    duration = 60000 
    t = np.linspace(0, duration/44100, duration)
    # audio = 0.5 * np.sin(2 * np.pi * 1000 * t)
    audio = np.random.normal(0, 0.5, duration)
    
    watermark_id = 123456789
    
    watermarked_audio = ds.embed(audio, watermark_id)
    
    extracted_id = ds.extract(watermarked_audio)
    print(f"Extracted: {extracted_id}")
    assert extracted_id == watermark_id
    print("PASS")

def test_noise():
    print("Test Noise...")
    ds = DeepSeal(chip_rate=512)
    duration = 60000 
    t = np.linspace(0, duration/44100, duration)
    audio = 0.5 * np.sin(2 * np.pi * 440 * t)
    
    watermark_id = 12345678 
    
    watermarked_audio = ds.embed(audio, watermark_id)
    noisy_audio = watermarked_audio + np.random.normal(0, 0.05, duration)
    
    extracted_id = ds.extract(noisy_audio)
    print(f"Extracted: {extracted_id}")
    assert extracted_id == watermark_id
    print("PASS")

if __name__ == "__main__":
    try:
        test_perfect()
    except Exception:
        print("PERFECT FAILED")
    try:
        test_noise()
    except Exception:
        print("NOISE FAILED")
        traceback.print_exc()
