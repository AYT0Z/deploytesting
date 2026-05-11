from rest_framework import mixins, permissions, viewsets
from rest_framework.exceptions import NotFound

from .models import Room
from .serializers import RoomCreateSerializer, RoomSerializer


class RoomViewSet(mixins.CreateModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    lookup_field = "slug"

    def get_queryset(self):
        return Room.objects.all()

    def get_serializer_class(self):
        if self.action == "create":
            return RoomCreateSerializer
        return RoomSerializer

    def get_permissions(self):
        if self.action == "retrieve":
            return [permissions.AllowAny()]
        return [permissions.IsAuthenticated()]

    def get_object(self):
        try:
            return super().get_object()
        except Room.DoesNotExist:
            raise NotFound()
