from django.urls import path

from . import views

app_name = "booth"

urlpatterns = [
    path("new/", views.new_session, name="new"),
    path("<uuid:session_id>/", views.room, name="room"),
    path("<uuid:session_id>/start/", views.start_solo, name="start_solo"),
    path("<uuid:session_id>/frames/", views.upload_frame, name="upload_frame"),
    path("<uuid:session_id>/status/", views.session_status, name="status"),
    path("<uuid:session_id>/finish/", views.finish, name="finish"),
    path("<uuid:session_id>/cancel/", views.cancel, name="cancel"),
]
