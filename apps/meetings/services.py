from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import TYPE_CHECKING

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.audit.services import log_audit_event

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from apps.meetings.models import AgendaItem, Meeting, MeetingStatusHistory

from apps.meetings.models import (
    ITEM_STATUS_CARRIED_FORWARD,
    STATUS_AGENDA_FINALIZED,
    STATUS_APPROVED,
    STATUS_ARCHIVED,
    STATUS_CHOICES,
    STATUS_CLOSED,
    STATUS_DRAFT,
    STATUS_FOR_REVIEW,
    STATUS_IN_PROGRESS,
    STATUS_OPEN_UPDATES,
    STATUS_PUBLISHED,
    STATUS_RETURNED_FOR_CORRECTION,
    AgendaItem,
    Meeting,
    MeetingStatusHistory,
)

logger = logging.getLogger(__name__)


VALID_TRANSITIONS: dict[str, set[str]] = {
    STATUS_DRAFT: {STATUS_DRAFT, STATUS_OPEN_UPDATES, STATUS_ARCHIVED},
    STATUS_OPEN_UPDATES: {STATUS_DRAFT, STATUS_AGENDA_FINALIZED, STATUS_ARCHIVED},
    STATUS_AGENDA_FINALIZED: {STATUS_OPEN_UPDATES, STATUS_IN_PROGRESS, STATUS_ARCHIVED},
    STATUS_IN_PROGRESS: {STATUS_AGENDA_FINALIZED, STATUS_FOR_REVIEW, STATUS_ARCHIVED},
    STATUS_FOR_REVIEW: {
        STATUS_IN_PROGRESS,
        STATUS_RETURNED_FOR_CORRECTION,
        STATUS_APPROVED,
        STATUS_ARCHIVED,
    },
    STATUS_RETURNED_FOR_CORRECTION: {STATUS_FOR_REVIEW, STATUS_ARCHIVED},
    STATUS_APPROVED: {STATUS_RETURNED_FOR_CORRECTION, STATUS_PUBLISHED, STATUS_ARCHIVED},
    STATUS_PUBLISHED: {
        STATUS_APPROVED,
        STATUS_RETURNED_FOR_CORRECTION,
        STATUS_CLOSED,
        STATUS_ARCHIVED,
    },
    STATUS_CLOSED: {STATUS_PUBLISHED, STATUS_ARCHIVED},
    STATUS_ARCHIVED: set(),
}

REQUIRE_REASON_TRANSITIONS: set[tuple[str, str]] = {
    (STATUS_FOR_REVIEW, STATUS_RETURNED_FOR_CORRECTION),
    (STATUS_APPROVED, STATUS_RETURNED_FOR_CORRECTION),
    (STATUS_PUBLISHED, STATUS_RETURNED_FOR_CORRECTION),
}

REQUIRE_ADMIN_TRANSITIONS: set[str] = {STATUS_RETURNED_FOR_CORRECTION, STATUS_ARCHIVED}


def _record_type(instance) -> str:
    return f"{instance._meta.app_label}.{instance._meta.object_name}"


def generate_meeting_reference(meeting: Meeting, *, save: bool = True) -> str:
    """Generate a unique human-readable reference for the meeting.

    Pattern: {TYPE_CODE}-{YYYY}-{NNNN}. Uses IntegrityError retry up to 3 times.
    """
    if meeting.reference:
        return meeting.reference
    mtype = getattr(meeting, "type", None)
    code = (getattr(mtype, "code", None) or "").strip().upper() or "MTG"
    year = (getattr(meeting, "start_at", None) or timezone.now()).year
    prefix = f"{code}-{year}-"

    for _attempt in range(3):
        with transaction.atomic():
            existing = list(
                Meeting.objects.filter(reference__startswith=prefix)
                .values_list("reference", flat=True)
                .iterator()
            )
            numbers = []
            for ref in existing:
                tail = ref[len(prefix) :]
                if tail.isdigit():
                    numbers.append(int(tail))
            next_n = max(numbers, default=0) + 1
            ref = f"{prefix}{next_n:04d}"
            if Meeting.objects.filter(reference=ref).exists():
                continue
            meeting.reference = ref
            if save:
                meeting.save(update_fields=["reference"])
            return ref
    raise ValidationError("Failed to generate a unique meeting reference after retries.")


