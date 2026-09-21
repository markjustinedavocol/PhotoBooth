import shutil
import tempfile
from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from booth.models import BoothSession, Frame
from booth.services import save_strip
from couples.models import Couple

from .models import PhotoStrip

User = get_user_model()
TEMP_MEDIA = tempfile.mkdtemp()


def jpeg():
    buf = BytesIO()
    Image.new("RGB", (320, 240), (90, 140, 200)).save(buf, "JPEG")
    return ContentFile(buf.getvalue(), name="f.jpg")


@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class GalleryTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEMP_MEDIA, ignore_errors=True)

    def setUp(self):
        self.alex = User.objects.create_user("alex", "a@example.com", "pw-123456!")
        self.sam = User.objects.create_user("sam", "s@example.com", "pw-123456!")
        self.eve = User.objects.create_user("eve", "e@example.com", "pw-123456!")
        self.couple = Couple.objects.create(partner_a=self.alex, partner_b=self.sam)
        session = BoothSession.objects.create(
            couple=self.couple, started_by=self.alex, status=BoothSession.Status.DONE
        )
        for user in (self.alex, self.sam):
            for i in range(4):
                Frame.objects.create(session=session, user=user, index=i, image=jpeg())
        self.strip = save_strip(session)

    def test_members_can_view_and_download(self):
        self.client.force_login(self.sam)
        self.assertContains(self.client.get(reverse("gallery:list")), "Untitled strip")
        self.assertEqual(self.client.get(reverse("gallery:detail", args=[self.strip.pk])).status_code, 200)
        image = self.client.get(reverse("gallery:image", args=[self.strip.pk]))
        self.assertEqual(image["Content-Type"], "image/png")
        download = self.client.get(reverse("gallery:download", args=[self.strip.pk]))
        self.assertIn("attachment", download["Content-Disposition"])

    def test_strangers_get_404(self):
        self.client.force_login(self.eve)
        for name in ("gallery:detail", "gallery:image", "gallery:download"):
            self.assertEqual(self.client.get(reverse(name, args=[self.strip.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse("gallery:delete", args=[self.strip.pk])).status_code, 404)

    def test_archived_couple_loses_access(self):
        self.couple.is_active = False
        self.couple.save()
        self.client.force_login(self.alex)
        self.assertEqual(self.client.get(reverse("gallery:image", args=[self.strip.pk])).status_code, 404)

    def test_favorite_toggle(self):
        self.client.force_login(self.alex)
        self.client.post(reverse("gallery:favorite", args=[self.strip.pk]))
        self.strip.refresh_from_db()
        self.assertTrue(self.strip.is_favorite)

    def test_favorite_ignores_offsite_next(self):
        self.client.force_login(self.alex)
        response = self.client.post(
            reverse("gallery:favorite", args=[self.strip.pk]), {"next": "https://evil.example/"}
        )
        self.assertEqual(response["Location"], reverse("gallery:detail", args=[self.strip.pk]))

    def test_caption_and_note_rerender(self):
        self.client.force_login(self.alex)
        old_image = self.strip.image.name
        self.client.post(
            reverse("gallery:detail", args=[self.strip.pk]),
            {"caption": "Us", "love_note": "miss you"},
        )
        self.strip.refresh_from_db()
        self.assertEqual((self.strip.caption, self.strip.love_note), ("Us", "miss you"))
        self.assertNotEqual(self.strip.image.name, old_image)

    def test_relayout(self):
        self.client.force_login(self.alex)
        self.client.post(reverse("gallery:relayout", args=[self.strip.pk]), {"layout": "grid"})
        self.strip.refresh_from_db()
        self.assertEqual(self.strip.layout, "grid")
        with self.strip.image.open("rb") as fh:
            width, height = Image.open(fh).size
        self.assertGreater(width, height)

    def test_delete_removes_strip_and_files(self):
        path = self.strip.image.path
        self.client.force_login(self.alex)
        self.client.post(reverse("gallery:delete", args=[self.strip.pk]))
        self.assertFalse(PhotoStrip.objects.exists())
        self.assertFalse(Frame.objects.exists())
        import os
        self.assertFalse(os.path.exists(path))
