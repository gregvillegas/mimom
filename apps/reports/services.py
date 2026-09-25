from __future__ import annotations

import re
from datetime import UTC
from typing import TYPE_CHECKING

from django.utils import timezone
from django.utils.html import escape, strip_tags
from django.utils.safestring import SafeString, mark_safe

if TYPE_CHECKING:
    from datetime import date, datetime

    from apps.audit.models import AuditLog
    from apps.meetings.models import ApprovedMeetingSnapshot, DepartmentSubmission, Meeting
    from apps.sales_updates.models import GroupPerformanceSnapshot, ReportingPeriod

_ALLOWED_TAGS_RE = re.compile(
    r"</?(?:p|br\s*/?|strong|em|b|i|ul|ol|li)\s*/?>",
    re.IGNORECASE,
)

_DANGEROUS_PATTERNS = [
    re.compile(r"<script\b[^>]*>.*?</script>", re.IGNORECASE | re.DOTALL),
    re.compile(r"</?iframe\b[^>]*>", re.IGNORECASE),
    re.compile(r"</?style\b[^>]*>.*?</style>", re.IGNORECASE | re.DOTALL),
    re.compile(r"</?svg\b[^>]*>.*?</svg>", re.IGNORECASE | re.DOTALL),
    re.compile(r"\bon\w+\s*=\s*\"[^\"]*\"", re.IGNORECASE),
    re.compile(r"\bon\w+\s*=\s*'[^']*'", re.IGNORECASE),
    re.compile(r"srcdoc\s*=\s*\"[^\"]*\"", re.IGNORECASE),
    re.compile(r"srcdoc\s*=\s*'[^']*'", re.IGNORECASE),
    re.compile(r"javascript\s*:", re.IGNORECASE),
]

_FILENAME_BAD_CHARS = re.compile(r"[\\/?*:|\"<>]")

_REPORT_SLUG_PREFIXES: dict[str, str] = {
    "meeting_minutes": "MIMOM_MeetingMinutes",
    "action_item_register": "MIMOM_ActionItemRegister",
    "open_action_items": "MIMOM_OpenActionItems",
    "overdue_action_items": "MIMOM_OverdueActionItems",
    "department_action_items": "MIMOM_DeptActionItems",
    "meeting_readiness": "MIMOM_MeetingReadiness",
    "sales_performance": "MIMOM_SalesPerformance",
    "weekly_commitments": "MIMOM_WeeklyCommitments",
    "meeting_history": "MIMOM_MeetingHistory",
    "authorized_audit_report": "MIMOM_AuditReport",
}


def _slug_prefix(report_slug: str) -> str:
    return _REPORT_SLUG_PREFIXES.get(report_slug, f"MIMOM_{report_slug}")


def meaningful_report_filename(
    report_slug: str,
    suffix: str,
    meeting: Meeting | None = None,
    snapshot: ApprovedMeetingSnapshot | None = None,
    period: ReportingPeriod | None = None,
    user=None,
    timestamp: datetime | None = None,
) -> str:
    parts: list[str] = [_slug_prefix(report_slug)]

    if meeting is not None:
        ref = getattr(meeting, "reference", None)
        if ref:
            parts.append(str(ref))

    if snapshot is not None:
        version = getattr(snapshot, "version", None)
        if version is not None:
            parts.append(f"v{version}")
        sref = getattr(getattr(snapshot, "meeting", None), "reference", None)
        if sref and not any(str(ref) == sref for ref in parts):
            parts.append(str(sref))

    if period is not None:
        pname = getattr(period, "name", None) or getattr(period, "code", None)
        if pname:
            parts.append(str(pname))

    ts = timestamp if timestamp is not None else timezone.now()
    try:
        tzutc = timezone.utc
    except AttributeError:
        tzutc = UTC
    parts.append(ts.astimezone(tzutc).strftime("%Y%m%d-%H%M%S"))

    joined = "_".join(str(p) for p in parts if p)
    cleaned = _FILENAME_BAD_CHARS.sub("_", joined)
    ext = suffix if suffix.startswith(".") else f".{suffix}"
    return f"{cleaned}{ext}"


def sanitize_html(html: str) -> SafeString:
    if html is None:
        return mark_safe("")
    text = str(html)

    for pattern in _DANGEROUS_PATTERNS:
        text = pattern.sub("", text)

    allowed_tokens: list[str] = []
    pos = 0
    for m in _ALLOWED_TAGS_RE.finditer(text):
        if m.start() > pos:
            allowed_tokens.append(escape(text[pos : m.start()]))
        allowed_tokens.append(m.group(0))
        pos = m.end()
    if pos < len(text):
        allowed_tokens.append(escape(text[pos:]))
    result = "".join(allowed_tokens)

    stripped = strip_tags(result)
    if stripped is None:
        return mark_safe("")
    fallback = escape(stripped)
    return mark_safe(result or fallback)


