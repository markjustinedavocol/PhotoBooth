import secrets

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone

# No 0/O/1/I so codes are easy to read out over a call.
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
CODE_LENGTH = 8


def generate_invite_code():
    while True:
        code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))
        if not Couple.objects.filter(invite_code=code).exists():
            return code


class Couple(models.Model):
    partner_a = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="couples_started"
    )
    partner_b = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="couples_joined",
        null=True,
        blank=True,
    )
    invite_code = models.CharField(max_length=12, unique=True, default=generate_invite_code)
    anniversary = models.DateField(null=True, blank=True)
    next_meetup = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    paired_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        b = self.partner_b.username if self.partner_b_id else "(waiting)"
        return f"{self.partner_a.username} & {b}"

    @classmethod
    def for_user(cls, user):
        """The user's current couple (paired or a pending invite), or None."""
        if not user.is_authenticated:
            return None
        return (
            cls.objects.filter(is_active=True)
            .filter(Q(partner_a=user) | Q(partner_b=user))
            .select_related("partner_a__profile", "partner_b__profile")
            .first()
        )

    @property
    def is_paired(self):
        return self.partner_b_id is not None

    def has_member(self, user):
        return user.id in (self.partner_a_id, self.partner_b_id)

    def partner_of(self, user):
        if user.id == self.partner_a_id:
            return self.partner_b
        if user.id == self.partner_b_id:
            return self.partner_a
        return None

    def days_together(self):
        if not self.anniversary:
            return None
        return (timezone.localdate() - self.anniversary).days

    def days_until_meetup(self):
        if not self.next_meetup:
            return None
        days = (self.next_meetup - timezone.localdate()).days
        return days if days >= 0 else None
