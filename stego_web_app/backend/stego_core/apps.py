from django.apps import AppConfig


class StegoCoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "stego_core"

    def ready(self):
        import stego_core.signals  # noqa: F401
