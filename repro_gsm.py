
import sys
import os
import numpy as np
import scipy.signal

sys.path.append(os.path.abspath("src"))
from sonictag.deepseal import DeepSeal
import sonictag.deepseal
print(f"DEBUG: DeepSeal File: {sonictag.deepseal.__file__}")

def repro_gsm():
    print("Repro GSM Start")
    ds = DeepSeal(telecom_mode=True, chip_rate=512)
    
    duration = 60000 
    t = np.linspace(0, duration/44100, duration)
    # 100Hz + 5000Hz + 1000Hz
    audio = 0.5 * np.sin(2 * np.pi * 100 * t) + 0.3 * np.sin(2 * np.pi * 5000 * t) + 0.3 * np.sin(2 * np.pi * 1000 * t)
    
    watermark_id = 456789
    print(f"Embedding ID: {watermark_id}")
    
    watermarked = ds.embed(audio, watermark_id)
    
    print("Simulating GSM Channel...")
    filtered = ds._apply_bandpass(watermarked)
    attenuated = filtered * 0.1
    
    print("Extracting...")
    print(f"DEBUG: extract_debug info: {ds.extract_debug.__code__}")
    print(f"DEBUG: extract_debug file: {ds.extract_debug.__code__.co_filename}")
    print(f"DEBUG: extract_debug line: {ds.extract_debug.__code__.co_firstlineno}")
    # extracted = ds.extract(attenuated)
    extracted = ds.extract_debug(attenuated)
    print(f"Extracted: {extracted}")
    
    if extracted == watermark_id:
        print("SUCCESS")
    else:
        print("FAILURE")
        # Detailed debug if failed
        # processed = ds._apply_bandpass(attenuated)
        # processed = ds._normalize_signal(processed)
        # 
        # preamble_len_chips = 16 * 512
        # full_pn = ds.generate_pn_sequence(preamble_len_chips + 70*512)
        # preamble_pn = full_pn[:preamble_len_chips]
        # exp_preamble = np.repeat(ds.preamble_bits, 512) * 2 - 1
        # ref = exp_preamble * preamble_pn
        # if ds.telecom_mode:
        #     ref = ds._apply_bandpass(ref)
        #     
        # search_win = processed[:min(len(processed), preamble_len_chips*2 + 44100*2)]
        # idx, val = ds._attempt_sync(search_win, ref)
        # print(f"DEBUG: Sync Peak: {val} at {idx}")

if __name__ == "__main__":
    repro_gsm()
