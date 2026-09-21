from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme

from couples.models import Couple

from .forms import AccountForm, ProfileForm, SignupForm
from .models import Profile


def _safe_next(request):
    nxt = request.POST.get("next") or request.GET.get("next") or ""
    if url_has_allowed_host_and_scheme(nxt, {request.get_host()}, request.is_secure()):
        return nxt
    return ""


def signup(request):
    if request.user.is_authenticated:
        return redirect("couples:dashboard")
    form = SignupForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        messages.success(request, f"Welcome, {user.profile.name}! Now pair up with your person.")
        return redirect(_safe_next(request) or "couples:pair")
    return render(request, "accounts/signup.html", {"form": form, "next": _safe_next(request)})


@login_required
def profile(request):
    profile = request.user.profile
    account_form = AccountForm(request.POST or None, instance=request.user, prefix="account")
    profile_form = ProfileForm(
        request.POST or None, request.FILES or None, instance=profile, prefix="profile"
    )
    if request.method == "POST" and account_form.is_valid() and profile_form.is_valid():
        old_avatar = profile.avatar.name if profile.avatar else ""
        account_form.save()
        saved = profile_form.save()
        if old_avatar and old_avatar != (saved.avatar.name or ""):
            saved.avatar.storage.delete(old_avatar)
        messages.success(request, "Profile saved.")
        return redirect("accounts:profile")
    return render(
        request,
        "accounts/profile.html",
        {"account_form": account_form, "profile_form": profile_form},
    )


@login_required
def avatar(request, user_id):
    """Avatars are only visible to their owner and that person's partner."""
    if user_id != request.user.id:
        couple = Couple.for_user(request.user)
        partner = couple.partner_of(request.user) if couple else None
        if partner is None or partner.id != user_id:
            raise Http404
    profile = get_object_or_404(Profile, user_id=user_id)
    if not profile.avatar:
        raise Http404
    try:
        return FileResponse(profile.avatar.open("rb"))
    except FileNotFoundError:
        raise Http404
