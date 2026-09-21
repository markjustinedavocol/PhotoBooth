"""Create a demo couple (alex / sam) with a few sample strips.

    python manage.py seed_demo          # create if missing
    python manage.py seed_demo --reset  # wipe the demo couple and recreate it
"""
import random
from datetime import date, timedelta
from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from PIL import Image, ImageDraw

from booth.models import BoothSession, Frame
from booth.services import save_strip
from couples.models import Couple

User = get_user_model()
PASSWORD = "photobooth123"

PEOPLE = [
    # username, display name, tz, city, sky top, sky bottom, skin, shirt, is_night
    ("alex", "Alex", "Asia/Manila", "Manila", (24, 30, 72), (92, 60, 110), (224, 172, 132), (184, 59, 94), True),
    ("sam", "Sam", "America/Toronto", "Toronto", (255, 214, 170), (250, 240, 225), (241, 200, 170), (70, 110, 160), False),
]

SAMPLES = [
    ("classic", "none", "strip", "Our first strip", "Same moon, different skies. Can't wait to see you."),
    ("pastel", "warm", "grid", "Sunday call date", "You fell asleep on call again. Cutest thing ever."),
    ("film", "bw", "strip", "", ""),
]


def fake_frame(person, pose, rng):
    _, _, _, _, top, bottom, skin, shirt, night = person
    w, h = 960, 720
    img = Image.new("RGB", (w, h))
    draw = ImageDraw.Draw(img)
    for y in range(h):
        t = y / h
        draw.line([(0, y), (w, y)], fill=tuple(int(a + (b - a) * t) for a, b in zip(top, bottom)))
    if night:
        for _ in range(40):
            x, y = rng.randrange(w), rng.randrange(h // 2)
            r = rng.choice([1, 1, 2])
            draw.ellipse([x - r, y - r, x + r, y + r], fill=(255, 250, 230))
        draw.ellipse([w - 190, 70, w - 110, 150], fill=(250, 240, 210))
    else:
        draw.ellipse([90, 60, 210, 180], fill=(255, 230, 150))

    cx = w // 2 + (-70, 40, -20, 80)[pose]
    tilt = (-18, 10, 0, 22)[pose]
    draw.ellipse([cx - 230, 520, cx + 230, 900], fill=shirt)  # shoulders
    hx, hy = cx + tilt, 380
    draw.ellipse([hx - 130, hy - 150, hx + 130, hy + 150], fill=skin)  # head
    hair = (60, 40, 35) if night else (120, 80, 50)
    draw.chord([hx - 140, hy - 170, hx + 140, hy + 60], 180, 360, fill=hair)
    for ex in (-48, 48):  # eyes
        if pose == 2:
            draw.arc([hx + ex - 18, hy - 10, hx + ex + 18, hy + 14], 200, 340, fill=(40, 30, 30), width=6)
        else:
            draw.ellipse([hx + ex - 10, hy - 8, hx + ex + 10, hy + 12], fill=(40, 30, 30))
    draw.arc([hx - 55, hy + 20, hx + 55, hy + 90], 15, 165, fill=(150, 60, 70), width=7)  # smile
    for bx in (-80, 80):
        draw.ellipse([hx + bx - 22, hy + 30, hx + bx + 22, hy + 52], fill=(240, 150, 150))
    if pose == 3:  # half a heart-hands gesture toward the other partner
        draw.ellipse([cx + 170, 470, cx + 250, 550], fill=skin)

    buf = BytesIO()
    img.save(buf, "JPEG", quality=88)
    return ContentFile(buf.getvalue(), name="frame.jpg")


class Command(BaseCommand):
    help = "Create a demo couple (alex / sam, password 'photobooth123') with sample strips."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Delete and recreate the demo data.")

    @transaction.atomic
    def handle(self, *args, **options):
        if options["reset"]:
            User.objects.filter(username__in=[p[0] for p in PEOPLE]).delete()

        users = []
        for person in PEOPLE:
            username, name, tz, city = person[:4]
            user, created = User.objects.get_or_create(
                username=username, defaults={"email": f"{username}@example.com"}
            )
            if created:
                user.set_password(PASSWORD)
                user.save()
            profile = user.profile
            profile.display_name, profile.timezone, profile.city = name, tz, city
            profile.save()
            users.append(user)

        alex, sam = users
        couple = Couple.for_user(alex)
        if couple and couple.is_paired and couple.strips.exists():
            self.stdout.write(self.style.WARNING("Demo couple already exists (use --reset to recreate)."))
            return
        if couple is None or not couple.is_paired:
            Couple.objects.filter(partner_a__in=users).delete()
            Couple.objects.filter(partner_b__in=users).delete()
            couple = Couple.objects.create(
                partner_a=alex,
                partner_b=sam,
                paired_at=timezone.now(),
                anniversary=date(2024, 2, 14),
                next_meetup=timezone.localdate() + timedelta(days=45),
            )

        rng = random.Random(7)
        for days_ago, (theme, photo_filter, layout, caption, note) in zip((30, 9, 1), SAMPLES):
            when = timezone.now() - timedelta(days=days_ago, hours=rng.randint(0, 5))
            session = BoothSession.objects.create(
                couple=couple,
                started_by=alex,
                status=BoothSession.Status.DONE,
                theme=theme,
                photo_filter=photo_filter,
                layout=layout,
                caption=caption,
                captured_at=when,
            )
            for user, person in zip(users, PEOPLE):
                for index in range(session.shots):
                    Frame.objects.create(
                        session=session, user=user, index=index, image=fake_frame(person, index, rng)
                    )
            strip = save_strip(session)
            strip.love_note = note
            strip.is_favorite = days_ago == 30
            strip.save()
            strip.created_at = when
            strip.save(update_fields=["created_at"])

        # A solo strip Sam took for Alex to wake up to.
        when = timezone.now() - timedelta(hours=6)
        session = BoothSession.objects.create(
            mode=BoothSession.Mode.SOLO,
            couple=couple,
            started_by=sam,
            status=BoothSession.Status.DONE,
            theme="polaroid",
            photo_filter="warm",
            layout="strip",
            caption="Good morning from Toronto",
            captured_at=when,
        )
        for index in range(session.shots):
            Frame.objects.create(
                session=session, user=sam, index=index, image=fake_frame(PEOPLE[1], index, rng)
            )
        strip = save_strip(session)
        strip.love_note = "Coffee's on. Wish you were here to steal a sip."
        strip.save()

        self.stdout.write(
            self.style.SUCCESS(
                f"Demo ready: log in as 'alex' or 'sam' with password '{PASSWORD}' "
                f"({couple.strips.count()} strips)."
            )
        )
