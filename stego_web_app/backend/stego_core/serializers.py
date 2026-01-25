from rest_framework import serializers

from .models import AudioTask


class AudioTaskSerializer(serializers.ModelSerializer):
    class Meta:
        model = AudioTask
        fields = [
            "id",
            "original_file",
            "processed_file",
            "hidden_message",
            "task_type",
            "task_status",
            "error_message",
            "created_at",
            "completed_at",
        ]
        read_only_fields = ["id", "processed_file", "task_status", "error_message", "created_at", "completed_at"]

    def validate(self, data):
        """
        Check that hidden_message is present if task_type is ENCODE.
        """
        task_type = data.get("task_type", "ENCODE")
        if task_type == "ENCODE" and not data.get("hidden_message"):
            raise serializers.ValidationError({"hidden_message": "This field is required for encoding tasks."})
        return data
