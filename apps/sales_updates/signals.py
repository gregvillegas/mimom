from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.audit.models import AuditLog
from apps.audit.services import log_audit_event
from apps.sales_updates.models import GroupPerformanceSnapshot
from apps.sales_updates.services import is_snapshot_locked


@receiver(post_save, sender=GroupPerformanceSnapshot)
def snapshot_post_save_audit(sender, instance: GroupPerformanceSnapshot, created, **kwargs):
    """Rule 14 — when a snapshot's linked meeting APPROVED/PUBLISHED status makes it
    locked, emit a LOCK audit event once.

    The snapshot does not have an explicit `locked` boolean column; lock state is
    derived from the linked meeting status via `is_snapshot_locked()`.
    """
    if is_snapshot_locked(instance):
        log_audit_event(
            record_type="sales_updates.groupperformancesnapshot",
            record=instance,
            action=AuditLog.ACTION_LOCK,
            user=getattr(instance, "created_by", None),
            reason=(
                f"Snapshot locked by meeting approval "
                f"({getattr(getattr(instance, 'meeting', None), 'reference', '?')})."
            ),
        )
