import numpy as np
import pytest

from sonictag.transceiver import SonicReceiver, SonicTransmitter


@pytest.fixture
def transceiver():
    tx = SonicTransmitter(sample_rate=48000)
    rx = SonicReceiver(sample_rate=48000)
    return tx, rx


def test_clean_loopback(transceiver):
    tx, rx = transceiver
    payload = b'{"command": "unlock", "id": 123}'

    # Create Frame
    audio_frame = tx.create_audio_frame(payload)

    # Pad with silence (simulating latency/buffers)
    padded_frame = np.concatenate([np.zeros(1000), audio_frame, np.zeros(1000)])

    # Decode
    decoded_payload, samples_consumed = rx.decode_frame(padded_frame)

    # Decode result is JSON-serialized bytes in current impl?
    # Let's check debug_loopback.py logic: it expected `decoded` directly.
    # Looking at main.py: decoded_payload, consumed = rx.decode_frame(worker_buffer)
    # The payload is bytes.

    # Important: decode_frame returns (payload_bytes, consumed_count)
    # If payload is None, it failed.

    assert decoded_payload is not None, "Failed to decode frame"
    assert decoded_payload == payload


def test_noisy_loopback(transceiver):
    tx, rx = transceiver
    payload = b"Noise Resistance Check"
    audio_frame = tx.create_audio_frame(payload)

    # Add Gaussian Noise (sigma=0.1 is significant noise)
    noise = np.random.normal(0, 0.1, len(audio_frame))
    noisy_frame = audio_frame + noise

    # Pad
    final_signal = np.concatenate([np.zeros(2000), noisy_frame, np.zeros(2000)])

    decoded_payload, samples_consumed = rx.decode_frame(final_signal)

    assert decoded_payload is not None, "Failed to decode noisy frame"
    assert decoded_payload == payload
