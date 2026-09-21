from django.contrib import admin
from django.urls import include, path

from couples import views as couple_views

urlpatterns = [
    path("", couple_views.home, name="home"),
    path("admin/", admin.site.urls),
    path("accounts/", include("accounts.urls")),
    path("booth/", include("booth.urls")),
    path("gallery/", include("gallery.urls")),
    path("", include("couples.urls")),
]
