from django.urls import path

from .consumers import BoothConsumer

websocket_urlpatterns = [
    path("ws/booth/<uuid:session_id>/", BoothConsumer.as_asgi()),
]
