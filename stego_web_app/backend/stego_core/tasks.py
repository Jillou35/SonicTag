import io
from pathlib import Path

import numpy as np
import soundfile as sf
from celery import shared_task
from django.core.files.base import ContentFile
from django.utils import timezone
from pydub import AudioSegment

# Import from the local library
from sonictag.steganography import SonicStegoDecoder, SonicStegoEncoder

from .models import AudioTask


@shared_task(bind=True)
def process_stego_task(self, task_id):
    try:
        # 1. Fetch Task
        task = AudioTask.objects.get(id=task_id)
        task.task_status = "PROCESSING"
        task.save()

        original_file_path = Path(task.original_file.path)

        # 2. Read Audio using Pydub
        audio = AudioSegment.from_file(original_file_path)
        samplerate = audio.frame_rate

        # Convert to numpy array and normalize to float32 [-1, 1]
        samples = np.array(audio.get_array_of_samples())

        if audio.sample_width == 2:
            audio_data = samples.astype(np.float32) / 32768.0
        elif audio.sample_width == 4:
            audio_data = samples.astype(np.float32) / 2147483648.0
        elif audio.sample_width == 1:
            audio_data = (samples.astype(np.float32) - 128.0) / 128.0
        else:
            max_val = float(2 ** (8 * audio.sample_width - 1))
            audio_data = samples.astype(np.float32) / max_val

        if audio.channels > 1:
            audio_data = audio_data.reshape((-1, audio.channels))

        if task.task_type == "ENCODE":
            # 3. Encode
            encoder = SonicStegoEncoder(sample_rate=samplerate)
            message = task.hidden_message
            stego_audio = encoder.encode(audio_data, message)

            # 4. Save Result (WAV)
            buffer = io.BytesIO()
            sf.write(buffer, stego_audio, samplerate, format="WAV")
            buffer.seek(0)

            new_filename = f"{original_file_path.stem}_stego.wav"
            task.processed_file.save(new_filename, ContentFile(buffer.read()), save=False)

        elif task.task_type == "DECODE":
            # 3. Decode
            decoder = SonicStegoDecoder(sample_rate=samplerate)
            decoded_message = decoder.decode(audio_data)

            # 4. Save Result (Message)
            task.hidden_message = decoded_message
            task.save(update_fields=["hidden_message"])

        # 5. Update Status
        task.task_status = "COMPLETED"
        task.completed_at = timezone.now()
        task.save()

        return f"Task {task_id} ({task.task_type}) completed successfully."

    except Exception as e:
        # Handle failures gracefully
        if "task" in locals():
            task.task_status = "ERROR"
            task.error_message = str(e)
            task.save()
        return f"Task failed: {str(e)}"
