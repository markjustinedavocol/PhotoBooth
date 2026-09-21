from django.db.models.signals import post_delete
from django.dispatch import receiver

from .models import PhotoStrip


@receiver(post_delete, sender=PhotoStrip)
def delete_strip_file(sender, instance, **kwargs):
    if instance.image:
        instance.image.delete(save=False)
