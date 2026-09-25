from __future__ import annotations

import logging
from datetime import date, timedelta
from itertools import chain
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
    SECTION_ACTION_ITEMS,
    SECTION_DEPT_UPDATES,
    SECTION_OTHER,
    SECTION_SALES_PERFORMANCE,
    SNAPSHOT_TRIGGER_APPROVE,
    SNAPSHOT_TRIGGER_CHOICES,
    SNAPSHOT_TRIGGER_PUBLISH,
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
    SUBMISSION_RETURNED,
    SUBMISSION_STATUS_CHOICES,
    SUBMISSION_SUBMITTED,
    AgendaItem,
    ApprovedMeetingSnapshot,
    DepartmentSubmission,
    Meeting,
    MeetingAttendance,
    MeetingStatusHistory,
    MinutesSectionSpec,
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
    STATUS_APPROVED: {
        STATUS_RETURNED_FOR_CORRECTION,
        STATUS_PUBLISHED,
        STATUS_ARCHIVED,
        STATUS_CLOSED,
    },
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


def _walk_pipeline(meeting: Meeting, user, target_status: str) -> None:
    """Walk transition graph from current status to target if skip_role_check allowed elsewhere.

    Used as helper *before* service-layer direct-transition calls when a test or fast-path
    caller needs to skip intermediates. Modifies instance in-place by successive
    ``transition_meeting`` calls with ``skip_role_check=True`` so existing validation
    (identical-status, reason) still fires. Callers refresh from DB afterwards.
    """
    steps: list[str] = []
    current = meeting.status
    if current == target_status:
        return
    bfs: dict[str, list[str]] = {current: [current]}
    queue = [current]
    found = False
    while queue and not found:
        nxt = queue.pop(0)
        path = bfs[nxt]
        if nxt == target_status:
            steps = path[1:]
            found = True
            break
        for nb in sorted(VALID_TRANSITIONS.get(nxt, set())):
            if nb in bfs:
                continue
            bfs[nb] = [*path, nb]
            queue.append(nb)
    if not found:
        return
    for s in steps:
        transition_meeting(meeting, s, by_user=user, skip_role_check=True)
        meeting.status = s


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


def _default_json(o):
    if hasattr(o, "isoformat"):
        return o.isoformat()
    if hasattr(o, "__decimal__") or hasattr(o, "quantize"):
        return str(o)
    if o is None:
        return None
    return str(o)


