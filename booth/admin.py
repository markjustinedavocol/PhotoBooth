from django.contrib import admin

from .models import BoothSession, Frame


class FrameInline(admin.TabularInline):
    model = Frame
    extra = 0
    readonly_fields = ("user", "index", "image", "captured_at")


@admin.register(BoothSession)
class BoothSessionAdmin(admin.ModelAdmin):
    list_display = ("id", "couple", "status", "theme", "photo_filter", "layout", "created_at")
    list_filter = ("status", "theme", "photo_filter", "layout")
    raw_id_fields = ("couple", "started_by")
    inlines = [FrameInline]


@admin.register(Frame)
class FrameAdmin(admin.ModelAdmin):
    list_display = ("session", "user", "index", "captured_at")
    raw_id_fields = ("session", "user")
