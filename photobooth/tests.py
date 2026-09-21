import os
from io import BytesIO, StringIO
from unittest import mock

import cloudinary
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from PIL import Image

from .storage import PrivateCloudinaryStorage


class FakeResponse(BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class PrivateCloudinaryStorageTests(SimpleTestCase):
    def setUp(self):
        cloudinary.config(cloud_name="demo", api_key="123", api_secret="shh")
        self.storage = PrivateCloudinaryStorage(folder="miles-apart")

    @mock.patch("cloudinary.uploader.upload")
    def test_save_uploads_privately(self, upload):
        name = self.storage.save("strips/1/ab12-strip.png", ContentFile(b"PNGDATA"))
        self.assertEqual(name, "strips/1/ab12-strip.png")
        stream = upload.call_args.args[0]
        self.assertEqual(stream.getvalue(), b"PNGDATA")
        kwargs = upload.call_args.kwargs
        self.assertEqual(kwargs["public_id"], "miles-apart/strips/1/ab12-strip.png")
        self.assertEqual((kwargs["resource_type"], kwargs["type"]), ("raw", "authenticated"))

    def test_url_is_signed_and_not_public(self):
        url = self.storage.url("strips/1/ab12-strip.png")
        self.assertIn("/raw/authenticated/s--", url)
        self.assertTrue(url.startswith("https://res.cloudinary.com/demo/"))
        self.assertNotIn("shh", url)

    @mock.patch("urllib.request.urlopen", return_value=FakeResponse(b"PNGDATA"))
    def test_open_downloads_through_signed_url(self, urlopen):
        with self.storage.open("strips/1/ab12-strip.png") as fh:
            self.assertEqual(fh.read(), b"PNGDATA")
        self.assertIn("/raw/authenticated/s--", urlopen.call_args.args[0])

    @mock.patch("cloudinary.uploader.destroy")
    def test_delete(self, destroy):
        self.storage.delete("avatars/1/x.jpg")
        destroy.assert_called_once_with(
            "miles-apart/avatars/1/x.jpg", resource_type="raw", type="authenticated", invalidate=True
        )


class FakeCloudinary:
    """Dict-backed stand-in for Cloudinary's upload/destroy/delivery endpoints."""

    def __init__(self):
        self.files = {}

    def upload(self, stream, **kwargs):
        assert kwargs["type"] == "authenticated"
        self.files[kwargs["public_id"]] = stream.getvalue()
        return {"public_id": kwargs["public_id"]}

    def destroy(self, public_id, **kwargs):
        self.files.pop(public_id, None)

    def urlopen(self, url, timeout=None):
        import urllib.error

        public_id = url.split("/v1/", 1)[1]
        if public_id not in self.files:
            raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)
        return FakeResponse(self.files[public_id])


@override_settings(
    STORAGES={
        "default": {"BACKEND": "photobooth.storage.PrivateCloudinaryStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
)
class CloudinaryEndToEndTests(TestCase):
    """The real booth flow (upload frames -> render strip -> serve/delete) on Cloudinary storage."""

    def setUp(self):
        cloudinary.config(cloud_name="demo", api_key="123", api_secret="shh")
        self.fake = FakeCloudinary()
        for target, fn in (
            ("cloudinary.uploader.upload", self.fake.upload),
            ("cloudinary.uploader.destroy", self.fake.destroy),
            ("urllib.request.urlopen", self.fake.urlopen),
        ):
            patcher = mock.patch(target, side_effect=fn)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_shoot_to_strip_on_cloudinary(self):
        from booth.models import BoothSession
        from couples.models import Couple
        from gallery.models import PhotoStrip

        User = get_user_model()
        alex = User.objects.create_user("alex", "a@example.com", "pw-123456!")
        sam = User.objects.create_user("sam", "s@example.com", "pw-123456!")
        couple = Couple.objects.create(partner_a=alex, partner_b=sam)
        session = BoothSession.objects.create(
            couple=couple, started_by=alex, status=BoothSession.Status.CAPTURING
        )

        for user in (alex, sam):
            self.client.force_login(user)
            for i in range(4):
                buf = BytesIO()
                Image.new("RGB", (320, 240), (200, 90, 120)).save(buf, "JPEG")
                response = self.client.post(
                    reverse("booth:upload_frame", args=[session.pk]),
                    {"index": i, "image": SimpleUploadedFile("f.jpg", buf.getvalue(), "image/jpeg")},
                )
                self.assertEqual(response.status_code, 200)

        strip = PhotoStrip.objects.get()
        self.assertEqual(len(self.fake.files), 9)  # 8 frames + 1 strip
        self.assertTrue(all(k.startswith("miles-apart/") for k in self.fake.files))

        image = self.client.get(reverse("gallery:image", args=[strip.pk]))
        self.assertEqual(image["Content-Type"], "image/png")
        self.assertTrue(b"".join(image.streaming_content).startswith(b"\x89PNG"))

        self.client.post(reverse("gallery:delete", args=[strip.pk]))
        self.assertEqual(self.fake.files, {})


class EnsureSuperuserTests(TestCase):
    def test_creates_once_from_env(self):
        env = {"DJANGO_SUPERUSER_USERNAME": "boss", "DJANGO_SUPERUSER_PASSWORD": "a-long-pass-9"}
        with mock.patch.dict(os.environ, env):
            call_command("ensure_superuser", stdout=StringIO())
            out = StringIO()
            call_command("ensure_superuser", stdout=out)  # second deploy: no-op
        self.assertIn("already exists", out.getvalue())
        user = get_user_model().objects.get(username="boss")
        self.assertTrue(user.is_superuser and user.check_password("a-long-pass-9"))

    def test_skips_without_env(self):
        with mock.patch.dict(os.environ, {}):
            os.environ.pop("DJANGO_SUPERUSER_USERNAME", None)
            call_command("ensure_superuser", stdout=StringIO())
        self.assertFalse(get_user_model().objects.filter(is_superuser=True).exists())