def _serialize_meeting_payload(meeting, *, by_user) -> dict:
    meeting.refresh_from_db()
    agenda_items = list(
        AgendaItem.objects.filter(meeting=meeting)
        .select_related("category", "owner", "department")
        .prefetch_related("action_item_links__action_item__owner")
        .order_by("order")
    )
    attendance_rows = list(
        MeetingAttendance.objects.filter(meeting=meeting)
        .select_related("user")
        .order_by("user__username")
    )
    status_histories = list(
        MeetingStatusHistory.objects.filter(meeting=meeting)
        .select_related("transitioned_by")
        .order_by("-transitioned_at")
    )
    ai_links = [
        {
            "agenda_item_id": str(link.agenda_item_id),
            "agenda_item_order": getattr(link.agenda_item, "order", None),
            "action_item_id": str(link.action_item_id),
            "action_item_reference": getattr(link.action_item, "reference", None) or None,
            "action_item_title": getattr(link.action_item, "title", None) or "",
            "action_item_owner_name": (
                link.action_item.owner.get_display_name()
                if getattr(getattr(link, "action_item", None), "owner", None)
                else ""
            ),
            "action_item_due_date": (
                link.action_item.due_date.isoformat()
                if getattr(getattr(link, "action_item", None), "due_date", None)
                else None
            ),
            "action_item_priority": getattr(link.action_item, "priority", None) or "",
            "action_item_status": getattr(link.action_item, "status", None) or "",
            "created_by": link.created_by.get_display_name() if link.created_by else None,
            "created_at": _default_json(link.created_at),
        }
        for ai in agenda_items
        for link in ai.action_item_links.all()
    ]
    action_items = (
        list({(link["action_item_id"],): link for link in ai_links}.values()) if ai_links else []
    )
    snapshots_qs = list(
        meeting.approved_snapshots.all()
        .order_by("version")
        .values("version", "trigger", "approved_at", "published_at")
    )
    sales = _serialize_sales_for_meeting(meeting)

    now = timezone.now()
    payload = {
        "version_format": 1,
        "generated_at": _default_json(now),
        "generated_by": by_user.get_display_name()
        if getattr(by_user, "is_authenticated", False)
        else None,
        "meeting_meta": {
            "id": str(meeting.pk),
            "reference": meeting.reference,
            "title": meeting.title,
            "description": meeting.description or "",
            "start_at": _default_json(meeting.start_at),
            "end_at": _default_json(meeting.end_at),
            "location": meeting.location or "",
            "status": meeting.status,
            "meeting_type_code": getattr(getattr(meeting, "type", None), "code", None),
            "meeting_type_name": getattr(getattr(meeting, "type", None), "name", None),
            "department_name": (meeting.department.name if meeting.department_id else None),
            "chair_name": meeting.chair.get_display_name() if meeting.chair_id else None,
            "notes": meeting.notes or "",
            "duration_minutes": meeting.duration_minutes,
            "is_locked": bool(meeting.is_locked),
            "published_at": _default_json(meeting.published_at),
            "closed_at": _default_json(meeting.closed_at),
            "archived_at": _default_json(meeting.archived_at),
            "created_by": (
                meeting.created_by.get_display_name() if meeting.created_by_id else None
            ),
        },
        "attendance": [
            {
                "user_name": a.user.get_display_name(),
                "username": a.user.username,
                "email": a.user.email,
                "is_invited": bool(a.is_invited),
                "is_attended": bool(a.is_attended),
                "rsvp_status": a.rsvp_status,
                "role_at_meeting": a.role_at_meeting or "",
                "notes": a.notes or "",
                "arrived_at": _default_json(a.arrived_at),
                "departed_at": _default_json(a.departed_at),
            }
            for a in attendance_rows
        ],
        "agenda_items": [
            {
                "id": str(ai.pk),
                "order": ai.order,
                "title": ai.title,
                "category_name": ai.category.name if ai.category_id else None,
                "section_type": (
                    SECTION_DEPT_UPDATES
                    if ai.department_id
                    else (SECTION_ACTION_ITEMS if ai.item_status else SECTION_OTHER)
                ),
                "owner_name": ai.owner.get_display_name() if ai.owner_id else None,
                "department_name": ai.department.name if ai.department_id else None,
                "discussion": ai.discussion or "",
                "decision": ai.decision or "",
                "item_status": ai.item_status,
                "time_allocated_minutes": ai.time_allocated_minutes,
                "is_confidential": bool(ai.is_confidential),
                "notes": ai.notes or "",
                "action_item_links_count": ai_links_count_for(ai_links, ai.pk),
                "action_items": [link for link in ai_links if link["agenda_item_id"] == str(ai.pk)],
            }
            for ai in agenda_items
        ],
        "discussions": [
            {
                "agenda_item_id": str(ai.pk),
                "agenda_item_order": ai.order,
                "title": ai.title,
                "discussion": ai.discussion or "",
            }
            for ai in agenda_items
            if (ai.discussion or "").strip()
        ],
        "decisions": [
            {
                "agenda_item_id": str(ai.pk),
                "agenda_item_order": ai.order,
                "title": ai.title,
                "decision": ai.decision or "",
            }
            for ai in agenda_items
            if (ai.decision or "").strip()
        ],
        "action_items": action_items
        if action_items
        else [
            {
                "action_item_id": str(link["action_item_id"]),
                "action_item_reference": link["action_item_reference"],
                "action_item_title": link["action_item_title"],
                "action_item_owner_name": link["action_item_owner_name"],
                "action_item_due_date": link["action_item_due_date"],
                "action_item_priority": link["action_item_priority"],
                "action_item_status": link["action_item_status"],
                "agenda_item_id": link["agenda_item_id"],
            }
            for link in ai_links
        ],
        "sales_data": sales,
        "status_history": [
            {
                "from_status": h.from_status or None,
                "to_status": h.to_status,
                "transitioned_at": _default_json(h.transitioned_at),
                "transitioned_by": (
                    h.transitioned_by.get_display_name() if h.transitioned_by_id else None
                ),
                "reason": h.reason or "",
            }
            for h in status_histories
        ],
        "snapshots": [
            {
                "version": s["version"],
                "trigger": s["trigger"],
                "approved_at": _default_json(s["approved_at"]),
                "published_at": _default_json(s["published_at"]),
            }
            for s in snapshots_qs
        ],
        "version": None,
    }
    return payload


