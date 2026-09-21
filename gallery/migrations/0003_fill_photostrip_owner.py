from django.db import migrations
from django.db.models import OuterRef, Subquery


def fill_owner(apps, schema_editor):
    PhotoStrip = apps.get_model("gallery", "PhotoStrip")
    BoothSession = apps.get_model("booth", "BoothSession")
    PhotoStrip.objects.filter(owner__isnull=True).update(
        owner=Subquery(
            BoothSession.objects.filter(pk=OuterRef("session_id")).values("started_by")[:1]
        )
    )


class Migration(migrations.Migration):
    dependencies = [
        ("gallery", "0002_photostrip_owner_alter_photostrip_couple"),
        ("booth", "0002_boothsession_mode_alter_boothsession_couple"),
    ]

    operations = [migrations.RunPython(fill_owner, migrations.RunPython.noop)]
