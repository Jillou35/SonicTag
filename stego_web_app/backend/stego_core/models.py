import uuid

from django.db import models


class AudioTask(models.Model):
    STATUS_CHOICES = [
        ("PENDING", "Pending"),
        ("PROCESSING", "Processing"),
        ("COMPLETED", "Completed"),
        ("ERROR", "Error"),
    ]

    TASK_TYPE_CHOICES = [
        ("ENCODE", "Encode"),
        ("DECODE", "Decode"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    original_file = models.FileField(upload_to="input_audio/%Y/%m/%d/")
    processed_file = models.FileField(upload_to="output_audio/%Y/%m/%d/", null=True, blank=True)
    hidden_message = models.TextField(null=True, blank=True)
    task_type = models.CharField(max_length=10, choices=TASK_TYPE_CHOICES, default="ENCODE")
    task_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="PENDING")
    error_message = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Task {self.id} - {self.task_status}"
