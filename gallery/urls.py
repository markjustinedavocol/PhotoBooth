from django.urls import path

from . import views

app_name = "gallery"

urlpatterns = [
    path("", views.strip_list, name="list"),
    path("<int:pk>/", views.detail, name="detail"),
    path("<int:pk>/image.png", views.image, name="image"),
    path("<int:pk>/download/", views.download, name="download"),
    path("<int:pk>/favorite/", views.toggle_favorite, name="favorite"),
    path("<int:pk>/layout/", views.relayout, name="relayout"),
    path("<int:pk>/delete/", views.delete, name="delete"),
]