_MINUTES_REQUIRED_KEYS = 8


def minutes_payload(snapshot: ApprovedMeetingSnapshot) -> dict:
    payload = dict(snapshot.payload or {})

    if isinstance(payload, dict):
        key_count = len(payload)
    else:
        key_count = 0

    if key_count < _MINUTES_REQUIRED_KEYS:
        raise ValueError(
            f"snapshot.payload must contain at least {_MINUTES_REQUIRED_KEYS} keys, got {key_count}"
        )

    if isinstance(payload, dict):
        if "meeting_meta" in payload and "metadata" not in payload:
            payload["metadata"] = payload["meeting_meta"]
        if "approval_meta" in payload and "approval_metadata" not in payload:
            payload["approval_metadata"] = payload["approval_meta"]
        if "agenda_items" in payload and "agenda_sections" not in payload:
            payload["agenda_sections"] = payload["agenda_items"]
        if "department_updates" in payload and "departments" not in payload:
            payload["departments"] = payload["department_updates"]
        if "sales_data" in payload and "sales_performance" not in payload:
            payload["sales_performance"] = payload["sales_data"]

        _TOP_LEVEL_DEFAULTS = [
            ("meeting_meta", {}),
            ("metadata", {}),
            ("approval_meta", {}),
            ("approval_metadata", {}),
            ("attendance", []),
            ("agenda_items", []),
            ("agenda_sections", []),
            ("discussions", []),
            ("decisions", []),
            ("action_items", []),
            ("sales_data", {}),
            ("sales_performance", {}),
            ("status_history", []),
            ("snapshots", []),
            ("department_updates", []),
            ("departments", []),
            ("sections", []),
        ]
        for key, default in _TOP_LEVEL_DEFAULTS:
            if key not in payload:
                payload[key] = default
        if isinstance(payload.get("meeting_meta"), dict):
            mm = payload["meeting_meta"]
            for src_key, dst_key in [
                ("meeting_type_name", "type_name"),
                ("meeting_type_name", "type"),
                ("meeting_type_code", "type_code"),
            ]:
                if src_key in mm and dst_key not in mm:
                    mm[dst_key] = mm[src_key]
            if "metadata" in payload and isinstance(payload.get("metadata"), dict):
                md = payload["metadata"]
                for src_key, dst_key in [
                    ("meeting_type_name", "type_name"),
                    ("meeting_type_name", "type"),
                    ("meeting_type_code", "type_code"),
                ]:
                    if src_key in md and dst_key not in md:
                        md[dst_key] = md[src_key]

        _ITEM_ALIASES = [
            ("category_name", "category"),
            ("department_name", "department"),
            ("owner_name", "owner"),
            ("discussion", "discussion_summary"),
            ("discussion", "summary"),
            ("item_status", "status"),
            ("item_status_label", "item_status"),
        ]
        for list_key in (
            "agenda_items",
            "agenda_sections",
            "discussions",
            "decisions",
            "action_items",
        ):
            items = payload.get(list_key)
            if isinstance(items, list):
                for it in items:
                    if isinstance(it, dict):
                        for src_key, dst_key in _ITEM_ALIASES:
                            if src_key in it and dst_key not in it:
                                it[dst_key] = it[src_key]

    def _walk(node):
        if isinstance(node, dict):
            return {k: _walk(v) for k, v in node.items()}
        if isinstance(node, list):
            return [_walk(item) for item in node]
        if isinstance(node, str):
            return sanitize_html(node)
        return node

    for top_key in ("agenda_sections", "sections"):
        if top_key in payload and isinstance(payload[top_key], list):
            for section in payload[top_key]:
                if not isinstance(section, dict):
                    continue
                for field in ("discussion", "decision", "discussion_summary", "summary"):
                    if field in section and isinstance(section[field], str):
                        section[field] = sanitize_html(section[field])
                for items_key in ("items", "agenda_items", "discussion_items"):
                    if items_key in section and isinstance(section[items_key], list):
                        for item in section[items_key]:
                            if not isinstance(item, dict):
                                continue
                            for field in (
                                "discussion",
                                "decision",
                                "discussion_summary",
                                "summary",
                                "notes",
                                "description",
                            ):
                                if field in item and isinstance(item[field], str):
                                    item[field] = sanitize_html(item[field])

    return _walk(payload)


