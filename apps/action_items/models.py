from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator
from django.db import models
from django.utils import timezone

from apps.core.models import TimeStampedModel

STATUS_OPEN = "OPEN"
STATUS_IN_PROGRESS = "IN_PROGRESS"
STATUS_BLOCKED = "BLOCKED"
STATUS_UNDER_REVIEW = "UNDER_REVIEW"
STATUS_COMPLETED = "COMPLETED"
STATUS_CANCELLED = "CANCELLED"
STATUS_REOPENED = "REOPENED"

STATUS_CHOICES = [
    (STATUS_OPEN, "Open"),
    (STATUS_IN_PROGRESS, "In Progress"),
    (STATUS_BLOCKED, "Blocked"),
    (STATUS_UNDER_REVIEW, "Under Review"),
    (STATUS_COMPLETED, "Completed"),
    (STATUS_CANCELLED, "Cancelled"),
    (STATUS_REOPENED, "Reopened"),
]

ACTIVE_STATUSES = {
    STATUS_OPEN,
    STATUS_IN_PROGRESS,
    STATUS_BLOCKED,
    STATUS_UNDER_REVIEW,
    STATUS_REOPENED,
}
TERMINAL_STATUSES = {STATUS_COMPLETED, STATUS_CANCELLED}
NON_EDITABLE_STATUSES = TERMINAL_STATUSES.copy()


PRIORITY_LOW = "LOW"
PRIORITY_MEDIUM = "MED"
PRIORITY_HIGH = "HIGH"
PRIORITY_URGENT = "URG"

PRIORITY_CHOICES = [
    (PRIORITY_LOW, "Low"),
    (PRIORITY_MEDIUM, "Medium"),
    (PRIORITY_HIGH, "High"),
    (PRIORITY_URGENT, "Urgent"),
]

PRIORITY_ORDER = [PRIORITY_URGENT, PRIORITY_HIGH, PRIORITY_MEDIUM, PRIORITY_LOW]


def _action_item_attachment_path(instance, filename: str) -> str:
    item_id = str(getattr(getattr(instance, "action_item", None), "pk", "unknown"))
    ym = timezone.now().strftime("%Y%m")
    return f"action_item_attachments/{item_id}/action/{ym}/{filename}"


def _action_update_attachment_path(instance, filename: str) -> str:
    item_id = str(
        getattr(getattr(getattr(instance, "update", None), "action_item", None), "pk", "unknown")
    )
    ym = timezone.now().strftime("%Y%m")
    return f"action_item_attachments/{item_id}/updates/{ym}/{filename}"


