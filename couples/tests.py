from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Couple
from .services import PairingError, get_or_create_invite, join_couple

User = get_user_model()


class PairingTests(TestCase):
    def setUp(self):
        self.alex = User.objects.create_user("alex", "alex@example.com", "pw-123456!")
        self.sam = User.objects.create_user("sam", "sam@example.com", "pw-123456!")
        self.kai = User.objects.create_user("kai", "kai@example.com", "pw-123456!")

    def test_invite_is_reused(self):
        first = get_or_create_invite(self.alex)
        self.assertEqual(first, get_or_create_invite(self.alex))
        self.assertFalse(first.is_paired)

    def test_join_with_code(self):
        invite = get_or_create_invite(self.alex)
        couple = join_couple(self.sam, invite.invite_code.lower())
        self.assertTrue(couple.is_paired)
        self.assertEqual(couple.partner_of(self.sam), self.alex)
        self.assertEqual(Couple.for_user(self.alex), Couple.for_user(self.sam))

    def test_cannot_join_own_code(self):
        invite = get_or_create_invite(self.alex)
        with self.assertRaises(PairingError):
            join_couple(self.alex, invite.invite_code)

    def test_code_cannot_be_used_twice(self):
        invite = get_or_create_invite(self.alex)
        join_couple(self.sam, invite.invite_code)
        with self.assertRaises(PairingError):
            join_couple(self.kai, invite.invite_code)

    def test_paired_user_cannot_join_another(self):
        join_couple(self.sam, get_or_create_invite(self.alex).invite_code)
        other = get_or_create_invite(self.kai)
        with self.assertRaises(PairingError):
            join_couple(self.sam, other.invite_code)

    def test_joiners_own_pending_invite_is_removed(self):
        mine = get_or_create_invite(self.sam)
        join_couple(self.sam, get_or_create_invite(self.alex).invite_code)
        self.assertFalse(Couple.objects.filter(pk=mine.pk).exists())

    def test_bad_code(self):
        with self.assertRaises(PairingError):
            join_couple(self.sam, "NOPE1234")

    def test_pair_view_flow(self):
        self.client.force_login(self.alex)
        self.client.post(reverse("couples:pair"), {"action": "invite"})
        code = Couple.for_user(self.alex).invite_code

        self.client.force_login(self.sam)
        response = self.client.post(reverse("couples:join", args=[code]))
        self.assertRedirects(response, reverse("couples:dashboard"))
        self.assertTrue(Couple.for_user(self.sam).is_paired)

        dashboard = self.client.get(reverse("couples:dashboard"))
        self.assertContains(dashboard, "Add your anniversary")
        self.assertContains(dashboard, "Start a booth session")

    def test_leave(self):
        join_couple(self.sam, get_or_create_invite(self.alex).invite_code)
        self.client.force_login(self.sam)
        self.client.post(reverse("couples:leave"))
        self.assertIsNone(Couple.for_user(self.alex))
