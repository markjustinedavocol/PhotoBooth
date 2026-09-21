import secrets

from django.conf import settings
from django.db import models
from django.db.models import Q

from booth.models import BoothSession
from couples.models import Couple


def strip_upload_path(instance, filename):
    folder = instance.couple_id or f"solo-{instance.owner_id}"
    return f"strips/{folder}/{secrets.token_hex(4)}-{filename}"


class PhotoStripQuerySet(models.QuerySet):
    def visible_to(self, user):
        """The user's shared couple gallery plus any solo strips they took while unpaired."""
        visible = Q(owner=user, couple__isnull=True)
        couple = Couple.for_user(user)
        if couple is not None and couple.is_paired:
            visible |= Q(couple=couple)
        return self.filter(visible)


class PhotoStrip(models.Model):
    session = models.OneToOneField(BoothSession, on_delete=models.CASCADE, related_name="strip")
    # Shared with this couple; empty for a solo strip taken while unpaired.
    couple = models.ForeignKey(
        Couple, on_delete=models.CASCADE, related_name="strips", null=True, blank=True
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="photo_strips",
        null=True,
        help_text="Who started the session.",
    )
    image = models.ImageField(upload_to=strip_upload_path)
    layout = models.CharField(
        max_length=8, choices=BoothSession.Layout.choices, default=BoothSession.Layout.STRIP
    )
    caption = models.CharField(max_length=80, blank=True)
    love_note = models.TextField(blank=True, max_length=1000)
    is_favorite = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = PhotoStripQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.caption or f"Strip from {self.created_at:%Y-%m-%d}"

    def can_view(self, user):
        if self.couple_id is None:
            return user.id == self.owner_id
        return self.couple.is_active and self.couple.has_member(user)
