from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import TYPE_CHECKING

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.audit.services import log_audit_event

if TYPE_CHECKING:
    from collections.abc import Sequence

    from apps.accounts.models import User as AuthUser
    from apps.action_items.models import ActionItem, ActionItemStatusHistory

from apps.action_items.models import (
    ACTIVE_STATUSES,
    PRIORITY_HIGH,
    PRIORITY_LOW,
    PRIORITY_MEDIUM,
    PRIORITY_URGENT,
    STATUS_BLOCKED,
    STATUS_CANCELLED,
    STATUS_CHOICES,
    STATUS_COMPLETED,
    STATUS_IN_PROGRESS,
    STATUS_OPEN,
    STATUS_REOPENED,
    STATUS_UNDER_REVIEW,
    ActionItem,
    ActionItemAssignee,
    ActionItemCarryForwardLink,
    ActionItemStatusHistory,
    ActionItemUpdate,
)

logger = logging.getLogger(__name__)


VALID_TRANSITIONS: dict[str, set[str]] = {
    STATUS_OPEN: {
        STATUS_IN_PROGRESS,
        STATUS_BLOCKED,
        STATUS_COMPLETED,
        STATUS_CANCELLED,
        STATUS_UNDER_REVIEW,
    },
    STATUS_IN_PROGRESS: {
        STATUS_OPEN,
        STATUS_BLOCKED,
        STATUS_COMPLETED,
        STATUS_CANCELLED,
        STATUS_UNDER_REVIEW,
    },
    STATUS_BLOCKED: {
        STATUS_OPEN,
        STATUS_IN_PROGRESS,
        STATUS_COMPLETED,
        STATUS_CANCELLED,
        STATUS_UNDER_REVIEW,
    },
    STATUS_UNDER_REVIEW: {
        STATUS_OPEN,
        STATUS_IN_PROGRESS,
        STATUS_BLOCKED,
        STATUS_COMPLETED,
        STATUS_CANCELLED,
    },
    STATUS_COMPLETED: {STATUS_REOPENED, STATUS_CANCELLED},
    STATUS_CANCELLED: {STATUS_REOPENED, STATUS_COMPLETED},
    STATUS_REOPENED: {
        STATUS_OPEN,
        STATUS_IN_PROGRESS,
        STATUS_BLOCKED,
        STATUS_UNDER_REVIEW,
        STATUS_COMPLETED,
        STATUS_CANCELLED,
    },
}

REQUIRE_REASON_TRANSITIONS: set[tuple[str, str]] = {
    (STATUS_COMPLETED, STATUS_REOPENED),
    (STATUS_CANCELLED, STATUS_REOPENED),
    (STATUS_UNDER_REVIEW, STATUS_CANCELLED),
}

REQUIRE_ADMIN_TRANSITIONS: set[str] = {STATUS_REOPENED}

DEFAULT_SKIP_CARRY_STATUSES: set[str] = {STATUS_COMPLETED, STATUS_CANCELLED}


def generate_action_reference(item: ActionItem, *, force: bool = False) -> str:
    if getattr(item, "reference", None) and not force:
        return item.reference
    year = timezone.now().year
    prefix = f"ACT-{year}-"
    for _attempt in range(3):
        with transaction.atomic():
            existing = list(
                ActionItem.objects.filter(reference__startswith=prefix)
                .values_list("reference", flat=True)
                .iterator()
            )
            numbers = []
            for ref in existing:
                tail = ref[len(prefix) :]
                if tail.isdigit():
                    numbers.append(int(tail))
            next_num = (max(numbers) + 1) if numbers else 1
            candidate = f"{prefix}{next_num:04d}"
            probe = ActionItem(reference=candidate)
            try:
                with transaction.atomic():
                    probe.full_clean(exclude=["title"])
                    probe.save(using=ActionItem.objects.db)
                    probe.delete()
            except IntegrityError:
                continue
            except ValidationError:
                pass
            item.reference = candidate
            return candidate
    raise ValidationError("Unable to generate unique action reference after 3 attempts.")


