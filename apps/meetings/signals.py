from django.db.models.signals import pre_save
from django.dispatch import receiver

from apps.meetings.models import Meeting


@receiver(pre_save, sender=Meeting, dispatch_uid="meeting_auto_reference")
def auto_generate_meeting_reference(sender, instance: Meeting, **kwargs):
    if not instance.reference:
        from apps.meetings.services import generate_meeting_reference

        generate_meeting_reference(instance, save=False)
