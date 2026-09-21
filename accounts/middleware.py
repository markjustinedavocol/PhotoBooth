from django.utils import timezone

from .utils import zone_for


class UserTimezoneMiddleware:
    """Show dates and times in the signed-in user's own timezone."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        profile = getattr(request.user, "profile", None) if request.user.is_authenticated else None
        if profile is not None:
            timezone.activate(zone_for(profile.timezone))
        else:
            timezone.deactivate()
        return self.get_response(request)
