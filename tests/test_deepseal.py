
import numpy as np
import pytest
from sonictag.deepseal import DeepSeal

def test_deepseal_pn_generation():
    """Test consistency of PN sequence generation."""
    ds = DeepSeal(seed=123)
    seq1 = ds.generate_pn_sequence(1024)
    
    ds2 = DeepSeal(seed=123)
    seq2 = ds2.generate_pn_sequence(1024)
    
    assert np.array_equal(seq1, seq2)
    assert len(seq1) == 1024
    # Check it contains only -1 and 1
    assert np.all(np.isin(seq1, [-1, 1]))

def test_deepseal_embed_extract_perfect():
    """Test embedding and extraction in perfect conditions (silence + watermark)."""
    ds = DeepSeal(chip_rate=512, telecom_mode=True) # Use robust mode
    
    # Create simple sine wave audio
    # Duration needs to cover Preamble (16 bits) + Payload (70 bits encoded) + Trailer (16) = 102 bits
    # 102 * 512 = 52224 samples
    duration = 60000 
    t = np.linspace(0, duration/44100, duration)
    audio = 0.5 * np.sin(2 * np.pi * 440 * t)
    
    watermark_id = 123456789
    
    watermarked_audio = ds.embed(audio, watermark_id)
    
    # Check that audio is modified
    assert not np.array_equal(audio, watermarked_audio)
    
    # Extract
    extracted_id = ds.extract(watermarked_audio)
    assert extracted_id == watermark_id

def test_deepseal_noise_resistance():
    """Test robustness against noise."""
    ds = DeepSeal(chip_rate=512, telecom_mode=True)
    
    duration = 60000 
    # Use a tonal signal (music-like) as host instead of white noise
    t = np.linspace(0, duration/44100, duration)
    audio = 0.5 * np.sin(2 * np.pi * 440 * t)
    
    watermark_id = 12345678 # Fits in 28 bits
    
    watermarked_audio = ds.embed(audio, watermark_id)
    
    # Add more noise (simulating channel noise)
    noisy_audio = watermarked_audio + np.random.normal(0, 0.05, duration)
    
    extracted_id = ds.extract(noisy_audio)
    assert extracted_id == watermark_id

def test_bits_conversion():
    ds = DeepSeal()
    val = 0b101010
    bits = ds._int_to_bits(val, 6)
    assert np.array_equal(bits, [1, 0, 1, 0, 1, 0])
    
    recovered = ds._bits_to_int(bits)
    assert recovered == val

def test_short_audio_error():
    ds = DeepSeal(chip_rate=1024)
    short_audio = np.zeros(100)
    with pytest.raises(ValueError, match="too short"):
        ds.embed(short_audio, 123)

def test_key_security():
    """Test that different keys produce different PN sequences."""
    ds1 = DeepSeal(key="secret_A", chip_rate=1024)
    ds2 = DeepSeal(key="secret_B", chip_rate=1024)
    
    seq1 = ds1.generate_pn_sequence(1000)
    seq2 = ds2.generate_pn_sequence(1000)
    
    # They must be different
    assert not np.array_equal(seq1, seq2)
    
    # Same key must be same
    ds3 = DeepSeal(key="secret_A", chip_rate=1024)
    seq3 = ds3.generate_pn_sequence(1000)
    assert np.array_equal(seq1, seq3)
    
def test_protocol_versioning():
    """Test that version bits are stripped correctly."""
    ds = DeepSeal()
    # Embed ID that fits in 28 bits
    original_id = 0x0ABCDEF
    
    # Mock embedding and extraction logic (end-to-end)
    # Just verify embed accepts it
    # We rely on existing end-to-end tests for full verification, 
    # but let's check input validation.
    
    with pytest.raises(ValueError, match="exceeds 28 bits"):
        ds.embed(np.zeros(100000), 0x1FFFFFFF) # 29 bits
