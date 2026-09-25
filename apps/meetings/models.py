from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.text import slugify

from apps.core.models import BaseNamedModel, TimeStampedModel

STATUS_DRAFT = "DRAFT"
STATUS_OPEN_UPDATES = "OPEN_UPDATES"
STATUS_AGENDA_FINALIZED = "AGENDA_FINALIZED"
STATUS_IN_PROGRESS = "IN_PROGRESS"
STATUS_FOR_REVIEW = "FOR_REVIEW"
STATUS_RETURNED_FOR_CORRECTION = "RETURNED"
STATUS_APPROVED = "APPROVED"
STATUS_PUBLISHED = "PUBLISHED"
STATUS_CLOSED = "CLOSED"
STATUS_ARCHIVED = "ARCHIVED"

STATUS_CHOICES = [
    (STATUS_DRAFT, "Draft"),
    (STATUS_OPEN_UPDATES, "Open for Department Updates"),
    (STATUS_AGENDA_FINALIZED, "Agenda Finalized"),
    (STATUS_IN_PROGRESS, "Meeting In Progress"),
    (STATUS_FOR_REVIEW, "For Review"),
    (STATUS_RETURNED_FOR_CORRECTION, "Returned for Correction"),
    (STATUS_APPROVED, "Approved"),
    (STATUS_PUBLISHED, "Published"),
    (STATUS_CLOSED, "Closed"),
    (STATUS_ARCHIVED, "Archived"),
]

NON_EDITABLE_STATUSES = {STATUS_APPROVED, STATUS_PUBLISHED, STATUS_CLOSED, STATUS_ARCHIVED}

ITEM_STATUS_TO_BE_DISCUSSED = "TBD"
ITEM_STATUS_CARRIED_FORWARD = "CARRIED"
ITEM_STATUS_IN_PROGRESS = "IN_PROGRESS"
ITEM_STATUS_DECIDED = "DECIDED"
ITEM_STATUS_WITHDRAWN = "WITHDRAWN"
ITEM_STATUS_CHOICES = [
    (ITEM_STATUS_TO_BE_DISCUSSED, "To Be Discussed"),
    (ITEM_STATUS_CARRIED_FORWARD, "Carried Forward"),
    (ITEM_STATUS_IN_PROGRESS, "In Progress"),
    (ITEM_STATUS_DECIDED, "Decided"),
    (ITEM_STATUS_WITHDRAWN, "Withdrawn"),
]

RSVP_PENDING = "PENDING"
RSVP_YES = "YES"
RSVP_NO = "NO"
RSVP_MAYBE = "MAYBE"
RSVP_CHOICES = [
    (RSVP_PENDING, "Pending"),
    (RSVP_YES, "Yes"),
    (RSVP_NO, "No"),
    (RSVP_MAYBE, "Maybe"),
]


def _meeting_attachment_path(instance, filename: str) -> str:
    meeting_id = str(getattr(getattr(instance, "meeting", None), "pk", "unknown"))
    ym = timezone.now().strftime("%Y%m")
    return f"meeting_attachments/{meeting_id}/meeting/{ym}/{filename}"


def _agenda_attachment_path(instance, filename: str) -> str:
    item = getattr(instance, "item", None)
    meeting_id = "unknown"
    if item is not None:
        meeting_id = str(getattr(getattr(item, "meeting", None), "pk", meeting_id))
    ym = timezone.now().strftime("%Y%m")
    return f"meeting_attachments/{meeting_id}/agenda/{ym}/{filename}"


class MeetingType(BaseNamedModel):
    code = models.CharField(max_length=20, unique=True, blank=True, db_index=True)
    description = models.TextField(blank=True)
    default_duration_minutes = models.PositiveIntegerField(default=60)
    requires_chair_approval = models.BooleanField(default=False)

    class Meta(BaseNamedModel.Meta):
        verbose_name_plural = "Meeting Types"

    def save(self, *args, **kwargs):
        if not self.code:
            base = slugify(self.name or "MTG")[:20].upper()
            base = base.replace("-", "") or "MTG"
            self.code = base[:20]
        super().save(*args, **kwargs)


