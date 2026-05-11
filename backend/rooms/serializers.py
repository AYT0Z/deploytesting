from rest_framework import serializers

from .models import Room
from .utils import parse_video_url


class RoomSerializer(serializers.ModelSerializer):
    class Meta:
        model = Room
        fields = (
            "slug",
            "title",
            "owner_id",
            "original_url",
            "provider",
            "embed_url",
            "stream_url",
            "extra",
            "created_at",
        )
        read_only_fields = fields


class RoomCreateSerializer(serializers.ModelSerializer):
    video_url = serializers.CharField(write_only=True)
    slug = serializers.SlugField(read_only=True)
    original_url = serializers.CharField(read_only=True)
    provider = serializers.CharField(read_only=True)
    embed_url = serializers.CharField(read_only=True)
    stream_url = serializers.CharField(read_only=True)
    extra = serializers.JSONField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)

    class Meta:
        model = Room
        fields = (
            "title",
            "video_url",
            "slug",
            "owner_id",
            "original_url",
            "provider",
            "embed_url",
            "stream_url",
            "extra",
            "created_at",
        )

    def create(self, validated_data):
        raw = validated_data.pop("video_url")
        parsed = parse_video_url(raw)
        owner = self.context["request"].user
        return Room.objects.create(
            title=validated_data.get("title") or "",
            original_url=raw,
            owner=owner,
            **parsed,
        )