def ai_links_count_for(ai_links, agenda_pk) -> int:
    return sum(1 for link in ai_links if link["agenda_item_id"] == str(agenda_pk))


def _serialize_sales_for_meeting(meeting) -> dict:
    try:
        from apps.sales_updates.models import GroupPerformanceSnapshot
    except Exception:
        return {"has_linked_snapshot": False}
    linked = (
        GroupPerformanceSnapshot.objects.filter(meeting=meeting)
        .select_related("group", "period")
        .order_by("-created_at")
        .first()
    )
    if not linked:
        return {"has_linked_snapshot": False}
    result = {
        "has_linked_snapshot": True,
        "group_code": getattr(linked.group, "code", None),
        "group_name": getattr(linked.group, "name", None),
        "period_name": getattr(linked.period, "name", None),
        "currency": getattr(linked.period, "currency", "PHP"),
        "revenue_target": str(linked.revenue_target) if linked.revenue_target is not None else None,
        "revenue_actual": str(linked.revenue_actual) if linked.revenue_actual is not None else None,
        "revenue_pct": str(linked.revenue_pct) if linked.revenue_pct is not None else None,
        "revenue_deficit": str(linked.revenue_deficit)
        if linked.revenue_deficit is not None
        else None,
        "profit_target": str(linked.profit_target) if linked.profit_target is not None else None,
        "profit_actual": str(linked.profit_actual) if linked.profit_actual is not None else None,
        "profit_pct": str(linked.profit_pct) if linked.profit_pct is not None else None,
        "profit_margin_actual": str(linked.profit_margin_actual)
        if linked.profit_margin_actual is not None
        else None,
        "orders_target": linked.orders_target,
        "orders_actual": linked.orders_actual,
        "orders_pct": str(linked.orders_pct) if linked.orders_pct is not None else None,
        "deliveries_planned": linked.deliveries_planned,
        "deliveries_achieved": linked.deliveries_achieved,
        "deliveries_on_time": linked.deliveries_on_time,
        "deliveries_on_time_pct": str(linked.deliveries_on_time_pct)
        if linked.deliveries_on_time_pct is not None
        else None,
        "weekly_revenue_total": str(linked.weekly_revenue_total)
        if linked.weekly_revenue_total is not None
        else None,
    }
    return result


def create_approved_snapshot(
    meeting: Meeting,
    *,
    by_user,
    trigger: str,
    force_version: int | None = None,
) -> ApprovedMeetingSnapshot:
    """Create an immutable snapshot of the meeting with auto-incrementing version.

    Uses ``select_for_update`` on ``ApprovedMeetingSnapshot`` to prevent
    double-publish race conditions; combined with ``unique_together(meeting,
    version)`` this provides a hard two-tier guard.
    """
    from apps.meetings.models import ApprovedMeetingSnapshot as _Snap

    valid_triggers = {c[0] for c in SNAPSHOT_TRIGGER_CHOICES}
    if trigger not in valid_triggers:
        raise ValidationError(f"Invalid snapshot trigger: {trigger!r}")
    with transaction.atomic():
        locked = Meeting.objects.select_for_update().get(pk=meeting.pk)
        last_version = (
            _Snap.objects.filter(meeting=locked)
            .order_by("-version")
            .values_list("version", flat=True)
            .first()
        )
        next_version = int(last_version or 0) + 1
        version = force_version if force_version is not None else next_version
        payload = _serialize_meeting_payload(locked, by_user=by_user)
        payload["version"] = version
        payload["approval_meta"] = {
            "trigger": trigger,
            "approved_at": _default_json(timezone.now()),
            "approved_by": by_user.get_display_name()
            if getattr(by_user, "is_authenticated", False)
            else None,
            "version": version,
        }
        now = timezone.now()
        snap = _Snap(
            meeting=locked,
            version=version,
            trigger=trigger,
            payload=payload,
            approved_at=now,
            approved_by=(
                by_user if getattr(by_user, "is_authenticated", False) and by_user.pk else None
            ),
        )
        try:
            snap.save()
        except Exception as e:
            raise ValidationError(f"Snapshot create failed (unique version conflict): {e}") from e
        if trigger == SNAPSHOT_TRIGGER_PUBLISH:
            snap.published_at = now
            snap.published_by = (
                by_user if getattr(by_user, "is_authenticated", False) and by_user.pk else None
            )
            snap.save(update_fields=["published_at", "published_by"])
    return snap


