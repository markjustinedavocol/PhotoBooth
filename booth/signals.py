from django.db.models.signals import post_delete
from django.dispatch import receiver

from .models import Frame


@receiver(post_delete, sender=Frame)
def delete_frame_file(sender, instance, **kwargs):
    if instance.image:
        instance.image.delete(save=False)