class Meeting(TimeStampedModel):
    type = models.ForeignKey(
        MeetingType,
        on_delete=models.PROTECT,
        related_name="meetings",
    )
    reference = models.CharField(
        max_length=50,
        unique=True,
        db_index=True,
        blank=True,
        editable=False,
        help_text="Auto-generated human-friendly reference.",
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    start_at = models.DateTimeField(help_text="Local meeting start time (timezone-aware).")
    end_at = models.DateTimeField(
        help_text="Local meeting end time (timezone-aware).",
    )
    location = models.CharField(max_length=255, blank=True)
    department = models.ForeignKey(
        "accounts.Department",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="meetings",
    )
    chair = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="chaired_meetings",
    )
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT, db_index=True
    )
    is_locked = models.BooleanField(
        default=False,
        help_text="If locked, only System/Management Administrator can unlock or transition.",
    )
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="meetings_created",
    )
    last_modified_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="meetings_modified",
    )
    published_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    archived_at = models.DateTimeField(null=True, blank=True)

    class Meta(TimeStampedModel.Meta):
        verbose_name_plural = "Meetings"
        ordering = ["-start_at"]
        indexes = [
            models.Index(fields=["status", "start_at"]),
            models.Index(fields=["type", "start_at"]),
            models.Index(fields=["department", "start_at"]),
            models.Index(fields=["chair", "start_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.reference or 'DRAFT'} — {self.title}"

    def clean(self):
        if self.start_at and self.end_at and self.end_at <= self.start_at:
            raise ValidationError("End time must be after start time.")

    @property
    def is_editable(self) -> bool:
        return self.status not in NON_EDITABLE_STATUSES

    @property
    def duration_minutes(self) -> int | None:
        if self.start_at and self.end_at:
            return int(max(0, (self.end_at - self.start_at).total_seconds() // 60))
        return None


class MeetingStatusHistory(TimeStampedModel):
    meeting = models.ForeignKey(
        Meeting,
        on_delete=models.CASCADE,
        related_name="status_history",
    )
    from_status = models.CharField(max_length=20, choices=STATUS_CHOICES, blank=True)
    to_status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    transitioned_at = models.DateTimeField(default=timezone.now, db_index=True)
    transitioned_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="meeting_transitions",
    )
    reason = models.TextField(blank=True)

    class Meta(TimeStampedModel.Meta):
        verbose_name_plural = "Meeting Status Histories"
        ordering = ["meeting_id", "-transitioned_at"]
        indexes = [
            models.Index(fields=["meeting", "transitioned_at"]),
        ]

    def __str__(self) -> str:
        return (
            f"{self.meeting.reference} {self.from_status or '-'} → {self.to_status}"
            f" @ {self.transitioned_at:%Y-%m-%d %H:%M}"
        )


class MeetingAttendance(TimeStampedModel):
    meeting = models.ForeignKey(
        Meeting,
        on_delete=models.CASCADE,
        related_name="attendance",
    )
    user = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="meeting_attendances",
    )
    is_invited = models.BooleanField(default=True, db_index=True)
    is_attended = models.BooleanField(default=False, db_index=True)
    rsvp_status = models.CharField(max_length=10, choices=RSVP_CHOICES, default=RSVP_PENDING)
    arrived_at = models.DateTimeField(null=True, blank=True)
    departed_at = models.DateTimeField(null=True, blank=True)
    role_at_meeting = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)

    class Meta(TimeStampedModel.Meta):
        unique_together = [["meeting", "user"]]
        ordering = ["meeting__start_at", "user__username"]
        indexes = [
            models.Index(fields=["meeting", "is_invited"]),
            models.Index(fields=["meeting", "is_attended"]),
        ]

    def __str__(self) -> str:
        invited = "invited" if self.is_invited else "not-invited"
        attended = "attended" if self.is_attended else "absent"
        return f"{self.user} at {self.meeting.reference} ({invited}/{attended})"

    def clean(self):
        if self.departed_at and self.arrived_at and self.departed_at < self.arrived_at:
            raise ValidationError("Departure time cannot be before arrival time.")
        if self.is_attended and not self.is_invited:
            pass  # Walk-ins allowed, no error


class AgendaCategory(BaseNamedModel):
    order = models.PositiveIntegerField(default=0, db_index=True)
    description = models.TextField(blank=True)
    scope_department = models.ForeignKey(
        "accounts.Department",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="agenda_categories",
    )

    class Meta(BaseNamedModel.Meta):
        verbose_name_plural = "Agenda Categories"
        ordering = ["order", "name"]


class AgendaItem(TimeStampedModel):
    meeting = models.ForeignKey(
        Meeting,
        on_delete=models.CASCADE,
        related_name="agenda_items",
    )
    category = models.ForeignKey(
        AgendaCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="agenda_items",
    )
    order = models.PositiveIntegerField(default=0, db_index=True)
    title = models.CharField(max_length=255)
    discussion = models.TextField(blank=True)
    decision = models.TextField(blank=True)
    item_status = models.CharField(
        max_length=16,
        choices=ITEM_STATUS_CHOICES,
        default=ITEM_STATUS_TO_BE_DISCUSSED,
        db_index=True,
    )
    owner = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="owned_agenda_items",
    )
    department = models.ForeignKey(
        "accounts.Department",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="agenda_items",
    )
    is_confidential = models.BooleanField(default=False, db_index=True)
    parent_item = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="children",
    )
    carried_forward_from = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="carried_to_items",
    )
    time_allocated_minutes = models.PositiveIntegerField(default=0, blank=True)
    notes = models.TextField(blank=True)

    class Meta(TimeStampedModel.Meta):
        verbose_name_plural = "Agenda Items"
        ordering = ["meeting__start_at", "order", "created_at"]
        unique_together = [["meeting", "order"]]
        indexes = [
            models.Index(fields=["meeting", "category", "order"]),
            models.Index(fields=["meeting", "is_confidential"]),
            models.Index(fields=["owner", "item_status"]),
        ]

    def __str__(self) -> str:
        return f"#{self.order} {self.title}"


