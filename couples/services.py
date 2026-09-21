from django.db import transaction
from django.utils import timezone

from .models import Couple


class PairingError(Exception):
    pass


def get_or_create_invite(user):
    """Return the user's current couple, creating a pending invite if they have none."""
    couple = Couple.for_user(user)
    if couple is None:
        couple = Couple.objects.create(partner_a=user)
    return couple


def join_couple(user, code):
    code = (code or "").strip().upper().replace(" ", "").replace("-", "")
    couple = Couple.objects.filter(invite_code=code, is_active=True).first()
    if couple is None:
        raise PairingError("That code doesn't match any open invite. Double-check it with your partner.")
    if couple.partner_a_id == user.id:
        raise PairingError("That's your own invite code — send it to your partner instead.")
    if couple.partner_b_id is not None:
        raise PairingError("That invite has already been used.")

    current = Couple.for_user(user)
    if current is not None and current.is_paired:
        raise PairingError("You're already paired. Leave your current pairing first in couple settings.")

    with transaction.atomic():
        if current is not None:
            # The joiner's own unused invite is no longer needed.
            current.delete()
        claimed = Couple.objects.filter(pk=couple.pk, partner_b__isnull=True).update(
            partner_b=user, paired_at=timezone.now()
        )
        if not claimed:
            raise PairingError("That invite has already been used.")
    couple.refresh_from_db()
    return couple
