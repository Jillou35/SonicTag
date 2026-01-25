from pathlib import Path

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import AudioTask
from .tasks import process_stego_task


@receiver(post_save, sender=AudioTask)
def trigger_audio_processing(sender, instance, created, **kwargs):
    """
    Trigger the Celery task when a new AudioTask is created.
    """
    if created:
        process_stego_task.delay(instance.id)


@receiver(post_delete, sender=AudioTask)
def cleanup_audio_files(sender, instance, **kwargs):
    """
    Delete the actual files from the filesystem when the AudioTask is deleted.
    """
    if instance.original_file:
        original_file_path = Path(instance.original_file.path)
        if original_file_path.is_file():
            original_file_path.unlink()

    if instance.processed_file:
        processed_file_path = Path(instance.processed_file.path)
        if processed_file_path.is_file():
            processed_file_path.unlink()