def action_items_queryset(
    status: str | None = None,
    department=None,
    from_date: date | None = None,
    to_date: date | None = None,
):
    from apps.action_items.models import ActionItem

    qs = ActionItem.objects.select_related("owner", "department", "source_meeting")

    if status:
        qs = qs.filter(status=status)

    if department is not None:
        dept_pk = getattr(department, "pk", department)
        qs = qs.filter(department_id=dept_pk)

    if from_date is not None:
        qs = qs.filter(due_date__gte=from_date)
    if to_date is not None:
        qs = qs.filter(due_date__lte=to_date)

    return qs


def sales_period_rows(period: ReportingPeriod) -> dict:
    from apps.sales_updates.services import overall_period_totals

    return overall_period_totals(period)


def weekly_commitments_rows(snapshot: GroupPerformanceSnapshot) -> dict:
    from apps.sales_updates.services import weekly_commitment_totals

    return weekly_commitment_totals(snapshot)


def meeting_readiness_rows(meeting: Meeting) -> list[DepartmentSubmission]:
    from apps.accounts.models import Department
    from apps.meetings.models import SUBMISSION_STATUS_CHOICES, DepartmentSubmission

    submissions = list(
        DepartmentSubmission.objects.filter(meeting=meeting)
        .select_related("department", "contributor")
        .order_by("department__name")
    )

    status_label = dict(SUBMISSION_STATUS_CHOICES)
    existing_by_dept: dict[int, DepartmentSubmission] = {}
    for s in submissions:
        if s.department_id is not None:
            existing_by_dept[s.department_id] = s

    rows: list[DepartmentSubmission] = []
    for dept in Department.objects.filter(is_active=True).order_by("name"):
        if dept.pk in existing_by_dept:
            sub = existing_by_dept[dept.pk]
        else:
            sub = DepartmentSubmission(
                meeting=meeting,
                department=dept,
                submission_state="NOT_STARTED",
            )
        sub._state_label = status_label.get(sub.submission_state, sub.submission_state)
        rows.append(sub)
    return rows


def meeting_history_rows(user, limit: int = 50):
    from apps.meetings.models import ApprovedMeetingSnapshot, MeetingStatusHistory

    snapshots = ApprovedMeetingSnapshot.objects.select_related(
        "meeting", "approved_by", "published_by"
    ).order_by("-approved_at", "-created_at")[:limit]

    result: list[dict] = []
    for snap in snapshots:
        latest_transition = (
            MeetingStatusHistory.objects.filter(meeting=snap.meeting)
            .select_related("transitioned_by")
            .order_by("-transitioned_at")
            .first()
        )
        result.append(
            {
                "snapshot": snap,
                "meeting": snap.meeting,
                "reference": getattr(snap.meeting, "reference", None),
                "title": getattr(snap.meeting, "title", None),
                "version": snap.version,
                "trigger": snap.trigger,
                "approved_at": snap.approved_at,
                "approved_by": snap.approved_by,
                "published_at": snap.published_at,
                "published_by": snap.published_by,
                "latest_transition": latest_transition,
            }
        )
    return result


def audit_report_rows(user, from_date: date, to_date: date) -> list[AuditLog]:
    from apps.audit.models import AuditLog

    start = timezone.make_aware(timezone.datetime.combine(from_date, timezone.datetime.min.time()))
    end_dt = timezone.datetime.combine(to_date, timezone.datetime.max.time())
    end = timezone.make_aware(end_dt)

    return list(
        AuditLog.objects.filter(created_at__range=(start, end))
        .select_related("user", "target_user")
        .order_by("-created_at")
    )


def reports_index_data(user) -> dict:
    from apps.action_items.models import STATUS_OPEN, ActionItem
    from apps.audit.models import AuditLog
    from apps.meetings.models import ApprovedMeetingSnapshot

    now = timezone.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_ago = now - timezone.timedelta(days=7)

    generated_today = ApprovedMeetingSnapshot.objects.filter(approved_at__gte=today_start).count()

    exports_week = AuditLog.objects.filter(
        action=AuditLog.ACTION_EXPORT,
        created_at__gte=week_ago,
    ).count()

    snapshots_reports = ApprovedMeetingSnapshot.objects.count()

    open_action_items = ActionItem.objects.filter(status=STATUS_OPEN).count()

    return {
        "generated_today": generated_today,
        "exports_week": exports_week,
        "snapshots_reports": snapshots_reports,
        "open_action_items": open_action_items,
    }
