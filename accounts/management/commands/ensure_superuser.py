"""Create the admin account from environment variables, if it doesn't exist yet.

Runs on every deploy (see build.sh). Render's free plan has no shell for
`createsuperuser`, so set these on the service instead:

    DJANGO_SUPERUSER_USERNAME, DJANGO_SUPERUSER_PASSWORD, DJANGO_SUPERUSER_EMAIL (optional)

An existing account is left alone, so changing the password in the admin sticks.
"""
import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Create a superuser from DJANGO_SUPERUSER_* env vars if it doesn't already exist."

    def handle(self, *args, **options):
        username = os.environ.get("DJANGO_SUPERUSER_USERNAME", "").strip()
        password = os.environ.get("DJANGO_SUPERUSER_PASSWORD", "")
        email = os.environ.get("DJANGO_SUPERUSER_EMAIL", "").strip()
        if not username or not password:
            self.stdout.write("ensure_superuser: DJANGO_SUPERUSER_USERNAME/PASSWORD not set, skipping.")
            return

        User = get_user_model()
        if User.objects.filter(username=username).exists():
            self.stdout.write(f"ensure_superuser: '{username}' already exists.")
            return
        User.objects.create_superuser(username=username, email=email, password=password)
        self.stdout.write(self.style.SUCCESS(f"ensure_superuser: created '{username}'."))
