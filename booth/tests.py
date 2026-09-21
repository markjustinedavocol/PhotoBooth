import shutil
import tempfile
from io import BytesIO

from asgiref.sync import sync_to_async
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from PIL import Image

from couples.models import Couple
from gallery.models import PhotoStrip

from .models import BoothSession, Frame
from .routing import websocket_urlpatterns
from .services import finalize_session
from .strips import CELL_H, compose

User = get_user_model()
TEMP_MEDIA = tempfile.mkdtemp()


def jpeg(color=(200, 80, 120), size=(640, 480)):
    buf = BytesIO()
    Image.new("RGB", size, color).save(buf, "JPEG")
    return SimpleUploadedFile("frame.jpg", buf.getvalue(), content_type="image/jpeg")


def make_couple():
    a = User.objects.create_user("alex", "a@example.com", "pw-123456!")
    b = User.objects.create_user("sam", "s@example.com", "pw-123456!")
    a.profile.timezone, a.profile.city = "Asia/Manila", "Manila"
    a.profile.save()
    b.profile.timezone = "America/Toronto"
    b.profile.save()
    return Couple.objects.create(partner_a=a, partner_b=b), a, b


@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class BoothViewTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEMP_MEDIA, ignore_errors=True)

    def setUp(self):
        self.couple, self.alex, self.sam = make_couple()
        self.stranger = User.objects.create_user("eve", "e@example.com", "pw-123456!")
        self.session = BoothSession.objects.create(
            couple=self.couple, started_by=self.alex, status=BoothSession.Status.CAPTURING
        )

    def upload(self, user, index, file=None):
        self.client.force_login(user)
        return self.client.post(
            reverse("booth:upload_frame", args=[self.session.pk]),
            {"index": index, "image": file or jpeg()},
        )

    def test_new_session_requires_pairing(self):
        self.client.force_login(self.stranger)
        response = self.client.get(reverse("booth:new"))
        self.assertRedirects(response, reverse("couples:pair"))

    def test_create_session_and_open_room(self):
        self.client.force_login(self.alex)
        response = self.client.post(
            reverse("booth:new"),
            {"theme": "film", "photo_filter": "bw", "layout": "grid", "caption": "hi"},
        )
        session = BoothSession.objects.filter(status=BoothSession.Status.WAITING).get()
        self.assertRedirects(response, reverse("booth:room", args=[session.pk]))
        room = self.client.get(reverse("booth:room", args=[session.pk]))
        self.assertContains(room, "booth-config")

    def test_strangers_get_404(self):
        self.client.force_login(self.stranger)
        for name in ("booth:room", "booth:status"):
            self.assertEqual(self.client.get(reverse(name, args=[self.session.pk])).status_code, 404)
        self.assertEqual(self.upload(self.stranger, 0).status_code, 404)

    def test_anonymous_redirected_to_login(self):
        response = self.client.get(reverse("booth:room", args=[self.session.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response["Location"])

    def test_rejects_non_images_and_bad_index(self):
        fake = SimpleUploadedFile("x.jpg", b"not an image", content_type="image/jpeg")
        self.assertEqual(self.upload(self.alex, 0, fake).status_code, 400)
        self.assertEqual(self.upload(self.alex, 9).status_code, 400)

    def test_upload_rejected_when_not_capturing(self):
        self.session.status = BoothSession.Status.WAITING
        self.session.save()
        self.assertEqual(self.upload(self.alex, 0).status_code, 409)

    def test_strip_created_when_all_frames_arrive(self):
        for i in range(4):
            self.assertEqual(self.upload(self.alex, i).status_code, 200)
        for i in range(3):
            self.upload(self.sam, i)
        self.assertFalse(PhotoStrip.objects.exists())
        response = self.upload(self.sam, 3)
        strip = PhotoStrip.objects.get()
        self.assertEqual(response.json()["strip_url"], reverse("gallery:detail", args=[strip.pk]))
        self.session.refresh_from_db()
        self.assertEqual(self.session.status, BoothSession.Status.DONE)

    def test_retry_replaces_frame(self):
        self.upload(self.alex, 0)
        self.upload(self.alex, 0)
        self.assertEqual(Frame.objects.filter(user=self.alex, index=0).count(), 1)

    def test_finish_anyway_uses_placeholders(self):
        self.upload(self.alex, 0)
        self.client.force_login(self.sam)
        response = self.client.post(reverse("booth:finish", args=[self.session.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(PhotoStrip.objects.filter(session=self.session).exists())

    def test_finalize_runs_only_once(self):
        for user in (self.alex, self.sam):
            for i in range(4):
                Frame.objects.create(session=self.session, user=user, index=i, image=jpeg())
        self.assertIsNotNone(finalize_session(self.session))
        self.assertIsNone(finalize_session(self.session))
        self.assertEqual(PhotoStrip.objects.count(), 1)


class ComposeTests(TestCase):
    def test_layout_sizes(self):
        pair = (Image.new("RGB", (800, 600), "red"), Image.new("RGB", (800, 600), "blue"))
        strip = compose([pair] * 4, layout="strip", names=("A", "B"))
        grid = compose([pair] * 4, layout="grid", names=("A", "B"))
        self.assertGreater(strip.height, strip.width)
        self.assertGreater(grid.width, grid.height)
        self.assertGreater(strip.height, 4 * CELL_H)

    def test_every_theme_and_filter_renders(self):
        pair = (Image.new("RGB", (400, 300), "orange"), None)
        for theme in BoothSession.Theme.values:
            for photo_filter in BoothSession.Filter.values:
                img = compose(
                    [pair], theme=theme, photo_filter=photo_filter, names=("A", "B"),
                    clocks=(("Manila", "9:14 PM"), ("Toronto", "9:14 AM")),
                )
                self.assertEqual(img.mode, "RGB")


@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class BoothConsumerTests(TransactionTestCase):
    def setUp(self):
        self.couple, self.alex, self.sam = make_couple()
        self.stranger = User.objects.create_user("eve", "e@example.com", "pw-123456!")
        self.session = BoothSession.objects.create(couple=self.couple, started_by=self.alex)

    def communicator(self, user):
        app = URLRouter(websocket_urlpatterns)
        comm = WebsocketCommunicator(app, f"/ws/booth/{self.session.pk}/")
        comm.scope["user"] = user
        return comm

    async def test_stranger_rejected(self):
        comm = self.communicator(self.stranger)
        connected, _ = await comm.connect()
        self.assertFalse(connected)

    async def test_relay_and_synced_start(self):
        a, b = self.communicator(self.alex), self.communicator(self.sam)
        self.assertTrue((await a.connect())[0])
        self.assertTrue((await b.connect())[0])

        await a.send_json_to({"type": "hello", "ready": True})
        msg = await b.receive_json_from()
        self.assertEqual((msg["type"], msg["ready"], msg["from"]), ("hello", True, self.alex.id))
        self.assertTrue(await a.receive_nothing())  # sender doesn't get its own relay

        await b.send_json_to({"type": "signal", "data": {"description": {"type": "offer", "sdp": "x"}}})
        self.assertEqual((await a.receive_json_from())["type"], "signal")

        await b.send_json_to({"type": "start"})
        for comm in (a, b):
            msg = await comm.receive_json_from()
            self.assertEqual((msg["type"], msg["shots"]), ("countdown", 4))

        status = await sync_to_async(
            lambda: BoothSession.objects.get(pk=self.session.pk).status
        )()
        self.assertEqual(status, BoothSession.Status.CAPTURING)

        await a.send_json_to({"type": "start"})  # second start is refused
        self.assertEqual((await a.receive_json_from())["type"], "error")

        await a.disconnect()
        msg = await b.receive_json_from()
        self.assertEqual((msg["type"], msg["online"]), ("presence", False))
        await b.disconnect()