class MeetingAttachment(TimeStampedModel):
    meeting = models.ForeignKey(
        Meeting,
        on_delete=models.CASCADE,
        related_name="attachments",
    )
    file = models.FileField(upload_to=_meeting_attachment_path, max_length=255)
    display_name = models.CharField(max_length=255, blank=True)
    description = models.TextField(blank=True)
    uploaded_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="meeting_attachments_uploaded",
    )
    is_confidential = models.BooleanField(default=False, db_index=True)
    is_active = models.BooleanField(default=True)

    class Meta(TimeStampedModel.Meta):
        verbose_name_plural = "Meeting Attachments"
        ordering = ["meeting__start_at", "created_at"]

    def __str__(self) -> str:
        return self.display_name or self.file.name.split("/")[-1]


class AgendaItemAttachment(TimeStampedModel):
    item = models.ForeignKey(
        AgendaItem,
        on_delete=models.CASCADE,
        related_name="attachments",
    )
    file = models.FileField(upload_to=_agenda_attachment_path, max_length=255)
    display_name = models.CharField(max_length=255, blank=True)
    description = models.TextField(blank=True)
    uploaded_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="agenda_attachments_uploaded",
    )
    is_confidential = models.BooleanField(default=False, db_index=True)
    is_active = models.BooleanField(default=True)

    class Meta(TimeStampedModel.Meta):
        verbose_name_plural = "Agenda Item Attachments"
        ordering = ["item__meeting__start_at", "item__order", "created_at"]

    def __str__(self) -> str:
        return self.display_name or self.file.name.split("/")[-1]


