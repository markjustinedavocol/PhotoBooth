from django.contrib import admin

from .models import PhotoStrip


@admin.register(PhotoStrip)
class PhotoStripAdmin(admin.ModelAdmin):
    list_display = ("__str__", "couple", "layout", "is_favorite", "created_at")
    list_filter = ("layout", "is_favorite")
    search_fields = ("caption", "love_note")
    raw_id_fields = ("session", "couple")
