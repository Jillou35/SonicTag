
import numpy as np
import time
import sys
import os

sys.path.append(os.path.abspath("src"))
from sonictag.realtime import RealTimeInjector

def demo_realtime():
    print("Initializing Real-Time Injector (Chip Rate=256)...")
    injector = RealTimeInjector(watermark_id=123456, chip_rate=256) # 0.5s Latency
    
    # Simulate a stream of 10 seconds audio
    # Chunk size simulates network packets (e.g. 4096 samples ~ 92ms)
    total_duration = 10.0
    sample_rate = 44100
    chunk_size = 4096
    
    t = np.linspace(0, total_duration, int(total_duration * sample_rate))
    full_audio = 0.5 * np.sin(2 * np.pi * 440 * t)
    
    def stream_generator():
        cursor = 0
        while cursor < len(full_audio):
            yield full_audio[cursor:cursor+chunk_size]
            cursor += chunk_size
            # Simulate real-time arrival? No, we want to measure pure processing speed.
            
    print("Starting Stream Processing...")
    start_time = time.time()
    
    processed_audio = []
    
    frame_count = 0
    total_proc_time = 0
    total_audio_duration = 0
    
    for processed_chunk in injector.process_stream(stream_generator()):
        processed_audio.append(processed_chunk)
        frame_count += 1
        
        # Approximate check
        chunk_dur = len(processed_chunk) / sample_rate
        total_audio_duration += chunk_dur
        
    end_time = time.time()
    wall_time = end_time - start_time
    
    print(f"Total Audio Duration: {total_audio_duration:.2f}s")
    print(f"Total Wall Time (Processing): {wall_time:.4f}s")
    print(f"Real-Time Factor: {wall_time / total_audio_duration:.4f}x")
    
    if wall_time < total_audio_duration:
        print("SUCCESS: Processing is FASTER than Real-Time.")
    else:
        print("FAILURE: System is lagging.")

if __name__ == "__main__":
    demo_realtime()
