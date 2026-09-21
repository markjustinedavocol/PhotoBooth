import secrets

from django.db import models

from booth.models import BoothSession
from couples.models import Couple


def strip_upload_path(instance, filename):
    return f"strips/{instance.couple_id}/{secrets.token_hex(4)}-{filename}"


class PhotoStrip(models.Model):
    session = models.OneToOneField(BoothSession, on_delete=models.CASCADE, related_name="strip")
    couple = models.ForeignKey(Couple, on_delete=models.CASCADE, related_name="strips")
    image = models.ImageField(upload_to=strip_upload_path)
    layout = models.CharField(
        max_length=8, choices=BoothSession.Layout.choices, default=BoothSession.Layout.STRIP
    )
    caption = models.CharField(max_length=80, blank=True)
    love_note = models.TextField(blank=True, max_length=1000)
    is_favorite = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.caption or f"Strip from {self.created_at:%Y-%m-%d}"