SUBMISSION_NOT_STARTED = "NOT_STARTED"
SUBMISSION_IN_PROGRESS = "IN_PROGRESS"
SUBMISSION_SUBMITTED = "SUBMITTED"
SUBMISSION_RETURNED = "RETURNED"
SUBMISSION_ACCEPTED = "ACCEPTED"
SUBMISSION_STATUS_CHOICES = [
    (SUBMISSION_NOT_STARTED, "Not Started"),
    (SUBMISSION_IN_PROGRESS, "In Progress"),
    (SUBMISSION_SUBMITTED, "Submitted"),
    (SUBMISSION_RETURNED, "Returned for Correction"),
    (SUBMISSION_ACCEPTED, "Accepted by Reviewer"),
]

SECTION_OPENING_REMARKS = "OPENING"
SECTION_DEPT_UPDATES = "DEPT_UPDATES"
SECTION_ACTION_ITEMS = "ACTION_ITEMS"
SECTION_SALES_PERFORMANCE = "SALES"
SECTION_OLD_BUSINESS = "OLD_BUSINESS"
SECTION_NEW_BUSINESS = "NEW_BUSINESS"
SECTION_OTHER = "OTHER"
SECTION_TYPE_CHOICES = [
    (SECTION_OPENING_REMARKS, "Opening Remarks"),
    (SECTION_DEPT_UPDATES, "Department Updates"),
    (SECTION_ACTION_ITEMS, "Action Items Review"),
    (SECTION_SALES_PERFORMANCE, "Sales Performance"),
    (SECTION_OLD_BUSINESS, "Old Business"),
    (SECTION_NEW_BUSINESS, "New Business"),
    (SECTION_OTHER, "Other Topics"),
]

SNAPSHOT_TRIGGER_SUBMIT = "SUBMIT"
SNAPSHOT_TRIGGER_APPROVE = "APPROVE"
SNAPSHOT_TRIGGER_PUBLISH = "PUBLISH"
SNAPSHOT_TRIGGER_MANUAL = "MANUAL"
SNAPSHOT_TRIGGER_CHOICES = [
    (SNAPSHOT_TRIGGER_SUBMIT, "Submitted for Review"),
    (SNAPSHOT_TRIGGER_APPROVE, "Approved"),
    (SNAPSHOT_TRIGGER_PUBLISH, "Published"),
    (SNAPSHOT_TRIGGER_MANUAL, "Manual Snapshot"),
]


class MinutesSectionSpec(TimeStampedModel):
    meeting_type = models.ForeignKey(
        MeetingType,
        on_delete=models.CASCADE,
        related_name="section_specs",
    )
    section_type = models.CharField(max_length=20, choices=SECTION_TYPE_CHOICES)
    order = models.PositiveIntegerField(default=0, db_index=True)
    name = models.CharField(max_length=128)
    is_required = models.BooleanField(default=True)
    description = models.TextField(blank=True)

    class Meta(TimeStampedModel.Meta):
        verbose_name_plural = "Minutes Section Specs"
        ordering = ["meeting_type_id", "order", "name"]
        unique_together = [["meeting_type", "section_type"]]
        indexes = [
            models.Index(fields=["meeting_type", "order"]),
        ]

    def __str__(self) -> str:
        flag = "R" if self.is_required else "O"
        return f"[{flag}] {self.meeting_type.code} #{self.order} {self.name}"


class DepartmentSubmission(TimeStampedModel):
    meeting = models.ForeignKey(
        Meeting,
        on_delete=models.CASCADE,
        related_name="department_submissions",
    )
    department = models.ForeignKey(
        "accounts.Department",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="meeting_submissions",
    )
    contributor = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    submission_state = models.CharField(
        max_length=20,
        choices=SUBMISSION_STATUS_CHOICES,
        default=SUBMISSION_NOT_STARTED,
        db_index=True,
    )
    last_updated_at = models.DateTimeField(null=True, blank=True)
    last_submitted_at = models.DateTimeField(null=True, blank=True)
    submitted_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    missing_info = models.TextField(blank=True)
    management_remarks = models.TextField(blank=True)
    notes = models.TextField(blank=True)

    class Meta(TimeStampedModel.Meta):
        verbose_name_plural = "Department Submissions"
        ordering = ["meeting__start_at", "department__name"]
        unique_together = [["meeting", "department"]]
        indexes = [
            models.Index(fields=["meeting", "submission_state"]),
            models.Index(fields=["department", "submission_state"]),
        ]

    def __str__(self) -> str:
        dept = self.department.name if self.department else "(cross)"
        return f"{self.meeting.reference} · {dept} · {self.submission_state}"