def submit_for_review(meeting: Meeting, *, by_user, reason: str = "") -> MeetingStatusHistory:
    from apps.audit.models import AuditLog
    from apps.core.permissions import can_submit_minutes

    if not can_submit_minutes(by_user, meeting):
        raise ValidationError("You are not authorized to submit minutes for review.")
    history = transition_meeting(meeting, STATUS_FOR_REVIEW, by_user, reason, skip_role_check=True)
    log_audit_event(
        record_type=_record_type(meeting),
        record=meeting,
        action=AuditLog.ACTION_SUBMIT,
        user=(by_user if getattr(by_user, "is_authenticated", False) else None),
        new_values={"status": STATUS_FOR_REVIEW},
        previous_values={"status": getattr(history, "from_status", "")},
        reason=reason,
    )
    return history


def return_for_correction(
    meeting: Meeting,
    *,
    by_user,
    reason: str,
    marked_section_types: set[str] | None = None,
    management_remarks: str = "",
) -> MeetingStatusHistory:
    from apps.audit.models import AuditLog
    from apps.core.permissions import can_return_minutes

    if not can_return_minutes(by_user, meeting):
        raise ValidationError("You are not authorized to return minutes for correction.")
    if not (reason and reason.strip()):
        raise ValidationError("A return reason is required.")
    history = transition_meeting(
        meeting,
        STATUS_RETURNED_FOR_CORRECTION,
        by_user,
        reason,
        skip_role_check=True,
    )
    log_audit_event(
        record_type=_record_type(meeting),
        record=meeting,
        action=AuditLog.ACTION_RETURN,
        user=(by_user if getattr(by_user, "is_authenticated", False) else None),
        new_values={
            "status": STATUS_RETURNED_FOR_CORRECTION,
            "marked_sections": sorted(marked_section_types or []),
        },
        previous_values={"status": getattr(history, "from_status", "")},
        reason=reason,
    )
    dept_subs = DepartmentSubmission.objects.filter(meeting=meeting)
    if marked_section_types or management_remarks:
        with transaction.atomic():
            for sub in dept_subs.select_for_update():
                if management_remarks and sub.management_remarks != management_remarks:
                    sub.management_remarks = (
                        f"{sub.management_remarks}\n\n--- {by_user} ---\n{management_remarks}".strip()
                        if sub.management_remarks
                        else management_remarks
                    )
                sub.submission_state = SUBMISSION_RETURNED
                sub.save(
                    update_fields=[
                        "management_remarks",
                        "submission_state",
                        "updated_at",
                    ]
                )
    return history


def resubmit_for_review(meeting: Meeting, *, by_user, reason: str = "") -> MeetingStatusHistory:
    from apps.audit.models import AuditLog
    from apps.core.permissions import can_resubmit_minutes

    if not can_resubmit_minutes(by_user, meeting):
        raise ValidationError("You are not authorized to resubmit minutes.")
    history = transition_meeting(meeting, STATUS_FOR_REVIEW, by_user, reason, skip_role_check=True)
    log_audit_event(
        record_type=_record_type(meeting),
        record=meeting,
        action=AuditLog.ACTION_RESUBMIT,
        user=(by_user if getattr(by_user, "is_authenticated", False) else None),
        new_values={"status": STATUS_FOR_REVIEW},
        previous_values={"status": getattr(history, "from_status", "")},
        reason=reason,
    )
    with transaction.atomic():
        for sub in DepartmentSubmission.objects.filter(
            meeting=meeting, submission_state=SUBMISSION_RETURNED
        ).select_for_update():
            sub.submission_state = SUBMISSION_SUBMITTED
            sub.save(update_fields=["submission_state", "updated_at"])
    return history


