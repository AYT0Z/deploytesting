import secrets
import string

from django.conf import settings
from django.db import models


def generate_room_slug():
    alphabet = string.ascii_lowercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(10))


class Room(models.Model):
    slug = models.SlugField(max_length=16, unique=True, db_index=True)
    title = models.CharField(max_length=255, blank=True)
    original_url = models.TextField()
    provider = models.CharField(max_length=32)
    embed_url = models.TextField(blank=True)
    stream_url = models.TextField(blank=True)
    extra = models.JSONField(default=dict, blank=True)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="owned_rooms",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        if not self.slug:
            for _ in range(20):
                candidate = generate_room_slug()
                if not Room.objects.filter(slug=candidate).exists():
                    self.slug = candidate
                    break
            else:
                self.slug = generate_room_slug() + secrets.token_hex(2)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.slug} ({self.provider})"