def transition_actionitem(
    item: ActionItem,
    target_status: str,
    *,
    by_user: AuthUser | None = None,
    reason: str = "",
    skip_role_check: bool = False,
) -> ActionItemStatusHistory:
    if not target_status or not any(target_status == s for s, _ in STATUS_CHOICES):
        raise ValidationError(f"Invalid target status: {target_status!r}")
    try:
        fresh_item = ActionItem.objects.get(pk=item.pk)
    except ActionItem.DoesNotExist as err:
        raise ValidationError("Action item not found.") from err
    current = fresh_item.status
    if current == target_status:
        raise ValidationError("Target status is identical to current status.")

    allowed_targets = VALID_TRANSITIONS.get(current, set())
    if target_status not in allowed_targets:
        raise ValidationError(
            f"Transition from {dict(STATUS_CHOICES).get(current, current)} to "
            f"{dict(STATUS_CHOICES).get(target_status, target_status)} is not permitted."
        )

    from apps.core.permissions import ACTION_REOPEN_ROLES

    if (
        target_status in REQUIRE_ADMIN_TRANSITIONS
        and not skip_role_check
        and not (
            getattr(by_user, "is_superuser", False)
            or bool(by_user and by_user.has_role(*ACTION_REOPEN_ROLES))
        )
    ):
        raise ValidationError(
            "This status transition requires System Administrator or Management "
            "Administrator privileges."
        )

    if (current, target_status) in REQUIRE_REASON_TRANSITIONS and not (reason and reason.strip()):
        raise ValidationError("A reason is required for this status transition.")

    progress_before = fresh_item.progress_pct
    if target_status == STATUS_COMPLETED and fresh_item.progress_pct < 100:
        progress_after = 100
    elif target_status == STATUS_IN_PROGRESS and fresh_item.progress_pct <= 0:
        progress_after = 10
    else:
        progress_after = fresh_item.progress_pct

    if target_status in {STATUS_COMPLETED, STATUS_CANCELLED, STATUS_REOPENED}:
        blockers = (fresh_item.blockers or "").strip()
        if target_status == STATUS_COMPLETED and blockers:
            raise ValidationError(
                "Resolve all blockers (clear the Blockers field) before marking complete."
            )

    with transaction.atomic():
        locked = ActionItem.objects.select_for_update().get(pk=fresh_item.pk)
        old_status = locked.status
        locked.status = target_status
        locked.progress_pct = progress_after
        if target_status == STATUS_COMPLETED:
            locked.completed_at = locked.completed_at or timezone.now()
        elif old_status == STATUS_COMPLETED and target_status != STATUS_COMPLETED:
            locked.completed_at = None
        if target_status == STATUS_REOPENED:
            locked.reopened_count = (locked.reopened_count or 0) + 1
        if by_user is not None:
            locked.last_modified_by = by_user
        locked.save()

        history = ActionItemStatusHistory.objects.create(
            action_item=locked,
            from_status=old_status,
            to_status=target_status,
            progress_before=progress_before,
            progress_after=progress_after,
            transitioned_by=by_user,
            reason=reason.strip() if reason else "",
        )

        action = AuditLog.ACTION_TRANSITION
        if target_status == STATUS_COMPLETED:
            action = AuditLog.ACTION_COMPLETE
        elif target_status == STATUS_REOPENED:
            action = AuditLog.ACTION_REOPEN
        log_audit_event(
            record_type="action_items.actionitem",
            record=locked,
            action=action,
            user=by_user,
            reason=reason.strip() if reason else f"Status: {old_status} → {target_status}",
        )

        item.status = locked.status
        item.progress_pct = locked.progress_pct
        item.completed_at = locked.completed_at
        item.reopened_count = locked.reopened_count
        item.last_modified_by = locked.last_modified_by
        return history