def approve_meeting(meeting: Meeting, *, by_user, reason: str = "") -> MeetingStatusHistory:
    from apps.core.permissions import can_approve_meeting

    if not can_approve_meeting(by_user, meeting):
        raise ValidationError("You are not authorized to approve this meeting.")
    history = transition_meeting(meeting, STATUS_APPROVED, by_user, reason, skip_role_check=True)
    with transaction.atomic():
        create_approved_snapshot(meeting, by_user=by_user, trigger=SNAPSHOT_TRIGGER_APPROVE)
    return history


def publish_meeting(meeting: Meeting, *, by_user, reason: str = "") -> MeetingStatusHistory:
    from apps.core.permissions import can_publish_meeting

    if not can_publish_meeting(by_user, meeting):
        raise ValidationError("You are not authorized to publish this meeting.")
    history = transition_meeting(meeting, STATUS_PUBLISHED, by_user, reason, skip_role_check=True)
    with transaction.atomic():
        snap = (
            ApprovedMeetingSnapshot.objects.filter(
                meeting=meeting, trigger__in={SNAPSHOT_TRIGGER_APPROVE, SNAPSHOT_TRIGGER_PUBLISH}
            )
            .order_by("-version")
            .first()
        )
        if snap is None or snap.trigger != SNAPSHOT_TRIGGER_PUBLISH:
            snap = create_approved_snapshot(
                meeting, by_user=by_user, trigger=SNAPSHOT_TRIGGER_PUBLISH
            )
    return history


def close_meeting(meeting: Meeting, *, by_user, reason: str = "") -> MeetingStatusHistory:
    from apps.core.permissions import can_close_meeting

    if not can_close_meeting(by_user, meeting):
        raise ValidationError("You are not authorized to close this meeting.")
    if not (reason and reason.strip()):
        raise ValidationError("A reason is required to close a meeting.")
    return transition_meeting(meeting, STATUS_CLOSED, by_user, reason, skip_role_check=True)


def reopen_meeting(
    meeting: Meeting,
    *,
    by_user,
    target_status: str,
    reason: str,
) -> MeetingStatusHistory:
    from apps.audit.models import AuditLog
    from apps.core.permissions import can_reopen_meeting

    if not can_reopen_meeting(by_user, meeting):
        raise ValidationError("You are not authorized to reopen this meeting.")
    if not (reason and reason.strip()):
        raise ValidationError("A reason is required to reopen a meeting.")
    allowed = {
        STATUS_APPROVED: {STATUS_RETURNED_FOR_CORRECTION, STATUS_PUBLISHED, STATUS_CLOSED},
        STATUS_PUBLISHED: {STATUS_RETURNED_FOR_CORRECTION, STATUS_APPROVED, STATUS_CLOSED},
        STATUS_CLOSED: {STATUS_PUBLISHED},
        STATUS_ARCHIVED: {STATUS_APPROVED, STATUS_PUBLISHED, STATUS_CLOSED},
    }
    current = meeting.status
    targets_from_current = allowed.get(current, set())
    if target_status not in targets_from_current:
        raise ValidationError(f"Cannot reopen from {current} to {target_status}.")
    history = transition_meeting(meeting, target_status, by_user, reason, skip_role_check=True)
    log_audit_event(
        record_type=_record_type(meeting),
        record=meeting,
        action=AuditLog.ACTION_REOPEN,
        user=(by_user if getattr(by_user, "is_authenticated", False) else None),
        new_values={"status": target_status},
        previous_values={"status": getattr(history, "from_status", "")},
        reason=reason,
    )
    return history


