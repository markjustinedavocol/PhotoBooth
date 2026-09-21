from django.contrib import admin

from .models import Couple


@admin.register(Couple)
class CoupleAdmin(admin.ModelAdmin):
    list_display = ("__str__", "invite_code", "is_active", "anniversary", "next_meetup", "paired_at")
    list_filter = ("is_active",)
    search_fields = ("partner_a__username", "partner_b__username", "invite_code")
    raw_id_fields = ("partner_a", "partner_b")
