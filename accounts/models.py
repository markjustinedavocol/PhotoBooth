import secrets
from pathlib import Path

from django.conf import settings
from django.db import models


def avatar_upload_path(instance, filename):
    ext = Path(filename).suffix.lower() or ".jpg"
    return f"avatars/{instance.user_id}/{secrets.token_hex(6)}{ext}"


class Profile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile"
    )
    display_name = models.CharField(max_length=60, blank=True)
    avatar = models.ImageField(upload_to=avatar_upload_path, blank=True)
    timezone = models.CharField(max_length=64, default="UTC")
    city = models.CharField(max_length=80, blank=True)

    def __str__(self):
        return self.name

    @property
    def name(self):
        return self.display_name or self.user.username

    @property
    def initials(self):
        parts = self.name.split()
        letters = "".join(p[0] for p in parts[:2]) if parts else "?"
        return letters.upper()

    @property
    def place(self):
        """City if given, otherwise the city part of the timezone (e.g. 'Asia/Manila' -> 'Manila')."""
        if self.city:
            return self.city
        return self.timezone.split("/")[-1].replace("_", " ")