def dept_submission_upsert(
    meeting: Meeting,
    department,
    *,
    by_user,
    submission_state: str,
    missing_info: str = "",
    management_remarks: str = "",
    notes: str = "",
    contributor=None,
) -> DepartmentSubmission:
    from apps.core.permissions import can_submit_minutes

    if not can_submit_minutes(by_user, meeting):
        raise ValidationError("Not authorized to edit department submissions.")
    valid_states = {c[0] for c in SUBMISSION_STATUS_CHOICES}
    if submission_state not in valid_states:
        raise ValidationError(f"Invalid submission state: {submission_state!r}")
    now = timezone.now()
    dept_id = getattr(department, "pk", None) or department
    with transaction.atomic():
        try:
            sub = DepartmentSubmission.objects.select_for_update().get(
                meeting=meeting, department_id=dept_id
            )
        except DepartmentSubmission.DoesNotExist:
            sub = DepartmentSubmission(
                meeting=meeting,
                department_id=dept_id,
            )
        sub.submission_state = submission_state
        sub.missing_info = missing_info or ""
        sub.management_remarks = management_remarks or ""
        sub.notes = notes or ""
        sub.contributor = contributor or sub.contributor
        sub.last_updated_at = now
        if submission_state == SUBMISSION_SUBMITTED:
            sub.last_submitted_at = now
            if getattr(by_user, "is_authenticated", False) and by_user.pk:
                sub.submitted_by = by_user
        if (
            getattr(by_user, "is_authenticated", False)
            and by_user.pk
            and sub.contributor_id is None
        ):
            sub.contributor = by_user
        sub.save()
    return sub


def agenda_completeness(meeting: Meeting) -> list[dict]:
    specs = list(MinutesSectionSpec.objects.filter(meeting_type=meeting.type_id).order_by("order"))
    subs = {s.department_id: s for s in DepartmentSubmission.objects.filter(meeting=meeting)}
    ai_by_dept: dict = {}
    for ai in (
        AgendaItem.objects.filter(meeting=meeting)
        .values("department_id", "discussion", "decision", "order")
        .iterator()
    ):
        did = ai["department_id"]
        ai_by_dept.setdefault(did, []).append(ai)
    rows: list[dict] = []
    for spec in specs:
        stype = spec.section_type
        section_pass = True
        missing: list[str] = []
        if stype == SECTION_DEPT_UPDATES:
            for dep_id, dept_ais in ai_by_dept.items():
                if dep_id is None:
                    continue
                if not any(a.get("discussion") or a.get("decision") for a in dept_ais):
                    section_pass = False
                    missing.append(f"Missing discussion/decision for department #{dep_id}")
        elif stype == SECTION_ACTION_ITEMS:
            all_action_ais = list(chain.from_iterable(ai_by_dept.values())) + ai_by_dept.get(
                None, []
            )
            ais_wo_status = [
                f"Agenda #{a.get('order')} has no item status"
                for a in all_action_ais
                if not a.get("discussion") and not a.get("decision")
            ]
            if ais_wo_status:
                section_pass = False
                missing.extend(ais_wo_status)
        elif stype == SECTION_SALES_PERFORMANCE:
            try:
                from apps.sales_updates.models import GroupPerformanceSnapshot as _GPS

                has_snapshot = _GPS.objects.filter(meeting=meeting).exists()
            except Exception:
                has_snapshot = False
            if not has_snapshot:
                section_pass = False
                missing.append("No sales snapshot linked to this meeting.")
        rows.append(
            {
                "spec": spec,
                "section_type": stype,
                "passed": section_pass,
                "missing": missing,
                "related_submissions": [
                    subs[dep]
                    for dep in subs
                    if (stype == SECTION_DEPT_UPDATES and dep is not None and subs[dep])
                ],
            }
        )
    return rows


def meetings_prep_dashboard_data(user) -> tuple[dict, list]:
    from apps.meetings.models import Meeting

    now = timezone.now()
    window_start = now.date()
    window_end = window_start + timedelta(days=60)
    qs = Meeting.objects.filter(
        start_at__date__gte=window_start,
        start_at__date__lte=window_end,
    ).order_by("start_at")
    counts: dict = {
        "total_in_window": qs.count(),
        "pending_review": qs.filter(status=STATUS_FOR_REVIEW).count(),
        "returned_for_correction": qs.filter(status=STATUS_RETURNED_FOR_CORRECTION).count(),
        "approved_this_month": qs.filter(
            status__in={STATUS_APPROVED, STATUS_PUBLISHED, STATUS_CLOSED},
            created_at__month=window_start.month,
            created_at__year=window_start.year,
        ).count(),
        "ready_to_publish": qs.filter(status=STATUS_APPROVED).count(),
    }
    rows = list(qs.values("pk", "reference", "title", "status", "start_at", "type__name"))[:30]
    return counts, rows
