
import numpy as np
import time
from typing import Generator, Optional
from sonictag.deepseal import DeepSeal

class RealTimeInjector:
    def __init__(self, watermark_id: int, chip_rate: int = 256, sample_rate: int = 44100):
        # Use lower chip rate (256) for low latency (~0.5s duration)
        self.ds = DeepSeal(chip_rate=chip_rate, sample_rate=sample_rate)
        self.watermark_id = watermark_id
        
        # Calculate buffer size needed for one full watermark
        # Preamble (16) + Payload (70) = 86 bits
        self.bits_count = 86
        self.chunk_size = self.bits_count * chip_rate
        
        self.buffer = np.array([], dtype=np.float32)
        
    def process_stream(self, audio_stream: Generator[np.ndarray, None, None]) -> Generator[np.ndarray, None, None]:
        """
        Process an audio stream, injecting watermarks into buffered chunks.
        
        Args:
            audio_stream: Generator yielding numpy audio arrays (chunks).
            
        Yields:
            Watermarked audio chunks (may be different size than input, 
            but total length is preserved).
        """
        for chunk in audio_stream:
            self.buffer = np.concatenate([self.buffer, chunk])
            
            # While we have enough data for a watermark frame
            while len(self.buffer) >= self.chunk_size:
                # Extract a full frame
                frame = self.buffer[:self.chunk_size]
                self.buffer = self.buffer[self.chunk_size:]
                
                # Measure time
                t0 = time.perf_counter()
                
                # Inject
                # Ensure we handle short frames gracefully if any (though logic prevents it)
                watermarked_frame = self.ds.embed(frame, self.watermark_id)
                
                t1 = time.perf_counter()
                dt = t1 - t0
                
                # Verify real-time constraint
                # If processing time > playback time (frame_duration), we lag.
                frame_duration = len(frame) / self.ds.sample_rate
                # print(f"DEBUG: Proc Time: {dt:.4f}s / Duration: {frame_duration:.4f}s")
                
                yield watermarked_frame
        
        # Yield remaining buffer (unwatermarked)
        if len(self.buffer) > 0:
            yield self.buffer
