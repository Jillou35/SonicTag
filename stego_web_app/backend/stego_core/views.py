from rest_framework import mixins, viewsets
from rest_framework.parsers import FormParser, MultiPartParser

from .models import AudioTask
from .serializers import AudioTaskSerializer


class AudioTaskViewSet(
    viewsets.GenericViewSet, mixins.CreateModelMixin, mixins.RetrieveModelMixin, mixins.ListModelMixin
):
    """
    API Endpoint for uploading audio tasks and tracking their status.
    POST /: Upload file + message -> Returns Task ID
    GET /{id}/: Check status (polling)
    """

    queryset = AudioTask.objects.all()
    serializer_class = AudioTaskSerializer
    parser_classes = (MultiPartParser, FormParser)
