from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from booth.models import BoothSession
from booth.services import save_strip

from .forms import StripNoteForm
from .models import PhotoStrip


def get_strip_for(user, pk):
    strip = get_object_or_404(
        PhotoStrip.objects.select_related(
            "couple__partner_a__profile", "couple__partner_b__profile", "session", "owner__profile"
        ),
        pk=pk,
    )
    if not strip.can_view(user):
        raise Http404
    return strip


@login_required
def strip_list(request):
    strips = PhotoStrip.objects.visible_to(request.user).select_related("session", "owner__profile")
    favorites_only = request.GET.get("fav") == "1"
    if favorites_only:
        strips = strips.filter(is_favorite=True)
    return render(
        request, "gallery/list.html", {"strips": strips, "favorites_only": favorites_only}
    )


@login_required
def detail(request, pk):
    strip = get_strip_for(request.user, pk)
    form = StripNoteForm(request.POST or None, instance=strip)
    if request.method == "POST" and form.is_valid():
        caption_changed = "caption" in form.changed_data
        strip = form.save()
        if caption_changed:
            save_strip(strip.session, caption=strip.caption)  # caption is printed on the strip
        messages.success(request, "Saved.")
        return redirect("gallery:detail", pk=strip.pk)
    other_layout = (
        BoothSession.Layout.GRID
        if strip.layout == BoothSession.Layout.STRIP
        else BoothSession.Layout.STRIP
    )
    return render(
        request,
        "gallery/detail.html",
        {
            "strip": strip,
            "form": form,
            "other_layout": other_layout,
            "other_layout_label": BoothSession.Layout(other_layout).label,
        },
    )


def _file_response(strip, *, download):
    try:
        fh = strip.image.open("rb")
    except FileNotFoundError:
        raise Http404
    filename = f"miles-apart-{strip.created_at:%Y-%m-%d}-{strip.pk}.png"
    return FileResponse(fh, as_attachment=download, filename=filename, content_type="image/png")


@login_required
def image(request, pk):
    response = _file_response(get_strip_for(request.user, pk), download=False)
    response["Cache-Control"] = "private, max-age=3600"
    return response


@login_required
def download(request, pk):
    return _file_response(get_strip_for(request.user, pk), download=True)


@login_required
@require_POST
def toggle_favorite(request, pk):
    strip = get_strip_for(request.user, pk)
    strip.is_favorite = not strip.is_favorite
    strip.save(update_fields=["is_favorite"])
    nxt = request.POST.get("next", "")
    if url_has_allowed_host_and_scheme(nxt, {request.get_host()}, request.is_secure()):
        return redirect(nxt)
    return redirect("gallery:detail", pk=strip.pk)


@login_required
@require_POST
def relayout(request, pk):
    strip = get_strip_for(request.user, pk)
    layout = request.POST.get("layout")
    if layout in BoothSession.Layout.values and layout != strip.layout:
        save_strip(strip.session, layout=layout)
        messages.success(request, f"Switched to the {BoothSession.Layout(layout).label.lower()}.")
    return redirect("gallery:detail", pk=strip.pk)


@login_required
@require_POST
def delete(request, pk):
    strip = get_strip_for(request.user, pk)
    strip.session.delete()  # cascades to the frames and the strip, and their files
    messages.info(request, "Strip deleted.")
    return redirect("gallery:list")
