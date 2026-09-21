import secrets
import uuid

from django.conf import settings
from django.db import models

from couples.models import Couple

# CSS equivalents of the Pillow filters in booth/strips.py, used for the live preview.
FILTER_CSS = {
    "none": "none",
    "bw": "grayscale(1) contrast(1.05)",
    "sepia": "sepia(0.85) contrast(0.95)",
    "warm": "sepia(0.22) saturate(1.3) hue-rotate(-8deg) brightness(1.03)",
}


def frame_upload_path(instance, filename):
    return (
        f"frames/{instance.session_id}/"
        f"{instance.user_id}-{instance.index}-{secrets.token_hex(4)}.jpg"
    )


class BoothSession(models.Model):
    class Status(models.TextChoices):
        WAITING = "waiting", "Waiting for both partners"
        CAPTURING = "capturing", "Taking photos"
        PROCESSING = "processing", "Developing strip"
        DONE = "done", "Done"
        CANCELLED = "cancelled", "Cancelled"

    class Theme(models.TextChoices):
        CLASSIC = "classic", "Classic"
        POLAROID = "polaroid", "Polaroid"
        FILM = "film", "Film"
        PASTEL = "pastel", "Pastel Hearts"

    class Filter(models.TextChoices):
        NONE = "none", "Natural"
        BW = "bw", "Black & White"
        SEPIA = "sepia", "Sepia"
        WARM = "warm", "Warm"

    class Layout(models.TextChoices):
        STRIP = "strip", "Classic strip"
        GRID = "grid", "2×2 grid"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    couple = models.ForeignKey(Couple, on_delete=models.CASCADE, related_name="sessions")
    started_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.WAITING)
    theme = models.CharField(max_length=12, choices=Theme.choices, default=Theme.CLASSIC)
    photo_filter = models.CharField(max_length=12, choices=Filter.choices, default=Filter.NONE)
    layout = models.CharField(max_length=8, choices=Layout.choices, default=Layout.STRIP)
    caption = models.CharField(max_length=80, blank=True)
    shots = models.PositiveSmallIntegerField(default=4)
    created_at = models.DateTimeField(auto_now_add=True)
    captured_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Session {str(self.pk)[:8]} ({self.get_status_display()})"

    @property
    def group_name(self):
        return group_name_for(self.pk)

    @property
    def filter_css(self):
        return FILTER_CSS.get(self.photo_filter, "none")

    def frames_by(self, user):
        return self.frames.filter(user=user).count()

    def has_all_frames(self):
        couple = self.couple
        return all(
            self.frames_by(member) >= self.shots
            for member in (couple.partner_a, couple.partner_b)
            if member is not None
        )


def group_name_for(session_id):
    return f"booth-{session_id}"


class Frame(models.Model):
    session = models.ForeignKey(BoothSession, on_delete=models.CASCADE, related_name="frames")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    index = models.PositiveSmallIntegerField()
    image = models.ImageField(upload_to=frame_upload_path)
    captured_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["index"]
        constraints = [
            models.UniqueConstraint(fields=["session", "user", "index"], name="unique_frame_slot")
        ]

    def __str__(self):
        return f"Frame {self.index} by {self.user} in {self.session_id}"