def transition_meeting(
    meeting: Meeting,
    target_status: str,
    by_user,
    reason: str = "",
    *,
    skip_role_check: bool = False,
) -> MeetingStatusHistory:
    """Validate and apply a meeting status transition inside a transaction."""
    if not target_status or not any(target_status == s for s, _ in STATUS_CHOICES):
        raise ValidationError(f"Invalid target status: {target_status!r}")
    try:
        fresh_meeting = Meeting.objects.get(pk=meeting.pk)
    except Meeting.DoesNotExist as err:
        raise ValidationError("Meeting not found.") from err
    current = fresh_meeting.status
    if current == target_status:
        raise ValidationError("Target status is identical to current status.")

    allowed_targets = VALID_TRANSITIONS.get(current, set())
    if target_status not in allowed_targets:
        raise ValidationError(
            f"Transition from {dict(STATUS_CHOICES).get(current, current)} to "
            f"{dict(STATUS_CHOICES).get(target_status, target_status)} is not permitted."
        )

    from apps.core.permissions import REOPEN_AUTHORIZED_ROLES

    if (
        target_status in REQUIRE_ADMIN_TRANSITIONS
        and not skip_role_check
        and not (
            getattr(by_user, "is_superuser", False)
            or bool(by_user and by_user.has_role(*REOPEN_AUTHORIZED_ROLES))
        )
    ):
        raise ValidationError(
            "This status transition requires System Administrator or Management "
            "Administrator privileges."
        )

    if (current, target_status) in REQUIRE_REASON_TRANSITIONS and not (reason and reason.strip()):
        raise ValidationError("A reason is required for this transition.")

    with transaction.atomic():
        locked = Meeting.objects.select_for_update().get(pk=meeting.pk)
        if locked.status != current:
            raise ValidationError("Meeting status changed concurrently. Please reload.")
        previous_values = {"status": locked.status}
        locked.status = target_status
        now = timezone.now()
        updates: list[str] = ["status", "updated_at"]
        if target_status == STATUS_PUBLISHED and not locked.published_at:
            locked.published_at = now
            updates.append("published_at")
            meeting.published_at = now
        if target_status == STATUS_CLOSED and not locked.closed_at:
            locked.closed_at = now
            updates.append("closed_at")
            meeting.closed_at = now
        if target_status == STATUS_ARCHIVED and not locked.archived_at:
            locked.archived_at = now
            updates.append("archived_at")
            meeting.archived_at = now
        locked.save(update_fields=updates)
        meeting.status = target_status

        history = MeetingStatusHistory.objects.create(
            meeting=locked,
            from_status=current,
            to_status=target_status,
            transitioned_at=now,
            transitioned_by=by_user if getattr(by_user, "is_authenticated", False) else None,
            reason=reason.strip() if reason else "",
        )

        action = AuditLog.ACTION_TRANSITION
        if target_status == STATUS_PUBLISHED:
            action = AuditLog.ACTION_PUBLISH
        elif target_status == STATUS_APPROVED:
            action = AuditLog.ACTION_APPROVE
        elif target_status == STATUS_ARCHIVED:
            action = AuditLog.ACTION_ARCHIVE
        log_audit_event(
            record_type=_record_type(locked),
            record=locked,
            action=action,
            user=by_user if getattr(by_user, "is_authenticated", False) else None,
            previous_values=previous_values,
            new_values={"status": target_status},
            reason=reason.strip() if reason else "",
        )
        return history


def build_calendar(month_start: date, meetings: Iterable[Meeting]) -> list[dict]:
    """Return a flat list of 42 day cells (6 weeks x 7 days) starting Sunday."""
    meetings = list(meetings)
    first_weekday = month_start.weekday()
    start = month_start - timedelta(days=(first_weekday + 1) % 7)
    cells: list[dict] = []
    for idx in range(42):
        d = start + timedelta(days=idx)
        day_meetings = [m for m in meetings if m.start_at and m.start_at.date() == d]
        cells.append(
            {
                "date": d,
                "in_month": d.month == month_start.month,
                "is_today": d == timezone.localdate(),
                "meetings": day_meetings,
            }
        )
    return cells


def carry_forward_agenda_items(
    source: Meeting,
    target: Meeting,
    item_ids: Sequence,
    by_user,
) -> list[AgendaItem]:
    """Copy selected items from source to target; clears decision, carries-forward flag set.

    Skips confidential items the caller cannot view. Appends new items at end of
    target's order list to avoid unique_together collisions.
    """
    from apps.core.permissions import can_view_confidential_items

    item_pks = [str(pk) for pk in item_ids]
    candidate_items = list(
        AgendaItem.objects.filter(meeting=source, pk__in=item_pks)
        .select_related("category", "owner", "department")
        .order_by("order")
    )
    user_can_view_conf = can_view_confidential_items(by_user, meeting=source)
    permitted: list[AgendaItem] = []
    for item in candidate_items:
        if item.is_confidential and not user_can_view_conf:
            continue
        permitted.append(item)
    if not permitted:
        return []

    with transaction.atomic():
        last_order_row = (
            AgendaItem.objects.filter(meeting=target)
            .order_by("-order")
            .values_list("order", flat=True)
            .first()
        )
        order_counter = int(last_order_row or -1) + 1
        created: list[AgendaItem] = []
        for source_item in permitted:
            copy = AgendaItem(
                meeting=target,
                category_id=source_item.category_id,
                order=order_counter,
                title=source_item.title,
                discussion="",
                decision="",
                item_status=ITEM_STATUS_CARRIED_FORWARD,
                owner_id=source_item.owner_id,
                department_id=source_item.department_id,
                is_confidential=source_item.is_confidential,
                parent_item_id=None,
                carried_forward_from=source_item,
                time_allocated_minutes=source_item.time_allocated_minutes,
                notes=source_item.notes,
            )
            copy.save()
            created.append(copy)
            order_counter += 1

        log_audit_event(
            record_type=_record_type(target),
            record=target,
            action=AuditLog.ACTION_UPDATE,
            user=by_user if getattr(by_user, "is_authenticated", False) else None,
            previous_values={"agenda_items_carry_forward_source": None},
            new_values={
                "carried_items": len(created),
                "source_meeting": str(source.pk),
            },
            reason="Carry-forward agenda items",
        )
    return created
