from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.utils import clock, local_time
from booth.models import BoothSession
from gallery.models import PhotoStrip

from .forms import CoupleSettingsForm, JoinForm
from .models import Couple
from .services import PairingError, get_or_create_invite, join_couple


def home(request):
    if request.user.is_authenticated:
        return redirect("couples:dashboard")
    return render(request, "couples/home.html")


@login_required
def dashboard(request):
    couple = Couple.for_user(request.user)
    strips = PhotoStrip.objects.visible_to(request.user).select_related("session", "owner__profile")
    context = {
        "couple": couple,
        "recent_strips": strips[:6],
        "strip_count": strips.count(),
    }
    if couple and couple.is_paired:
        partner = couple.partner_of(request.user)
        context.update(
            partner=partner,
            my_clock=clock(local_time(request.user.profile)),
            partner_clock=clock(local_time(partner.profile)),
            active_session=BoothSession.objects.filter(
                couple=couple,
                mode=BoothSession.Mode.DUO,
                status__in=[BoothSession.Status.WAITING, BoothSession.Status.CAPTURING],
                created_at__gte=timezone.now() - timedelta(hours=3),
            ).first(),
        )
    return render(request, "couples/dashboard.html", context)


@login_required
def pair(request):
    couple = Couple.for_user(request.user)
    if couple and couple.is_paired:
        return redirect("couples:dashboard")

    join_form = JoinForm()
    if request.method == "POST":
        if request.POST.get("action") == "invite":
            get_or_create_invite(request.user)
            return redirect("couples:pair")
        join_form = JoinForm(request.POST)
        if join_form.is_valid():
            try:
                joined = join_couple(request.user, join_form.cleaned_data["code"])
            except PairingError as exc:
                join_form.add_error("code", str(exc))
            else:
                messages.success(request, f"You're paired with {joined.partner_a.profile.name}! ♥")
                return redirect("couples:dashboard")

    invite_url = (
        request.build_absolute_uri(reverse("couples:join", args=[couple.invite_code]))
        if couple
        else None
    )
    return render(
        request,
        "couples/pair.html",
        {"couple": couple, "join_form": join_form, "invite_url": invite_url},
    )


@login_required
def join_link(request, code):
    """Landing page for a shared invite link: confirm, then pair."""
    couple = Couple.objects.filter(invite_code=code.upper(), is_active=True).select_related(
        "partner_a__profile"
    ).first()
    if request.method == "POST":
        try:
            join_couple(request.user, code)
        except PairingError as exc:
            messages.error(request, str(exc))
            return redirect("couples:pair")
        messages.success(request, "You're paired! ♥ Time to take your first strip.")
        return redirect("couples:dashboard")
    return render(request, "couples/join.html", {"invite": couple, "code": code})


@login_required
def couple_settings(request):
    couple = Couple.for_user(request.user)
    if couple is None or not couple.is_paired:
        return redirect("couples:pair")
    form = CoupleSettingsForm(request.POST or None, instance=couple)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Dates saved.")
        return redirect("couples:dashboard")
    return render(request, "couples/settings.html", {"form": form, "couple": couple})


@login_required
@require_POST
def leave(request):
    couple = Couple.for_user(request.user)
    if couple is not None:
        couple.is_active = False
        couple.save(update_fields=["is_active"])
        messages.info(request, "You've unpaired. Your shared gallery is archived.")
    return redirect("couples:dashboard")