class ActionItem(TimeStampedModel):
    reference = models.CharField(
        max_length=50,
        unique=True,
        db_index=True,
        blank=True,
        editable=False,
        help_text="Auto-generated reference, e.g. ACT-2026-0012.",
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    source_meeting = models.ForeignKey(
        "meetings.Meeting",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="action_items",
    )
    source_agenda_item = models.ForeignKey(
        "meetings.AgendaItem",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="action_items",
    )
    department = models.ForeignKey(
        "accounts.Department",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="action_items",
    )
    created_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="action_items_created",
    )
    last_modified_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="action_items_modified",
    )
    owner = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="owned_action_items",
        help_text="User responsible for the outcome (same as primary assignee usually).",
    )
    priority = models.CharField(
        max_length=8,
        choices=PRIORITY_CHOICES,
        default=PRIORITY_MEDIUM,
        db_index=True,
    )
    status = models.CharField(
        max_length=16,
        choices=STATUS_CHOICES,
        default=STATUS_OPEN,
        db_index=True,
    )
    progress_pct = models.PositiveSmallIntegerField(
        default=0,
        validators=[MaxValueValidator(100)],
        help_text="0-100 progress (auto-set 100 on COMPLETED).",
    )
    due_date = models.DateField(null=True, blank=True, db_index=True)
    blockers = models.TextField(
        blank=True,
        help_text="Current blockers preventing progress.",
    )
    next_steps = models.TextField(
        blank=True,
        help_text="Next steps to move this item forward.",
    )
    carried_forward_from = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="carried_forward_to",
    )
    completed_at = models.DateTimeField(null=True, blank=True)
    reopened_count = models.PositiveIntegerField(default=0)

    class Meta(TimeStampedModel.Meta):
        verbose_name_plural = "Action Items"
        ordering = [
            models.Case(
                *[models.When(priority=p, then=idx) for idx, p in enumerate(PRIORITY_ORDER)],
                default=99,
            ),
            "-due_date",
            "-created_at",
        ]
        indexes = [
            models.Index(fields=["status", "priority", "due_date"]),
            models.Index(fields=["department", "status", "due_date"]),
            models.Index(fields=["owner", "status", "due_date"]),
            models.Index(fields=["source_meeting", "status"]),
        ]

    def __str__(self) -> str:
        return f"{self.reference or 'DRAFT'} — {self.title}"

    def clean(self):
        if self.progress_pct < 0 or self.progress_pct > 100:
            raise ValidationError("Progress percentage must be between 0 and 100.")
        if self.status == STATUS_COMPLETED and self.progress_pct < 100:
            raise ValidationError("Completed items must have 100% progress.")
        if self.status == STATUS_COMPLETED and self.blockers and str(self.blockers).strip():
            raise ValidationError("Completed items must not have unresolved blockers.")

    @property
    def is_editable(self) -> bool:
        return self.status not in NON_EDITABLE_STATUSES

    @property
    def is_overdue(self) -> bool:
        if not self.due_date or self.status in TERMINAL_STATUSES:
            return False
        return self.due_date < timezone.now().date()

    @property
    def overdue_age_days(self) -> int:
        if not self.is_overdue:
            return 0
        return max(0, (timezone.now().date() - self.due_date).days)

    @property
    def primary_assignee(self):
        primary = self.assignees.filter(is_primary=True).select_related("user").first()
        return primary.user if primary else None

    @property
    def supporting_users(self):
        return [a.user for a in self.assignees.filter(is_supporting=True).select_related("user")]


class ActionItemAssignee(TimeStampedModel):
    action_item = models.ForeignKey(
        ActionItem,
        on_delete=models.CASCADE,
        related_name="assignees",
    )
    user = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="action_item_assignments",
    )
    is_primary = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Primary assignee owns the deliverable.",
    )
    is_supporting = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Supporting user (helps but not the owner).",
    )
    notes = models.CharField(max_length=255, blank=True)

    class Meta(TimeStampedModel.Meta):
        unique_together = [["action_item", "user"]]
        ordering = ["action_item__created_at", "-is_primary", "-is_supporting", "user__username"]

    def __str__(self) -> str:
        parts = []
        if self.is_primary:
            parts.append("Primary")
        if self.is_supporting:
            parts.append("Supporting")
        suffix = f" ({'/'.join(parts)})" if parts else ""
        return f"{self.user.get_display_name()} on {self.action_item.reference}{suffix}"

    def clean(self):
        if not self.is_primary and not self.is_supporting:
            self.is_supporting = True
        if self.is_primary and self.is_supporting:
            raise ValidationError("A user cannot be both primary and supporting at the same time.")
        if not self.user.is_active:
            raise ValidationError(f"{self.user.get_display_name()} is inactive.")