def carry_forward_action_items(
    source_items: Sequence[ActionItem],
    *,
    target_meeting=None,
    target_scope_key: str = "default",
    include_completed: bool = False,
    include_cancelled: bool = False,
    by_user: AuthUser | None = None,
    reason: str = "",
) -> list[ActionItem]:
    if not source_items:
        return []
    skip_statuses = set(DEFAULT_SKIP_CARRY_STATUSES)
    if include_completed:
        skip_statuses.discard(STATUS_COMPLETED)
    if include_cancelled:
        skip_statuses.discard(STATUS_CANCELLED)
    ordered = sorted(
        [s for s in source_items if s.status not in skip_statuses],
        key=lambda s: (s.priority, s.created_at),
    )
    created: list[ActionItem] = []
    today = timezone.now().date()
    try:
        with transaction.atomic():
            for src in ordered:
                existing_link = ActionItemCarryForwardLink.objects.filter(
                    source_item=src,
                    target_meeting=target_meeting,
                    target_scope_key=target_scope_key,
                ).first()
                if existing_link is not None:
                    created.append(existing_link.new_item)
                    continue
                new_item = ActionItem(
                    title=src.title,
                    description=src.description,
                    source_meeting=target_meeting or src.source_meeting,
                    source_agenda_item=src.source_agenda_item,
                    department=src.department,
                    created_by=by_user,
                    last_modified_by=by_user,
                    owner=src.owner,
                    priority=src.priority,
                    status=STATUS_OPEN,
                    progress_pct=0,
                    due_date=src.due_date or (today + timedelta(days=14)),
                    blockers="",
                    next_steps=src.next_steps,
                    carried_forward_from=src,
                )
                try:
                    new_item.full_clean(exclude=["reference"])
                except ValidationError as err:
                    logger.warning("Carry-forward item %s skipped: %s", src.pk, err)
                    continue
                generate_action_reference(new_item)
                new_item.save()
                if src.owner_id is not None:
                    ActionItemAssignee.objects.get_or_create(
                        action_item=new_item,
                        user_id=src.owner_id,
                        defaults={"is_primary": True, "is_supporting": False},
                    )
                for assign in src.assignees.select_related("user").all():
                    if assign.user_id == src.owner_id:
                        continue
                    ActionItemAssignee.objects.get_or_create(
                        action_item=new_item,
                        user_id=assign.user_id,
                        defaults={"is_primary": assign.is_primary, "is_supporting": True},
                    )
                for upd in src.updates.all().order_by("created_at"):
                    carried_body = (
                        f"[Carried from {src.reference or 'source action'} — "
                        f"{upd.created_at:%Y-%m-%d %H:%M}] {upd.body}"
                    )
                    ActionItemUpdate.objects.create(
                        action_item=new_item,
                        author=upd.author,
                        status_snapshot=STATUS_OPEN,
                        progress_snapshot=0,
                        body=carried_body,
                    )
                ActionItemCarryForwardLink.objects.create(
                    source_item=src,
                    new_item=new_item,
                    target_meeting=target_meeting,
                    target_scope_key=target_scope_key,
                    carried_by=by_user,
                    reason=reason.strip() if reason else "",
                )
                log_audit_event(
                    record_type="action_items.actionitem",
                    record=new_item,
                    action=AuditLog.ACTION_CARRY_FORWARD,
                    user=by_user,
                    reason=reason or f"Carried forward from {src.reference or 'source'}.",
                )
                created.append(new_item)
    except IntegrityError as err:
        logger.exception("Carry-forward rolled back: %s", err)
        raise ValidationError("Carry-forward aborted due to a conflict. Try again.") from err
    return created


PRIORITY_WEIGHT = {
    PRIORITY_URGENT: 0,
    PRIORITY_HIGH: 1,
    PRIORITY_MEDIUM: 2,
    PRIORITY_LOW: 3,
}


def overdue_action_items_queryset(
    user: AuthUser | None = None,
    *,
    department=None,
    limit: int | None = None,
):
    today = timezone.now().date()
    qs = ActionItem.objects.filter(
        due_date__lt=today,
        status__in=ACTIVE_STATUSES,
    ).select_related("owner", "department", "source_meeting")
    if user is not None and not getattr(user, "is_superuser", False):
        from apps.core.permissions import ACTION_VIEWER_ROLES

        if user.has_role(*ACTION_VIEWER_ROLES):
            pass
        else:
            qs = qs.filter(
                pk__in=ActionItemAssignee.objects.filter(user=user).values_list(
                    "action_item_id", flat=True
                )
            ) | qs.filter(owner_id=getattr(user, "pk", None))
    if department is not None:
        qs = qs.filter(department=department)
    qs = qs.order_by("due_date", "priority")
    if limit is not None:
        qs = qs[:limit]
    return qs


def dashboard_action_counts(user: AuthUser | None) -> dict[str, int | date | None]:
    counts: dict[str, int | date | None] = {
        "total_open": 0,
        "assigned_me": 0,
        "overdue": 0,
        "due_this_week": 0,
        "completed_this_week": 0,
        "today": timezone.now().date(),
    }
    today = timezone.now().date()
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)
    try:
        base = ActionItem.objects.all()
        counts["total_open"] = int(base.filter(status__in=ACTIVE_STATUSES).count())
        if user is not None:
            user_pk = getattr(user, "pk", None)
            mine = base.filter(
                pk__in=ActionItemAssignee.objects.filter(user_id=user_pk).values_list(
                    "action_item_id", flat=True
                )
            ) | base.filter(owner_id=user_pk)
            counts["assigned_me"] = int(mine.filter(status__in=ACTIVE_STATUSES).count())
            counts["overdue"] = int(
                mine.filter(status__in=ACTIVE_STATUSES, due_date__lt=today).count()
            )
            counts["due_this_week"] = int(
                mine.filter(
                    status__in=ACTIVE_STATUSES, due_date__range=(week_start, week_end)
                ).count()
            )
            counts["completed_this_week"] = int(
                mine.filter(
                    status=STATUS_COMPLETED, completed_at__date__range=(week_start, week_end)
                ).count()
            )
    except Exception as err:
        logger.warning("dashboard_action_counts failed: %s", err)
    return counts