class ActionItemLink(TimeStampedModel):
    agenda_item = models.ForeignKey(
        AgendaItem,
        on_delete=models.CASCADE,
        related_name="action_item_links",
    )
    action_item = models.ForeignKey(
        "action_items.ActionItem",
        on_delete=models.CASCADE,
        related_name="agenda_links",
    )
    created_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta(TimeStampedModel.Meta):
        verbose_name_plural = "Action Item Links"
        ordering = ["agenda_item__meeting__start_at", "agenda_item__order"]
        unique_together = [["agenda_item", "action_item"]]
        indexes = [
            models.Index(fields=["agenda_item", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"#{self.agenda_item.order} → AI {self.action_item.pk}"


class ApprovedMeetingSnapshot(TimeStampedModel):
    meeting = models.ForeignKey(
        Meeting,
        on_delete=models.CASCADE,
        related_name="approved_snapshots",
    )
    version = models.PositiveSmallIntegerField(db_index=True)
    trigger = models.CharField(
        max_length=10,
        choices=SNAPSHOT_TRIGGER_CHOICES,
        default=SNAPSHOT_TRIGGER_MANUAL,
        db_index=True,
    )
    payload = models.JSONField(
        default=dict,
        help_text="Immutable serialized meeting content at snapshot time.",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    published_at = models.DateTimeField(null=True, blank=True)
    published_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    notes = models.TextField(blank=True)

    class Meta(TimeStampedModel.Meta):
        verbose_name_plural = "Approved Meeting Snapshots"
        ordering = ["meeting_id", "-version"]
        unique_together = [["meeting", "version"]]
        indexes = [
            models.Index(fields=["meeting", "trigger", "version"]),
        ]

    def __str__(self) -> str:
        return f"{self.meeting.reference or 'DRAFT'} v{self.version} ({self.trigger})"

    def clean(self):
        super().clean()
        if not self.payload:
            self.payload = {}
        if self.pk:
            from django.core.exceptions import ValidationError as VE

            try:
                current = ApprovedMeetingSnapshot.objects.values(
                    "meeting_id", "version", "trigger", "payload", "approved_at", "approved_by_id"
                ).get(pk=self.pk)
            except ApprovedMeetingSnapshot.DoesNotExist:
                return
            locked_fields = (
                "meeting_id",
                "version",
                "trigger",
                "payload",
                "approved_at",
                "approved_by_id",
            )
            for f in locked_fields:
                prior = current[f]
                if f.endswith("_id"):
                    prior = current[f]
                    rel_name = f[:-3]
                    obj = getattr(self, rel_name, None)
                    new_val = getattr(obj, "pk", None) if obj is not None else None
                    if prior != new_val:
                        raise VE({f: f"ApprovedMeetingSnapshot.{f} is immutable after creation."})
                elif f == "payload":
                    prior_json = current.get("payload") or {}
                    new_json = self.payload or {}
                    if prior_json != new_json:
                        raise VE({f: f"ApprovedMeetingSnapshot.{f} is immutable after creation."})
                elif prior != getattr(self, f, None):
                    raise VE({f: f"ApprovedMeetingSnapshot.{f} is immutable after creation."})

    def save(self, *args, **kwargs):
        force_insert = kwargs.get("force_insert", False)
        if self.pk and not force_insert:
            self.full_clean()
        super().save(*args, **kwargs)