class ActionItemUpdate(TimeStampedModel):
    action_item = models.ForeignKey(
        ActionItem,
        on_delete=models.CASCADE,
        related_name="updates",
    )
    author = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="action_updates",
    )
    status_snapshot = models.CharField(
        max_length=16,
        choices=STATUS_CHOICES,
        blank=True,
        help_text="Item status at the time of this update.",
    )
    progress_snapshot = models.PositiveSmallIntegerField(
        default=0,
        validators=[MaxValueValidator(100)],
    )
    body = models.TextField(blank=False)
    attachment = models.FileField(
        upload_to=_action_update_attachment_path,
        blank=True,
        null=True,
    )

    class Meta(TimeStampedModel.Meta):
        verbose_name_plural = "Action Item Updates"
        ordering = ["action_item__created_at", "-created_at"]

    def __str__(self) -> str:
        stamp = self.status_snapshot or self.action_item.status
        who = self.author.get_display_name() if self.author else "System"
        return f"[{stamp}] {who} @ {self.created_at:%Y-%m-%d %H:%M}"


class ActionItemAttachment(TimeStampedModel):
    action_item = models.ForeignKey(
        ActionItem,
        on_delete=models.CASCADE,
        related_name="attachments",
    )
    uploaded_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="action_item_attachments",
    )
    file = models.FileField(upload_to=_action_item_attachment_path)
    caption = models.CharField(max_length=255, blank=True)

    class Meta(TimeStampedModel.Meta):
        ordering = ["action_item__created_at", "-created_at"]

    def __str__(self) -> str:
        name = (self.caption or self.file.name or "Attachment")[:60]
        return f"{name} @ {self.action_item.reference}"

    @property
    def filename(self) -> str:
        try:
            return self.file.name.split("/")[-1]
        except (AttributeError, IndexError):
            return self.caption or "attachment"


class ActionItemStatusHistory(TimeStampedModel):
    action_item = models.ForeignKey(
        ActionItem,
        on_delete=models.CASCADE,
        related_name="status_history",
    )
    from_status = models.CharField(max_length=16, choices=STATUS_CHOICES, blank=True)
    to_status = models.CharField(max_length=16, choices=STATUS_CHOICES)
    progress_before = models.PositiveSmallIntegerField(
        default=0,
        validators=[MaxValueValidator(100)],
    )
    progress_after = models.PositiveSmallIntegerField(
        default=0,
        validators=[MaxValueValidator(100)],
    )
    transitioned_at = models.DateTimeField(default=timezone.now, db_index=True)
    transitioned_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="action_item_transitions",
    )
    reason = models.TextField(blank=True)

    class Meta(TimeStampedModel.Meta):
        verbose_name_plural = "Action Item Status Histories"
        ordering = ["action_item__created_at", "-transitioned_at"]
        indexes = [
            models.Index(fields=["action_item", "transitioned_at"]),
        ]

    def __str__(self) -> str:
        return (
            f"{self.action_item.reference or 'ITEM'} {self.from_status or '-'} → {self.to_status}"
            f" @ {self.transitioned_at:%Y-%m-%d %H:%M}"
        )


class ActionItemCarryForwardLink(TimeStampedModel):
    source_item = models.ForeignKey(
        ActionItem,
        on_delete=models.CASCADE,
        related_name="carried_forward_links",
    )
    new_item = models.ForeignKey(
        ActionItem,
        on_delete=models.CASCADE,
        related_name="carry_forward_sources",
    )
    target_meeting = models.ForeignKey(
        "meetings.Meeting",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="carry_forward_links",
    )
    target_scope_key = models.CharField(
        max_length=100,
        default="default",
        db_index=True,
        help_text="Hashable key distinguishing different carry-forwards (e.g. include_completed flag).",
    )
    carried_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="carried_forward_actions",
    )
    carried_at = models.DateTimeField(default=timezone.now, db_index=True)
    reason = models.TextField(blank=True)

    class Meta(TimeStampedModel.Meta):
        verbose_name_plural = "Action Item Carry Forward Links"
        unique_together = [["source_item", "target_meeting", "target_scope_key"]]
        ordering = ["-carried_at"]

    def __str__(self) -> str:
        src = self.source_item.reference or "SRC"
        dst = self.new_item.reference or "DST"
        return f"{src} → {dst}"
