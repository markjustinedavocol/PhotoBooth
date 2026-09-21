import logging
from io import BytesIO

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.core.files.base import ContentFile
from django.urls import reverse
from PIL import Image

from accounts.utils import clock, local_time, pretty_date

from .models import BoothSession
from .strips import compose

logger = logging.getLogger(__name__)


def notify(session, payload):
    """Push a message to everyone connected to the session's booth room."""
    layer = get_channel_layer()
    if layer is None:
        return
    try:
        async_to_sync(layer.group_send)(
            session.group_name, {"type": "broadcast", "payload": payload}
        )
    except Exception:  # a dead Redis shouldn't break the HTTP request
        logger.exception("Could not notify booth %s", session.pk)


def _open_frame(frame):
    if frame is None:
        return None
    try:
        with frame.image.open("rb") as fh:
            img = Image.open(fh)
            img.load()
            return img
    except (OSError, ValueError):
        logger.warning("Frame %s could not be read", frame.pk)
        return None


def render_session(session, *, layout, caption):
    people = session.photographers()  # partner_a on the left for couples
    frames = {(f.user_id, f.index): f for f in session.frames.all()}
    shots = [
        tuple(_open_frame(frames.get((person.id, i))) for person in people)
        for i in range(session.shots)
    ]
    when = session.captured_at or session.created_at
    times = [local_time(person.profile, when) for person in people]
    return compose(
        shots,
        theme=session.theme,
        photo_filter=session.photo_filter,
        layout=layout,
        caption=caption,
        names=tuple(person.profile.name for person in people),
        date_text=pretty_date(times[0]),
        clocks=tuple((person.profile.place, clock(t)) for person, t in zip(people, times)),
        seed=session.pk.int % 10_000,
    )


def save_strip(session, *, layout=None, caption=None):
    """Create or re-render the PhotoStrip for a session."""
    from gallery.models import PhotoStrip

    strip = PhotoStrip.objects.filter(session=session).first()
    if layout is None:
        layout = strip.layout if strip else session.layout
    if caption is None:
        caption = strip.caption if strip else session.caption

    image = render_session(session, layout=layout, caption=caption)
    buffer = BytesIO()
    image.save(buffer, "PNG")

    old_name = strip.image.name if strip and strip.image else ""
    if strip is None:
        strip = PhotoStrip(session=session, couple=session.couple, owner=session.started_by)
    strip.layout = layout
    strip.caption = caption
    strip.image.save(f"{layout}.png", ContentFile(buffer.getvalue()), save=False)
    strip.save()
    if old_name and old_name != strip.image.name:
        strip.image.storage.delete(old_name)
    return strip


def finalize_session(session, *, force=False):
    """Turn a finished shoot into a strip.

    Normally runs once both partners have uploaded every frame. With force=True
    (the "finish anyway" button) missing frames become placeholders.
    Safe to call concurrently: only the caller that flips CAPTURING -> PROCESSING renders.
    """
    if not force and not session.has_all_frames():
        return None
    claimed = BoothSession.objects.filter(
        pk=session.pk, status=BoothSession.Status.CAPTURING
    ).update(status=BoothSession.Status.PROCESSING)
    if not claimed:
        return None
    try:
        strip = save_strip(session)
    except Exception:
        BoothSession.objects.filter(pk=session.pk).update(status=BoothSession.Status.CAPTURING)
        raise
    BoothSession.objects.filter(pk=session.pk).update(status=BoothSession.Status.DONE)
    session.status = BoothSession.Status.DONE
    notify(session, {"type": "strip_ready", "url": reverse("gallery:detail", args=[strip.pk])})
    return strip
