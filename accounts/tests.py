from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase
from django.urls import reverse

from couples.models import Couple

User = get_user_model()


class AccountTests(TestCase):
    def test_signup_creates_profile_with_timezone(self):
        response = self.client.post(
            reverse("accounts:signup"),
            {
                "username": "alex",
                "email": "alex@example.com",
                "display_name": "Alex",
                "timezone": "Asia/Manila",
                "password1": "a-long-pass-phrase-9",
                "password2": "a-long-pass-phrase-9",
            },
        )
        self.assertRedirects(response, reverse("couples:pair"))
        profile = User.objects.get(username="alex").profile
        self.assertEqual((profile.name, profile.timezone, profile.place), ("Alex", "Asia/Manila", "Manila"))

    def test_bogus_timezone_falls_back_to_utc(self):
        self.client.post(
            reverse("accounts:signup"),
            {
                "username": "sam", "email": "sam@example.com", "timezone": "Mars/Base",
                "password1": "a-long-pass-phrase-9", "password2": "a-long-pass-phrase-9",
            },
        )
        self.assertEqual(User.objects.get(username="sam").profile.timezone, "UTC")

    def test_password_reset_email(self):
        User.objects.create_user("alex", "alex@example.com", "pw-123456!")
        self.client.post(reverse("accounts:password_reset"), {"email": "alex@example.com"})
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("/accounts/reset/", mail.outbox[0].body)

    def test_avatar_private_to_couple(self):
        alex = User.objects.create_user("alex", "a@example.com", "pw-123456!")
        sam = User.objects.create_user("sam", "s@example.com", "pw-123456!")
        eve = User.objects.create_user("eve", "e@example.com", "pw-123456!")
        Couple.objects.create(partner_a=alex, partner_b=sam)
        self.client.force_login(eve)
        self.assertEqual(self.client.get(reverse("accounts:avatar", args=[alex.id])).status_code, 404)

    def test_pages_render(self):
        for name in ("home", "accounts:login", "accounts:signup", "accounts:password_reset"):
            self.assertEqual(self.client.get(reverse(name)).status_code, 200, name)
