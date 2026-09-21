from django.urls import path

from . import views

app_name = "couples"

urlpatterns = [
    path("dashboard/", views.dashboard, name="dashboard"),
    path("pair/", views.pair, name="pair"),
    path("pair/join/<str:code>/", views.join_link, name="join"),
    path("couple/settings/", views.couple_settings, name="settings"),
    path("couple/leave/", views.leave, name="leave"),
]
