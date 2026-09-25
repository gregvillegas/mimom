from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from apps.audit.models import AuditLog
from apps.audit.services import log_audit_event
from apps.meetings.models import ApprovedMeetingSnapshot, Meeting


@receiver(pre_save, sender=Meeting, dispatch_uid="meeting_auto_reference")
def auto_generate_meeting_reference(sender, instance: Meeting, **kwargs):
    if not instance.reference:
        from apps.meetings.services import generate_meeting_reference

        generate_meeting_reference(instance, save=False)


@receiver(post_save, sender=ApprovedMeetingSnapshot, dispatch_uid="snapshot_created_audit")
def audit_snapshot_created(sender, instance: ApprovedMeetingSnapshot, created, **kwargs):
    if not created:
        return
    by = getattr(instance, "approved_by", None)
    log_audit_event(
        record_type=f"{instance._meta.app_label}.{instance._meta.object_name}",
        record=instance,
        action=AuditLog.ACTION_SNAPSHOT,
        user=by,
        new_values={
            "version": instance.version,
            "trigger": instance.trigger,
            "meeting_id": str(instance.meeting_id),
        },
        reason="Approved meeting snapshot created.",
    )
