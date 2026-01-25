import asyncio
import io
import json
import logging
import queue
import threading

import numpy as np
import scipy.io.wavfile
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel

from sonictag.transceiver import SonicReceiver, SonicTransmitter

# Configure Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("SonicServer")

app = FastAPI(title="SonicTag API")

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global Objects
TARGET_FS = 48000
tx = SonicTransmitter(sample_rate=TARGET_FS)
rx = SonicReceiver(sample_rate=TARGET_FS)

BUFFER_DURATION = 1.0  # Optimized for fast 0.3s packets
BUFFER_SIZE = int(TARGET_FS * BUFFER_DURATION)

# --- Threaded DSP Architecture ---
audio_queue: queue.Queue = queue.Queue()
processing_active: bool = False
active_connections: list[WebSocket] = []

# We need a reference to the main event loop to dispatch async messages from the thread
main_loop = None


def audio_processing_worker():
    """
    Background thread that consumes audio chunks and runs the heavy DSP decoding.
    """
    global processing_active
    logger.info("DSP Worker Thread Started")

    # Local buffer for the worker
    worker_buffer = np.zeros(0, dtype=np.float32)

    while processing_active:
        try:
            # Get data from queue
            chunk = audio_queue.get(timeout=1.0)

            # RMS Level Check
            # rms = np.sqrt(np.mean(chunk**2))

            # Clip Detection
            max_amp = np.max(np.abs(chunk))
            if max_amp > 0.95:
                logger.warning(f"Input Clipping Detected! Max: {max_amp:.2f}")

            # Append to worker buffer (Thread Safe-ish, as only one producer/consumer)
            worker_buffer = np.concatenate((worker_buffer, chunk))

            # Sliding Window Management
            if len(worker_buffer) > BUFFER_SIZE:
                worker_buffer = worker_buffer[-BUFFER_SIZE:]

            # Attempt Decode
            try:
                # Heavy Blocking Call
                # Now returns (payload, consumed_samples)
                decoded_payload, consumed = rx.decode_frame(worker_buffer)

                # Correctly advance buffer
                if consumed > 0:
                    worker_buffer = worker_buffer[consumed:]

                if decoded_payload:
                    message = json.loads(decoded_payload.decode("utf-8"))
                    logger.info(f"Rx Success! Decoded: {message}")

                    # Broadcast back to WebSockets
                    if main_loop and main_loop.is_running():
                        asyncio.run_coroutine_threadsafe(broadcast_message(message), main_loop)

            except Exception:
                logger.debug("Decode failed")

            audio_queue.task_done()

        except queue.Empty:
            continue
        except Exception as e:
            logger.error(f"DSP Worker Error: {e}")


async def broadcast_message(data: dict):
    """
    Helper to send message to all connected clients.
    """
    to_remove = []
    for ws in list(active_connections):
        try:
            await ws.send_json({"type": "message", "data": data})
        except Exception:
            to_remove.append(ws)

    for ws in to_remove:
        if ws in active_connections:
            active_connections.remove(ws)


@app.on_event("startup")
async def startup_event():
    global processing_active, main_loop
    main_loop = asyncio.get_running_loop()
    processing_active = True
    t = threading.Thread(target=audio_processing_worker, daemon=True)
    t.start()


@app.on_event("shutdown")
def shutdown_event():
    global processing_active
    processing_active = False


# --- API Endpoints ---


class TransmitRequest(BaseModel):
    payload: dict


@app.post("/api/transmit")
async def transmit(request: TransmitRequest):
    """
    Encodes JSON payload and returns a WAV file.
    """
    try:
        data_bytes = json.dumps(request.payload).encode("utf-8")

        # Generator signal (float32, +/- 1.0)
        signal = tx.create_audio_frame(data_bytes)

        # Convert to 16-bit PCM for WAV compatibility
        signal_int16 = (signal * 32767).astype(np.int16)

        # Write to BytesIO
        wav_buffer = io.BytesIO()
        scipy.io.wavfile.write(wav_buffer, TARGET_FS, signal_int16)
        wav_buffer.seek(0)

        return Response(content=wav_buffer.read(), media_type="audio/wav")

    except Exception as e:
        logger.error(f"Transmit failed: {e}")
        return {"status": "error", "message": str(e)}


@app.websocket("/ws/receive")
async def receive_socket(websocket: WebSocket):
    """
    Receives raw float32 audio chunks from client.
    Handles text config messages and binary audio.
    """
    await websocket.accept()
    logger.info("Client connected to Receiver Socket")
    active_connections.append(websocket)

    client_sr = TARGET_FS  # Default assumption

    try:
        while True:
            # We need to handle both Text (JSON Config) and Binary (Audio)
            # receive() auto-detects
            message = await websocket.receive()

            if "text" in message:
                try:
                    data = json.loads(message["text"])
                    if data.get("type") == "config":
                        client_sr = data.get("sampleRate", TARGET_FS)

                        # ADAPTIVE RATE SWITCH
                        # If the client is running at a different rate (e.g. 44100 vs 48000),
                        # we switch the backend to match. This avoids resampling artifacts.
                        # CAUTION: This affects all connected clients (Single User assumption).
                        global rx, tx
                        if client_sr != rx.fs:
                            logger.warning(f"Switching Backend Sample Rate to {client_sr} Hz")
                            # Re-init Transceiver
                            rx = SonicReceiver(sample_rate=client_sr)
                            tx = SonicTransmitter(sample_rate=client_sr)
                            # Note: BUFFER_SIZE not updated dynamically, but it's large enough (48k)

                except Exception as e:
                    logger.error(f"Config Parse Error: {e}")

            elif "bytes" in message:
                data = message["bytes"]

                # Convert to numpy
                block = np.frombuffer(data, dtype=np.float32)

                # Send to Processing Queue (Non-blocking)
                # No Resampling! We trust the Adaptive Switch.
                audio_queue.put(block)

    except WebSocketDisconnect:
        logger.info("Client disconnected")
        if websocket in active_connections:
            active_connections.remove(websocket)
    except RuntimeError as e:
        if 'Cannot call "receive" once a disconnect message has been received' in str(e):
            logger.info("Client disconnected (RuntimeError)")
            if websocket in active_connections:
                active_connections.remove(websocket)
        else:
            logger.error(f"WebSocket Runtime Error: {e}")
            if websocket in active_connections:
                active_connections.remove(websocket)
            raise e
    except Exception as e:
        logger.error(f"WebSocket Error: {e}")
        if websocket in active_connections:
            active_connections.remove(websocket)
