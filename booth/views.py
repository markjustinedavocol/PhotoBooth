from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse
from django.middleware.csrf import get_token
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST
from PIL import Image, UnidentifiedImageError

from couples.models import Couple

from .forms import BoothSessionForm
from .models import BoothSession, Frame
from .services import finalize_session, notify

ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}
MAX_PIXELS = 4096 * 4096


def get_session_for(user, session_id):
    """Fetch a session, 404ing unless the user belongs to its (active) couple."""
    session = get_object_or_404(
        BoothSession.objects.select_related(
            "couple__partner_a__profile", "couple__partner_b__profile"
        ),
        pk=session_id,
    )
    if not session.couple.is_active or not session.couple.has_member(user):
        raise Http404
    return session


def _strip_url(session):
    strip = getattr(session, "strip", None)
    return reverse("gallery:detail", args=[strip.pk]) if strip else None


@login_required
def new_session(request):
    couple = Couple.for_user(request.user)
    if couple is None or not couple.is_paired:
        messages.info(request, "Pair with your partner first — the booth needs two.")
        return redirect("couples:pair")

    form = BoothSessionForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        # Only one open room per couple, so both partners land in the same place.
        BoothSession.objects.filter(couple=couple, status=BoothSession.Status.WAITING).update(
            status=BoothSession.Status.CANCELLED
        )
        session = form.save(commit=False)
        session.couple = couple
        session.started_by = request.user
        session.save()
        return redirect("booth:room", session_id=session.pk)
    return render(request, "booth/new.html", {"form": form})


@login_required
def room(request, session_id):
    session = get_session_for(request.user, session_id)
    if session.status == BoothSession.Status.DONE and _strip_url(session):
        return redirect(_strip_url(session))
    if session.status == BoothSession.Status.CANCELLED:
        messages.info(request, "That booth session was closed. Start a fresh one!")
        return redirect("couples:dashboard")

    couple = session.couple
    me = request.user
    partner = couple.partner_of(me)
    config = {
        "sessionId": str(session.pk),
        "userId": me.id,
        "partnerId": partner.id,
        "partnerName": partner.profile.name,
        "shots": session.shots,
        "status": session.status,
        "wsPath": f"/ws/booth/{session.pk}/",
        "uploadUrl": reverse("booth:upload_frame", args=[session.pk]),
        "statusUrl": reverse("booth:status", args=[session.pk]),
        "finishUrl": reverse("booth:finish", args=[session.pk]),
        "dashboardUrl": reverse("couples:dashboard"),
        "csrfToken": get_token(request),
    }
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
    partner = session.couple.partner_of(request.user)
    return JsonResponse(
        {
            "status": session.status,
            "strip_url": _strip_url(session),
            "my_frames": session.frames_by(request.user),
            "partner_frames": session.frames_by(partner),
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
