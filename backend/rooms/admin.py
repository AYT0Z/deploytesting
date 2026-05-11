from django.contrib import admin

from .models import Room


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ("slug", "title", "provider", "owner", "created_at")
    search_fields = ("slug", "title", "original_url")
