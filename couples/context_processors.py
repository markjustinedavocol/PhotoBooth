from .models import Couple


def couple(request):
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return {}
    current = Couple.for_user(user)
    return {
        "current_couple": current,
        "current_partner": current.partner_of(user) if current else None,
    }
