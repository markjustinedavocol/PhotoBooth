from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse
from django.middleware.csrf import get_token
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST
from PIL import Image, UnidentifiedImageError

from couples.models import Couple

from .consumers import COUNTDOWN_SECONDS, PAUSE_BETWEEN_SHOTS_MS
from .forms import BoothSessionForm
from .models import BoothSession, Frame
from .services import finalize_session, notify

ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}
MAX_PIXELS = 4096 * 4096


def get_session_for(user, session_id):
    """Fetch a session, 404ing unless the user may use it (see BoothSession.can_join)."""
    session = get_object_or_404(
        BoothSession.objects.select_related(
            "started_by__profile", "couple__partner_a__profile", "couple__partner_b__profile"
        ),
        pk=session_id,
    )
    if not session.can_join(user):
        raise Http404
    return session


def _strip_url(session):
    strip = getattr(session, "strip", None)
    return reverse("gallery:detail", args=[strip.pk]) if strip else None


@login_required
def new_session(request):
    couple = Couple.for_user(request.user)
    paired = couple is not None and couple.is_paired
    # ?mode=solo links (dashboard, nav) preselect the solo booth
    requested = request.GET.get("mode")
    initial = {"mode": requested} if requested in BoothSession.Mode.values else {}
    form = BoothSessionForm(request.POST or None, paired=paired, initial=initial)
    if request.method == "POST" and form.is_valid():
        session = form.save(commit=False)
        session.started_by = request.user
        # A solo strip made while paired lands in the shared gallery too.
        session.couple = couple if paired else None
        if not session.is_solo:
            # Only one open room per couple, so both partners land in the same place.
            BoothSession.objects.filter(
                couple=couple, mode=BoothSession.Mode.DUO, status=BoothSession.Status.WAITING
            ).update(status=BoothSession.Status.CANCELLED)
        session.save()
        return redirect("booth:room", session_id=session.pk)
    return render(request, "booth/new.html", {"form": form, "paired": paired})


def _common_config(request, session):
    return {
        "sessionId": str(session.pk),
        "shots": session.shots,
        "status": session.status,
        "uploadUrl": reverse("booth:upload_frame", args=[session.pk]),
        "statusUrl": reverse("booth:status", args=[session.pk]),
        "finishUrl": reverse("booth:finish", args=[session.pk]),
        "dashboardUrl": reverse("couples:dashboard"),
        "csrfToken": get_token(request),
    }


@login_required
def room(request, session_id):
    session = get_session_for(request.user, session_id)
    if session.status == BoothSession.Status.DONE and _strip_url(session):
        return redirect(_strip_url(session))
    if session.status == BoothSession.Status.CANCELLED:
        messages.info(request, "That booth session was closed. Start a fresh one!")
        return redirect("couples:dashboard")

    config = _common_config(request, session)
    if session.is_solo:
        config["startUrl"] = reverse("booth:start_solo", args=[session.pk])
        return render(request, "booth/solo.html", {"session": session, "config": config})

    couple = session.couple
    me = request.user
    partner = couple.partner_of(me)
    config.update(
        userId=me.id,
        partnerId=partner.id,
        partnerName=partner.profile.name,
        wsPath=f"/ws/booth/{session.pk}/",
    )
    return render(
        request,
        "booth/room.html",
        {
            "session": session,
            "partner": partner,
            "me_left": couple.partner_a_id == me.id,
            "config": config,
        },
    )


@login_required
@require_POST
def start_solo(request, session_id):
    """Solo sessions have no partner to sync with, so the start is a plain request."""
    session = get_session_for(request.user, session_id)
    if not session.is_solo:
        raise Http404
    claimed = BoothSession.objects.filter(
        pk=session.pk, status=BoothSession.Status.WAITING
    ).update(status=BoothSession.Status.CAPTURING, captured_at=timezone.now())
    if not claimed:
        return JsonResponse({"error": "This shoot has already started."}, status=409)
    return JsonResponse(
        {"shots": session.shots, "seconds": COUNTDOWN_SECONDS, "pause": PAUSE_BETWEEN_SHOTS_MS}
    )


@login_required
@require_POST
def upload_frame(request, session_id):
    session = get_session_for(request.user, session_id)
    if session.status != BoothSession.Status.CAPTURING:
        return JsonResponse({"error": "This session isn't taking photos right now."}, status=409)

    try:
        index = int(request.POST.get("index", ""))
    except ValueError:
        index = -1
    if not 0 <= index < session.shots:
        return JsonResponse({"error": "Invalid frame index."}, status=400)

    upload = request.FILES.get("image")
    if upload is None:
        return JsonResponse({"error": "No image received."}, status=400)
    if upload.size > settings.MAX_FRAME_UPLOAD_SIZE:
        return JsonResponse({"error": "Image is too large."}, status=413)
    try:
        with Image.open(upload) as probe:
            fmt, (w, h) = probe.format, probe.size
            probe.verify()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        return JsonResponse({"error": "That file isn't a valid image."}, status=400)
    if fmt not in ALLOWED_FORMATS or w * h > MAX_PIXELS:
        return JsonResponse({"error": "Unsupported image."}, status=400)
    upload.seek(0)

    for old in Frame.objects.filter(session=session, user=request.user, index=index):
        old.delete()  # retries replace the earlier upload (signal removes the file)
    Frame.objects.create(session=session, user=request.user, index=index, image=upload)

    strip = finalize_session(session)
    return JsonResponse(
        {
            "ok": True,
            "strip_url": reverse("gallery:detail", args=[strip.pk]) if strip else None,
        }
    )


@login_required
@require_GET
def session_status(request, session_id):
    session = get_session_for(request.user, session_id)
    partner = None if session.is_solo else session.couple.partner_of(request.user)
    return JsonResponse(
        {
            "status": session.status,
            "strip_url": _strip_url(session),
            "my_frames": session.frames_by(request.user),
            "partner_frames": session.frames_by(partner) if partner else None,
            "shots": session.shots,
        }
    )


@login_required
@require_POST
def finish(request, session_id):
    """Build the strip now, using placeholders for any frames that never arrived."""
    session = get_session_for(request.user, session_id)
    if session.status == BoothSession.Status.CAPTURING:
        if not session.frames.exists():
            return JsonResponse({"error": "No photos were taken yet."}, status=409)
        finalize_session(session, force=True)
        session.refresh_from_db()
    url = _strip_url(session)
    if url is None:
        return JsonResponse({"error": "The strip isn't ready yet — try again in a moment."}, status=409)
    return JsonResponse({"ok": True, "strip_url": url})


@login_required
@require_POST
def cancel(request, session_id):
    session = get_session_for(request.user, session_id)
    updated = BoothSession.objects.filter(
        pk=session.pk,
        status__in=[BoothSession.Status.WAITING, BoothSession.Status.CAPTURING],
    ).update(status=BoothSession.Status.CANCELLED)
    if updated:
        notify(session, {"type": "cancelled", "by": request.user.profile.name})
        messages.info(request, "Booth session closed.")
    return redirect("couples:dashboard")
