from __future__ import annotations

from datetime import date

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.generic import TemplateView, View

from apps.action_items.models import STATUS_CHOICES, ActionItem
from apps.audit.models import AuditLog
from apps.audit.services import log_audit_event
from apps.core.permissions import can_export_reports
from apps.meetings.models import ApprovedMeetingSnapshot, Meeting
from apps.reports.excel_writer import write_workbook_bytes
from apps.reports.html_writer import RENDER_PRINTABLE_CONTEXT
from apps.reports.permissions import can_view_report
from apps.reports.services import (
    action_items_queryset,
    audit_report_rows,
    meaningful_report_filename,
    meeting_history_rows,
    meeting_readiness_rows,
    minutes_payload,
    sales_period_rows,
    weekly_commitments_rows,
)
from apps.reports.word_writer import build_docx_report
from apps.sales_updates.models import GroupPerformanceSnapshot, ReportingPeriod


def _client_ip(request):
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def _record_type(obj) -> str:
    if obj is None:
        return "reports.Report"
    try:
        return f"{obj._meta.app_label}.{obj._meta.object_name}"
    except AttributeError:
        return "reports.Report"


def _log_export(request, report_slug: str, target=None, extra: dict | None = None):
    try:
        new_vals = {"report_slug": report_slug}
        if extra:
            new_vals.update(extra)
        log_audit_event(
            record_type=_record_type(target or request.user),
            record=target or request.user,
            action=AuditLog.ACTION_EXPORT,
            user=request.user,
            ip_address=_client_ip(request),
            new_values=new_vals,
            reason=f"Exported report: {report_slug}",
        )
    except Exception:
        pass


REPORT_SLUG_MANAGEMENT_MEETING_MINUTES = "management-meeting-minutes"
REPORT_SLUG_ACTION_ITEM_REGISTER = "action-item-register"
REPORT_SLUG_OPEN_ACTION_ITEMS = "open-action-items"
REPORT_SLUG_OVERDUE_ACTION_ITEMS = "overdue-action-items"
REPORT_SLUG_DEPARTMENT_ACTION_ITEMS = "department-action-items"
REPORT_SLUG_MEETING_READINESS = "meeting-readiness"
REPORT_SLUG_SALES_PERFORMANCE = "sales-performance"
REPORT_SLUG_WEEKLY_COMMITMENTS = "weekly-commitments"
REPORT_SLUG_MEETING_HISTORY = "meeting-history"
REPORT_SLUG_AUTHORIZED_AUDIT_REPORT = "authorized-audit-report"


CATALOG: dict[str, dict] = {
    REPORT_SLUG_MANAGEMENT_MEETING_MINUTES: {
        "label": "Management Meeting Minutes",
        "formats": ["html", "pdf", "word", "excel"],
        "permission": "reports.view_report",
        "requires_pk": True,
        "pk_target": "snapshot",
        "description": "Immutable approved meeting minutes snapshot with agenda, discussions, decisions, and action items.",
    },
    REPORT_SLUG_ACTION_ITEM_REGISTER: {
        "label": "Action Item Register",
        "formats": ["html", "pdf", "word", "excel"],
        "permission": "reports.view_report",
        "requires_pk": False,
        "pk_target": None,
        "description": "Complete register of all action items with owners, priorities, due dates, and statuses.",
    },
    REPORT_SLUG_OPEN_ACTION_ITEMS: {
        "label": "Open Action Items",
        "formats": ["html", "pdf", "word", "excel"],
        "permission": "reports.view_report",
        "requires_pk": False,
        "pk_target": None,
        "description": "All active (non-terminal) action items grouped by priority and due date.",
    },
    REPORT_SLUG_OVERDUE_ACTION_ITEMS: {
        "label": "Overdue Action Items",
        "formats": ["html", "pdf", "word", "excel"],
        "permission": "reports.view_report",
        "requires_pk": False,
        "pk_target": None,
        "description": "Action items past due date with terminal status excluded, highlighting overdue age.",
    },
    REPORT_SLUG_DEPARTMENT_ACTION_ITEMS: {
        "label": "Department Action Items",
        "formats": ["html", "pdf", "word", "excel"],
        "permission": "reports.view_report",
        "requires_pk": False,
        "pk_target": None,
        "description": "Action items grouped by responsible department with open/closed counts.",
    },
    REPORT_SLUG_MEETING_READINESS: {
        "label": "Meeting Readiness",
        "formats": ["html", "pdf", "word", "excel"],
        "permission": "reports.view_report",
        "requires_pk": True,
        "pk_target": "meeting",
        "description": "Department submission status per meeting: not-started, in-progress, submitted, returned, accepted.",
    },
    REPORT_SLUG_SALES_PERFORMANCE: {
        "label": "Sales Performance",
        "formats": ["html", "pdf", "word", "excel"],
        "permission": "reports.view_report",
        "requires_pk": True,
        "pk_target": "period",
        "description": "Revenue, profit, orders and delivery KPIs by sales group vs targets for a reporting period.",
    },
    REPORT_SLUG_WEEKLY_COMMITMENTS: {
        "label": "Weekly Commitments",
        "formats": ["html", "pdf", "word", "excel"],
        "permission": "reports.view_report",
        "requires_pk": True,
        "pk_target": "snapshot_or_period",
        "description": "Weekly committed vs actual revenue/profit by week across sales groups.",
    },
    REPORT_SLUG_MEETING_HISTORY: {
        "label": "Meeting History",
        "formats": ["html", "pdf", "word", "excel"],
        "permission": "reports.view_report",
        "requires_pk": False,
        "pk_target": None,
        "description": "Approved meeting snapshot history with versions, triggers, approver, and publisher info.",
    },
    REPORT_SLUG_AUTHORIZED_AUDIT_REPORT: {
        "label": "Authorized Audit Report",
        "formats": ["html", "pdf", "word", "excel"],
        "permission": "reports.view_report",
        "requires_pk": False,
        "pk_target": None,
        "description": "Filterable audit log of all authorized system actions (from_date / to_date query params).",
    },
}


# ============================================================================
# Index View
# ============================================================================


class ReportsIndexView(LoginRequiredMixin, TemplateView):
    template_name = "reports/index.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["reports_catalog"] = CATALOG
        ctx["page_title"] = "Reports & Exports"
        return ctx


# ============================================================================
# Core Mixins
# ============================================================================


class ReportMixin:
    report_slug_kwarg = "report"
    pk_kwarg = "pk"
    html_template = "reports/base_printable.html"

    def get_report_slug(self) -> str:
        slug = self.kwargs.get(self.report_slug_kwarg)
        if slug not in CATALOG:
            raise Http404(f"Unknown report slug: {slug}")
        return slug

    def get_catalog_entry(self) -> dict:
        return CATALOG[self.get_report_slug()]

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            from django.contrib.auth.views import redirect_to_login

            return redirect_to_login(request.get_full_path())
        slug = self.get_report_slug()
        if not can_view_report(request.user, slug):
            raise PermissionDenied("You do not have permission to view this report.")
        return super().dispatch(request, *args, **kwargs)

    def _resolve_pk(self):
        pk = self.kwargs.get(self.pk_kwarg)
        if pk is None:
            pk = self.request.GET.get(self.pk_kwarg)
        return pk

    def get_snapshot(self):
        pk = self._resolve_pk()
        if pk is None:
            return None
        return get_object_or_404(ApprovedMeetingSnapshot, pk=pk)

    def get_meeting(self):
        pk = self._resolve_pk()
        if pk is None:
            return None
        return get_object_or_404(Meeting, pk=pk)

    def get_period(self):
        pk = self._resolve_pk()
        if pk is None:
            return None
        return get_object_or_404(ReportingPeriod, pk=pk)

    def get_sales_snapshot(self):
        pk = self._resolve_pk()
        if pk is None:
            return None
        try:
            return GroupPerformanceSnapshot.objects.get(pk=pk)
        except GroupPerformanceSnapshot.DoesNotExist:
            return None

    def filename_components(self):
        slug = self.get_report_slug()
        return {
            "report_slug": slug,
            "snapshot": None,
            "period": None,
            "meeting": None,
        }


class ApprovedSnapshotRequiredMixin(ReportMixin):
    def dispatch(self, request, *args, **kwargs):
        resp = super().dispatch(request, *args, **kwargs)
        if hasattr(resp, "status_code") and resp.status_code >= 400:
            return resp
        try:
            snap = self.get_snapshot()
        except Http404:
            snap = None
        if snap is None:
            raise Http404("Approved snapshot is required for this report.")
        if snap.approved_at is None:
            raise PermissionDenied("This snapshot has not been approved.")
        return resp


class PrintableHtmlMixin(ReportMixin):
    def get_html_template(self) -> str:
        return self.html_template

    def render_to_response(self, context, **response_kwargs):
        from django.conf import settings
        from django.template.loader import render_to_string

        html = render_to_string(
            self.get_html_template(),
            context,
            request=self.request,
        )
        comps = self.filename_components()
        fname = meaningful_report_filename(
            report_slug=comps["report_slug"],
            suffix=".html",
            meeting=comps.get("meeting"),
            snapshot=comps.get("snapshot"),
            period=comps.get("period"),
            user=self.request.user,
        )
        response = HttpResponse(html, content_type="text/html; charset=utf-8")
        response["Content-Disposition"] = f'inline; filename="{fname}"'
        if getattr(settings, "LOG_HTML_VIEW", True):
            _log_export(
                self.request,
                comps["report_slug"],
                comps.get("snapshot") or comps.get("period") or comps.get("meeting"),
            )
        return response


class ExcelExportMixin(ReportMixin):
    def render_to_response(self, context, **response_kwargs):
        if not can_export_reports(self.request.user):
            raise PermissionDenied("You do not have permission to export reports.")
        sheets = self.get_excel_sheets()
        payload = {}
        for name, val in sheets.items():
            headers, rows, money_cols = val
            payload[name] = (list(headers), list(rows), frozenset(money_cols or ()))
        data = write_workbook_bytes(payload)
        comps = self.filename_components()
        fname = meaningful_report_filename(
            report_slug=comps["report_slug"],
            suffix=".xlsx",
            meeting=comps.get("meeting"),
            snapshot=comps.get("snapshot"),
            period=comps.get("period"),
            user=self.request.user,
        )
        response = HttpResponse(
            data,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response["Content-Disposition"] = f'attachment; filename="{fname}"'
        _log_export(
            self.request,
            comps["report_slug"],
            comps.get("snapshot") or comps.get("period") or comps.get("meeting"),
            {"format": "excel"},
        )
        return response

    def get(self, request, *args, **kwargs):
        return self.render_to_response({})


class WordExportMixin(ReportMixin):
    def get_report_title(self) -> str:
        return CATALOG[self.get_report_slug()]["label"]

    def get_report_subtitle(self) -> str | None:
        return None

    def render_to_response(self, context, **response_kwargs):
        if not can_export_reports(self.request.user):
            raise PermissionDenied("You do not have permission to export reports.")
        sections = self.get_word_sections()
        data = build_docx_report(
            title=self.get_report_title(),
            subtitle=self.get_report_subtitle(),
            sections=sections,
        )
        comps = self.filename_components()
        fname = meaningful_report_filename(
            report_slug=comps["report_slug"],
            suffix=".docx",
            meeting=comps.get("meeting"),
            snapshot=comps.get("snapshot"),
            period=comps.get("period"),
            user=self.request.user,
        )
        response = HttpResponse(
            data,
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        response["Content-Disposition"] = f'attachment; filename="{fname}"'
        _log_export(
            self.request,
            comps["report_slug"],
            comps.get("snapshot") or comps.get("period") or comps.get("meeting"),
            {"format": "word"},
        )
        return response

    def get(self, request, *args, **kwargs):
        return self.render_to_response({})


class PdfExportMixin(PrintableHtmlMixin):
    def render_to_response(self, context, **response_kwargs):
        from django.template.loader import render_to_string

        html = render_to_string(
            self.get_html_template(),
            context,
            request=self.request,
        )
        comps = self.filename_components()
        fname = meaningful_report_filename(
            report_slug=comps["report_slug"],
            suffix=".pdf",
            meeting=comps.get("meeting"),
            snapshot=comps.get("snapshot"),
            period=comps.get("period"),
            user=self.request.user,
        )
        response = HttpResponse(html, content_type="text/html; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="{fname}"'
        response["X-Print-As-PDF"] = "1"
        _log_export(
            self.request,
            comps["report_slug"],
            comps.get("snapshot") or comps.get("period") or comps.get("meeting"),
            {"format": "pdf"},
        )
        return response


# ============================================================================
# Base Report View (data assembly shared across formats)
# ============================================================================


class BaseReportView(LoginRequiredMixin, ReportMixin, TemplateView):
    def get_printable_context(self, context: dict | None = None) -> dict:
        base = RENDER_PRINTABLE_CONTEXT()
        if context:
            base.update(context)
        base.setdefault("report_slug", self.get_report_slug())
        base.setdefault("report_label", CATALOG[self.get_report_slug()]["label"])
        return base

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        return self.get_printable_context(ctx)


# ============================================================================
# 1. Management Meeting Minutes Report
# ============================================================================


class ManagementMeetingMinutesView(ApprovedSnapshotRequiredMixin, BaseReportView):
    html_template = "reports/management_meeting_minutes.html"

    def get_context_data(self, **kwargs):
        snapshot = self.get_snapshot()
        payload = minutes_payload(snapshot)
        ctx = super().get_context_data(**kwargs)
        ctx.update(
            {
                "snapshot": snapshot,
                "meeting": snapshot.meeting,
                "minutes": payload,
            }
        )
        return ctx

    def filename_components(self):
        snapshot = self.get_snapshot()
        return {
            "report_slug": REPORT_SLUG_MANAGEMENT_MEETING_MINUTES,
            "snapshot": snapshot,
            "meeting": snapshot.meeting if snapshot else None,
            "period": None,
        }

    def get_excel_sheets(self):
        snapshot = self.get_snapshot()
        meeting = snapshot.meeting
        payload = minutes_payload(snapshot)

        meta_headers = ["Field", "Value"]
        meta_rows = [
            ["Company", "MIMOM"],
            ["Document Title", "Management Meeting Minutes"],
            ["Reference", getattr(meeting, "reference", "")],
            ["Meeting Date", f"{meeting.start_at:%Y-%m-%d %H:%M}"],
            ["Reporting Cut-off", ""],
            ["Status / Version", f"Approved v{snapshot.version}"],
            ["Trigger", snapshot.get_trigger_display() or snapshot.trigger],
            [
                "Approved At",
                f"{snapshot.approved_at:%Y-%m-%d %H:%M}" if snapshot.approved_at else "",
            ],
            ["Approved By", str(snapshot.approved_by) if snapshot.approved_by else ""],
        ]

        ai_headers = ["Ref", "Title", "Owner", "Priority", "Status", "Due Date"]
        ai_rows: list[list] = []
        action_items = payload.get("action_items") or payload.get("actions") or []
        if isinstance(action_items, list):
            for item in action_items:
                if isinstance(item, dict):
                    ai_rows.append(
                        [
                            str(item.get("reference") or ""),
                            str(item.get("title") or item.get("description") or ""),
                            str(item.get("owner") or item.get("owner_name") or ""),
                            str(item.get("priority") or ""),
                            str(item.get("status") or ""),
                            str(item.get("due_date") or ""),
                        ]
                    )

        return {
            "Minutes Meta": (meta_headers, meta_rows, frozenset()),
            "Action Items": (ai_headers, ai_rows, frozenset()),
        }

    def get_word_sections(self):
        snapshot = self.get_snapshot()
        meeting = snapshot.meeting

        meta_rows = [
            ["Field", "Value"],
            ["Company", "MIMOM"],
            ["Reference", getattr(meeting, "reference", "")],
            ["Meeting Date", f"{meeting.start_at:%Y-%m-%d %H:%M}"],
            ["Version", f"v{snapshot.version}"],
            ["Approved At", f"{snapshot.approved_at:%Y-%m-%d}" if snapshot.approved_at else ""],
        ]

        ai_rows = [["Ref", "Title", "Owner", "Status", "Due Date"]]
        payload = minutes_payload(snapshot)
        action_items = payload.get("action_items") or payload.get("actions") or []
        if isinstance(action_items, list):
            for item in action_items:
                if isinstance(item, dict):
                    ai_rows.append(
                        [
                            str(item.get("reference") or ""),
                            str(item.get("title") or item.get("description") or ""),
                            str(item.get("owner") or ""),
                            str(item.get("status") or ""),
                            str(item.get("due_date") or ""),
                        ]
                    )

        sections = [
            {"heading": "Document Metadata", "rows": meta_rows},
            {"heading": "Action Items", "rows": ai_rows},
        ]
        return sections


# ============================================================================
# Shared: Action item helpers for Excel/Word/Context
# ============================================================================


def _ai_row(item: ActionItem, with_dept: bool = False, with_overdue: bool = False) -> list:
    owner_name = item.owner.get_display_name() if item.owner else ""
    dept_name = item.department.name if item.department else ""
    row = [
        item.reference or "",
        item.title,
        owner_name,
        item.get_priority_display() or item.priority,
        item.get_status_display() or item.status,
        f"{item.due_date}" if item.due_date else "",
    ]
    if with_dept:
        row.insert(3, dept_name)
    if with_overdue:
        row.append("Yes" if item.is_overdue else "No")
        row.append(f"{item.overdue_age_days}")
    return row


def _ai_headers(with_dept: bool = False, with_overdue: bool = False) -> list[str]:
    h = ["Reference", "Title", "Owner", "Priority", "Status", "Due Date"]
    if with_dept:
        h.insert(3, "Department")
    if with_overdue:
        h.extend(["Is Overdue", "Overdue (days)"])
    return h


# ============================================================================
# 2. Action Item Register
# ============================================================================


class ActionItemRegisterView(BaseReportView):
    html_template = "reports/action_item_register.html"

    def get_items(self):
        return list(action_items_queryset())

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        items = self.get_items()
        ctx["action_items"] = items
        ctx["status_choices"] = STATUS_CHOICES
        return ctx

    def filename_components(self):
        return {
            "report_slug": REPORT_SLUG_ACTION_ITEM_REGISTER,
            "snapshot": None,
            "period": None,
            "meeting": None,
        }

    def get_excel_sheets(self):
        items = self.get_items()
        headers = _ai_headers(with_dept=True)
        rows = [_ai_row(i, with_dept=True) for i in items]
        return {"Action Item Register": (headers, rows, frozenset())}

    def get_word_sections(self):
        items = self.get_items()
        rows = [_ai_headers(with_dept=True)]
        rows.extend(_ai_row(i, with_dept=True) for i in items)
        return [{"heading": "Action Item Register", "rows": rows}]


# ============================================================================
# 3. Open Action Items
# ============================================================================


class OpenActionItemsView(BaseReportView):
    html_template = "reports/open_action_items.html"

    def get_items(self):
        from apps.action_items.models import ACTIVE_STATUSES

        return list(action_items_queryset().filter(status__in=ACTIVE_STATUSES))

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["action_items"] = self.get_items()
        ctx["status_choices"] = STATUS_CHOICES
        ctx["view_title"] = "Open Action Items"
        return ctx

    def filename_components(self):
        return {
            "report_slug": REPORT_SLUG_OPEN_ACTION_ITEMS,
            "snapshot": None,
            "period": None,
            "meeting": None,
        }

    def get_excel_sheets(self):
        items = self.get_items()
        headers = _ai_headers(with_dept=True)
        rows = [_ai_row(i, with_dept=True) for i in items]
        return {"Open Action Items": (headers, rows, frozenset())}

    def get_word_sections(self):
        items = self.get_items()
        rows = [_ai_headers(with_dept=True)]
        rows.extend(_ai_row(i, with_dept=True) for i in items)
        return [{"heading": "Open Action Items", "rows": rows}]


# ============================================================================
# 4. Overdue Action Items
# ============================================================================


class OverdueActionItemsView(BaseReportView):
    html_template = "reports/overdue_action_items.html"

    def get_items(self):
        today = timezone.now().date()
        from apps.action_items.models import TERMINAL_STATUSES

        return list(
            action_items_queryset().exclude(status__in=TERMINAL_STATUSES).filter(due_date__lt=today)
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        items = self.get_items()
        ctx["action_items"] = items
        ctx["status_choices"] = STATUS_CHOICES
        ctx["view_title"] = "Overdue Action Items"
        return ctx

    def filename_components(self):
        return {
            "report_slug": REPORT_SLUG_OVERDUE_ACTION_ITEMS,
            "snapshot": None,
            "period": None,
            "meeting": None,
        }

    def get_excel_sheets(self):
        items = self.get_items()
        headers = _ai_headers(with_dept=True, with_overdue=True)
        rows = [_ai_row(i, with_dept=True, with_overdue=True) for i in items]
        return {"Overdue Action Items": (headers, rows, frozenset())}

    def get_word_sections(self):
        items = self.get_items()
        rows = [_ai_headers(with_dept=True, with_overdue=True)]
        rows.extend(_ai_row(i, with_dept=True, with_overdue=True) for i in items)
        return [{"heading": "Overdue Action Items", "rows": rows}]


# ============================================================================
# 5. Department Action Items
# ============================================================================


class DepartmentActionItemsView(BaseReportView):
    html_template = "reports/department_action_items.html"

    def get_groups(self):
        items = list(action_items_queryset().select_related("department", "owner"))
        grouped: dict[str, list[ActionItem]] = {}
        unassigned: list[ActionItem] = []
        for it in items:
            dept_name = it.department.name if it.department else None
            if dept_name:
                grouped.setdefault(dept_name, []).append(it)
            else:
                unassigned.append(it)
        result = []
        for name in sorted(grouped):
            result.append({"department": name, "items": grouped[name]})
        if unassigned:
            result.append({"department": "(Unassigned)", "items": unassigned})
        return result

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        groups = self.get_groups()
        ctx["department_groups"] = groups
        return ctx

    def filename_components(self):
        return {
            "report_slug": REPORT_SLUG_DEPARTMENT_ACTION_ITEMS,
            "snapshot": None,
            "period": None,
            "meeting": None,
        }

    def get_excel_sheets(self):
        groups = self.get_groups()
        sheets: dict[str, tuple[list[str], list[list], frozenset[int] | None]] = {}
        summary_headers = ["Department", "Total", "Open", "Completed", "Cancelled"]
        summary_rows: list[list] = []
        from apps.action_items.models import ACTIVE_STATUSES, STATUS_CANCELLED, STATUS_COMPLETED

        for g in groups:
            items = g["items"]
            dept_key = (g["department"] or "Unassigned")[:31]
            h = _ai_headers()
            rows = [_ai_row(i) for i in items]
            sheets[dept_key] = (h, rows, frozenset())

            total = len(items)
            open_n = sum(1 for i in items if i.status in ACTIVE_STATUSES)
            comp_n = sum(1 for i in items if i.status == STATUS_COMPLETED)
            canc_n = sum(1 for i in items if i.status == STATUS_CANCELLED)
            summary_rows.append([g["department"], total, open_n, comp_n, canc_n])

        sheets["Summary"] = (summary_headers, summary_rows, frozenset())
        return sheets

    def get_word_sections(self):
        groups = self.get_groups()
        sections = []
        for g in groups:
            rows = [_ai_headers()]
            rows.extend(_ai_row(i) for i in g["items"])
            sections.append({"heading": f"Department — {g['department']}", "rows": rows})
        return sections


# ============================================================================
# 6. Meeting Readiness
# ============================================================================


class MeetingReadinessView(BaseReportView):
    html_template = "reports/meeting_readiness.html"

    def get_meeting(self):
        meeting = super().get_meeting()
        if meeting is None:
            raise Http404("Meeting PK is required for meeting readiness report.")
        return meeting

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        meeting = self.get_meeting()
        submissions = meeting_readiness_rows(meeting)
        ctx["meeting"] = meeting
        ctx["submissions"] = submissions
        return ctx

    def filename_components(self):
        meeting = self.get_meeting()
        return {
            "report_slug": REPORT_SLUG_MEETING_READINESS,
            "snapshot": None,
            "period": None,
            "meeting": meeting,
        }

    def get_excel_sheets(self):
        meeting = self.get_meeting()
        submissions = meeting_readiness_rows(meeting)
        headers = ["Department", "Status", "Contributor", "Last Updated", "Submitted At"]
        rows: list[list] = []
        for s in submissions:
            rows.append(
                [
                    s.department.name if s.department else "",
                    getattr(s, "_state_label", s.submission_state),
                    s.contributor.get_display_name() if s.contributor else "",
                    f"{s.last_updated_at:%Y-%m-%d %H:%M}" if s.last_updated_at else "",
                    f"{s.last_submitted_at:%Y-%m-%d %H:%M}" if s.last_submitted_at else "",
                ]
            )
        meta_headers = ["Field", "Value"]
        meta_rows = [
            ["Meeting Reference", getattr(meeting, "reference", "")],
            ["Title", meeting.title],
            ["Scheduled", f"{meeting.start_at:%Y-%m-%d %H:%M}"],
            ["Status", meeting.get_status_display() or meeting.status],
        ]
        return {
            "Meeting": (meta_headers, meta_rows, frozenset()),
            "Department Readiness": (headers, rows, frozenset()),
        }

    def get_word_sections(self):
        meeting = self.get_meeting()
        submissions = meeting_readiness_rows(meeting)
        meta_rows = [
            ["Field", "Value"],
            ["Meeting Reference", getattr(meeting, "reference", "")],
            ["Title", meeting.title],
            ["Scheduled", f"{meeting.start_at:%Y-%m-%d %H:%M}"],
            ["Status", meeting.get_status_display() or meeting.status],
        ]
        sub_rows = [["Department", "Status", "Contributor", "Last Updated"]]
        for s in submissions:
            sub_rows.append(
                [
                    s.department.name if s.department else "",
                    getattr(s, "_state_label", s.submission_state),
                    s.contributor.get_display_name() if s.contributor else "",
                    f"{s.last_updated_at:%Y-%m-%d}" if s.last_updated_at else "",
                ]
            )
        return [
            {"heading": "Meeting", "rows": meta_rows},
            {"heading": "Department Submission Readiness", "rows": sub_rows},
        ]


# ============================================================================
# 7. Sales Performance
# ============================================================================


class SalesPerformanceView(BaseReportView):
    html_template = "reports/sales_performance.html"

    def get_period(self):
        period = super().get_period()
        if period is None:
            raise Http404("Reporting period PK is required for sales performance report.")
        return period

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        period = self.get_period()
        totals = sales_period_rows(period)
        ctx["period"] = period
        ctx["totals"] = totals
        return ctx

    def filename_components(self):
        period = self.get_period()
        return {
            "report_slug": REPORT_SLUG_SALES_PERFORMANCE,
            "snapshot": None,
            "period": period,
            "meeting": None,
        }

    def get_excel_sheets(self):
        period = self.get_period()
        totals = sales_period_rows(period)

        meta_headers = ["Field", "Value"]
        meta_rows = [
            ["Period", period.name],
            ["Start", f"{period.start_date}"],
            ["End", f"{period.end_date}"],
            ["Cut-off", f"{period.cut_off_date}"],
            ["Weeks", period.weeks_count],
            ["Currency", period.get_currency_display() or period.currency],
            ["Status", period.get_status_display() or period.status],
        ]

        group_headers = [
            "Group",
            "Revenue Target",
            "Revenue Actual",
            "Revenue Deficit",
            "Revenue %",
            "Profit Target",
            "Profit Actual",
            "Profit Deficit",
            "Profit %",
            "Orders Target",
            "Orders Actual",
            "Deliveries Target",
            "Deliveries Achieved",
            "On-Time %",
        ]
        group_rows: list[list] = []
        money_cols = frozenset([1, 2, 3, 5, 6, 7])
        groups = totals.get("groups") or []
        for g in groups:
            if not isinstance(g, dict):
                continue
            group_rows.append(
                [
                    str(g.get("group_code") or g.get("group") or ""),
                    g.get("revenue_target", 0),
                    g.get("revenue_actual", 0),
                    g.get("revenue_deficit", 0),
                    f"{g.get('revenue_pct', 0)}%",
                    g.get("profit_target", 0),
                    g.get("profit_actual", 0),
                    g.get("profit_deficit", 0),
                    f"{g.get('profit_pct', 0)}%",
                    g.get("orders_target", 0),
                    g.get("orders_actual", 0),
                    g.get("deliveries_target", 0),
                    g.get("deliveries_achieved", 0),
                    f"{g.get('on_time_pct', 0)}%",
                ]
            )

        total_row = totals.get("total") or {}
        summary_headers = ["Metric", "Target", "Actual", "Deficit / Result"]
        summary_rows = [
            [
                "Revenue",
                total_row.get("revenue_target", 0),
                total_row.get("revenue_actual", 0),
                total_row.get("revenue_deficit", 0),
            ],
            [
                "Profit",
                total_row.get("profit_target", 0),
                total_row.get("profit_actual", 0),
                total_row.get("profit_deficit", 0),
            ],
            ["Orders", total_row.get("orders_target", 0), total_row.get("orders_actual", 0), ""],
            [
                "Deliveries",
                total_row.get("deliveries_target", 0),
                total_row.get("deliveries_achieved", 0),
                f"{total_row.get('on_time_pct', 0)}% on-time",
            ],
        ]

        return {
            "Period": (meta_headers, meta_rows, frozenset()),
            "Group Performance": (group_headers, group_rows, money_cols),
            "Period Totals": (summary_headers, summary_rows, frozenset([1, 2, 3])),
        }

    def get_word_sections(self):
        period = self.get_period()
        totals = sales_period_rows(period)

        meta_rows = [
            ["Field", "Value"],
            ["Period", period.name],
            ["Date Range", f"{period.start_date} → {period.end_date}"],
            ["Cut-off", f"{period.cut_off_date}"],
            ["Currency", period.get_currency_display() or period.currency],
        ]

        perf_rows = [
            ["Group", "Revenue %", "Profit %", "Orders Actual", "Deliveries Achieved", "On-Time %"]
        ]
        groups = totals.get("groups") or []
        for g in groups:
            if not isinstance(g, dict):
                continue
            perf_rows.append(
                [
                    str(g.get("group_code") or g.get("group") or ""),
                    f"{g.get('revenue_pct', 0)}%",
                    f"{g.get('profit_pct', 0)}%",
                    g.get("orders_actual", 0),
                    g.get("deliveries_achieved", 0),
                    f"{g.get('on_time_pct', 0)}%",
                ]
            )

        return [
            {"heading": "Reporting Period", "rows": meta_rows},
            {"heading": "Sales Performance Summary", "rows": perf_rows},
        ]


# ============================================================================
# 8. Weekly Commitments
# ============================================================================


class WeeklyCommitmentsView(BaseReportView):
    html_template = "reports/weekly_commitments.html"

    def _resolve_target(self):
        pk = self._resolve_pk()
        if pk is None:
            raise Http404("Snapshot or Period PK is required for weekly commitments report.")
        snap = None
        period = None
        try:
            snap = GroupPerformanceSnapshot.objects.get(pk=pk)
        except GroupPerformanceSnapshot.DoesNotExist:
            try:
                period = ReportingPeriod.objects.get(pk=pk)
            except ReportingPeriod.DoesNotExist:
                raise Http404("Neither snapshot nor reporting period found for the given PK.")
        return snap, period

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        snap, period = self._resolve_target()
        if snap is not None:
            rows_result = weekly_commitments_rows(snap)
            ctx["snapshot"] = snap
            ctx["period"] = snap.period
        else:
            rows_result = {
                "period": period,
                "snapshots": list(
                    GroupPerformanceSnapshot.objects.filter(period=period).select_related(
                        "group", "period"
                    )
                ),
            }
            ctx["period"] = period
        ctx["weekly_rows"] = rows_result
        return ctx

    def filename_components(self):
        snap, period = self._resolve_target()
        return {
            "report_slug": REPORT_SLUG_WEEKLY_COMMITMENTS,
            "snapshot": snap,
            "period": period or (snap.period if snap else None),
            "meeting": None,
        }

    def get_excel_sheets(self):
        snap, period = self._resolve_target()
        if snap is not None:
            data = weekly_commitments_rows(snap)
            weeks = data.get("weeks") or []
            headers = [
                "Week",
                "Committed Revenue",
                "Actual Revenue",
                "Committed Profit",
                "Actual Profit",
                "Notes",
            ]
            rows: list[list] = []
            money_cols = frozenset([1, 2, 3, 4])
            for w in weeks:
                rows.append(
                    [
                        f"W{w.get('week_number', '')}",
                        w.get("committed_revenue", 0),
                        w.get("actual_revenue", 0),
                        w.get("committed_profit", 0),
                        w.get("actual_profit", 0),
                        str(w.get("notes") or ""),
                    ]
                )
            return {
                f"{snap.group.code} Weekly": (headers, rows, money_cols),
            }
        else:
            sheets: dict[str, tuple[list[str], list[list], frozenset[int] | None]] = {}
            headers = [
                "Group",
                "Week",
                "Committed Revenue",
                "Actual Revenue",
                "Committed Profit",
                "Actual Profit",
            ]
            rows: list[list] = []
            money_cols = frozenset([2, 3, 4, 5])
            snapshots = (
                GroupPerformanceSnapshot.objects.filter(period=period)
                .select_related("group", "period")
                .order_by("group__code")
            )
            for s in snapshots:
                data = weekly_commitments_rows(s)
                for w in data.get("weeks") or []:
                    rows.append(
                        [
                            s.group.code,
                            f"W{w.get('week_number', '')}",
                            w.get("committed_revenue", 0),
                            w.get("actual_revenue", 0),
                            w.get("committed_profit", 0),
                            w.get("actual_profit", 0),
                        ]
                    )
                sheets[f"{s.group.code}"[:31]] = (
                    [
                        "Week",
                        "Committed Revenue",
                        "Actual Revenue",
                        "Committed Profit",
                        "Actual Profit",
                    ],
                    [
                        [
                            f"W{w.get('week_number', '')}",
                            w.get("committed_revenue", 0),
                            w.get("actual_revenue", 0),
                            w.get("committed_profit", 0),
                            w.get("actual_profit", 0),
                        ]
                        for w in data.get("weeks") or []
                    ],
                    frozenset([1, 2, 3, 4]),
                )
            sheets["All Groups"] = (headers, rows, money_cols)
            return sheets

    def get_word_sections(self):
        snap, period = self._resolve_target()
        sections = []
        if snap is not None:
            data = weekly_commitments_rows(snap)
            meta_rows = [
                ["Field", "Value"],
                ["Group", f"{snap.group.code} / {snap.group.name}"],
                ["Period", snap.period.name],
            ]
            wc_rows = [
                ["Week", "Committed Revenue", "Actual Revenue", "Committed Profit", "Actual Profit"]
            ]
            for w in data.get("weeks") or []:
                wc_rows.append(
                    [
                        f"W{w.get('week_number', '')}",
                        str(w.get("committed_revenue", 0)),
                        str(w.get("actual_revenue", 0)),
                        str(w.get("committed_profit", 0)),
                        str(w.get("actual_profit", 0)),
                    ]
                )
            sections.append({"heading": "Snapshot", "rows": meta_rows})
            sections.append({"heading": "Weekly Commitments", "rows": wc_rows})
        else:
            snapshots = (
                GroupPerformanceSnapshot.objects.filter(period=period)
                .select_related("group", "period")
                .order_by("group__code")
            )
            meta_rows = [
                ["Field", "Value"],
                ["Period", period.name],
                ["Snapshot Count", snapshots.count()],
            ]
            sections.append({"heading": "Reporting Period", "rows": meta_rows})
            for s in snapshots:
                data = weekly_commitments_rows(s)
                rows = [
                    [
                        "Week",
                        "Committed Revenue",
                        "Actual Revenue",
                        "Committed Profit",
                        "Actual Profit",
                    ]
                ]
                for w in data.get("weeks") or []:
                    rows.append(
                        [
                            f"W{w.get('week_number', '')}",
                            str(w.get("committed_revenue", 0)),
                            str(w.get("actual_revenue", 0)),
                            str(w.get("committed_profit", 0)),
                            str(w.get("actual_profit", 0)),
                        ]
                    )
                sections.append(
                    {
                        "heading": f"{snap.group.code if snap else s.group.code} Commitments",
                        "rows": rows,
                    }
                )
        return sections


# ============================================================================
# 9. Meeting History
# ============================================================================


class MeetingHistoryView(BaseReportView):
    html_template = "reports/meeting_history.html"

    def get_history(self):
        return meeting_history_rows(self.request.user, limit=100)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["history_rows"] = self.get_history()
        return ctx

    def filename_components(self):
        return {
            "report_slug": REPORT_SLUG_MEETING_HISTORY,
            "snapshot": None,
            "period": None,
            "meeting": None,
        }

    def get_excel_sheets(self):
        history = self.get_history()
        headers = [
            "Reference",
            "Title",
            "Version",
            "Trigger",
            "Approved At",
            "Approved By",
            "Published At",
            "Published By",
            "Latest Transition",
        ]
        rows: list[list] = []
        for r in history:
            tr = r.get("latest_transition")
            rows.append(
                [
                    r.get("reference") or "",
                    r.get("title") or "",
                    r.get("version") or "",
                    r.get("snapshot").get_trigger_display()
                    if r.get("snapshot")
                    else r.get("trigger", ""),
                    f"{r.get('approved_at'):%Y-%m-%d %H:%M}" if r.get("approved_at") else "",
                    str(r.get("approved_by") or ""),
                    f"{r.get('published_at'):%Y-%m-%d %H:%M}" if r.get("published_at") else "",
                    str(r.get("published_by") or ""),
                    f"{tr.to_status} by {tr.transitioned_by} @ {tr.transitioned_at:%Y-%m-%d}"
                    if tr
                    else "",
                ]
            )
        return {"Meeting History": (headers, rows, frozenset())}

    def get_word_sections(self):
        history = self.get_history()
        rows = [["Reference", "Title", "Version", "Trigger", "Approved At", "Approved By"]]
        for r in history:
            rows.append(
                [
                    r.get("reference") or "",
                    r.get("title") or "",
                    r.get("version") or "",
                    r.get("snapshot").get_trigger_display()
                    if r.get("snapshot")
                    else r.get("trigger", ""),
                    f"{r.get('approved_at'):%Y-%m-%d}" if r.get("approved_at") else "",
                    str(r.get("approved_by") or ""),
                ]
            )
        return [{"heading": "Approved Meeting Snapshot History", "rows": rows}]


# ============================================================================
# 10. Authorized Audit Report
# ============================================================================


class AuthorizedAuditReportView(BaseReportView):
    html_template = "reports/authorized_audit_report.html"

    def _parse_date(self, s: str) -> date | None:
        if not s:
            return None
        try:
            return timezone.datetime.strptime(s, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            return None

    def get_date_range(self) -> tuple[date, date]:
        from_date = self._parse_date(self.request.GET.get("from_date"))
        to_date = self._parse_date(self.request.GET.get("to_date"))
        today = timezone.now().date()
        if to_date is None:
            to_date = today
        if from_date is None:
            from_date = to_date - timezone.timedelta(days=30)
        if from_date > to_date:
            from_date, to_date = to_date, from_date
        return from_date, to_date

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        from_date, to_date = self.get_date_range()
        rows = audit_report_rows(self.request.user, from_date, to_date)
        ctx["from_date"] = from_date
        ctx["to_date"] = to_date
        ctx["audit_rows"] = rows
        return ctx

    def filename_components(self):
        from_date, to_date = self.get_date_range()
        return {
            "report_slug": REPORT_SLUG_AUTHORIZED_AUDIT_REPORT,
            "snapshot": None,
            "period": None,
            "meeting": None,
        }

    def get_excel_sheets(self):
        from_date, to_date = self.get_date_range()
        rows = audit_report_rows(self.request.user, from_date, to_date)

        range_headers = ["Field", "Value"]
        range_rows = [
            ["From Date", f"{from_date}"],
            ["To Date", f"{to_date}"],
            ["Event Count", len(rows)],
            ["Generated At", f"{timezone.now():%Y-%m-%d %H:%M:%S}"],
        ]

        log_headers = [
            "Timestamp",
            "Action",
            "Record Type",
            "Record ID",
            "Initiated By",
            "Target User",
            "IP Address",
            "Reason",
        ]
        log_rows: list[list] = []
        for log in rows:
            log_rows.append(
                [
                    f"{log.created_at:%Y-%m-%d %H:%M:%S}",
                    log.get_action_display() or log.action,
                    log.record_type,
                    log.record_id,
                    log.user.get_display_name() if log.user else "",
                    log.target_user.get_display_name() if log.target_user else "",
                    log.ip_address or "",
                    log.reason or "",
                ]
            )

        return {
            "Report Range": (range_headers, range_rows, frozenset()),
            "Audit Events": (log_headers, log_rows, frozenset()),
        }

    def get_word_sections(self):
        from_date, to_date = self.get_date_range()
        rows = audit_report_rows(self.request.user, from_date, to_date)

        meta_rows = [
            ["Field", "Value"],
            ["From Date", f"{from_date}"],
            ["To Date", f"{to_date}"],
            ["Event Count", len(rows)],
        ]
        log_rows = [["Timestamp", "Action", "Record Type", "Initiated By", "Target"]]
        for log in rows[:500]:
            log_rows.append(
                [
                    f"{log.created_at:%Y-%m-%d %H:%M}",
                    log.get_action_display() or log.action,
                    log.record_type,
                    log.user.get_display_name() if log.user else "",
                    log.target_user.get_display_name() if log.target_user else "",
                ]
            )
        return [
            {"heading": "Report Parameters", "rows": meta_rows},
            {"heading": "Audit Events (first 500)", "rows": log_rows},
        ]


# ============================================================================
# Dispatch map: report slug -> base report CBV
# ============================================================================


_BASE_REPORT_VIEWS: dict[str, type[BaseReportView]] = {
    REPORT_SLUG_MANAGEMENT_MEETING_MINUTES: ManagementMeetingMinutesView,
    REPORT_SLUG_ACTION_ITEM_REGISTER: ActionItemRegisterView,
    REPORT_SLUG_OPEN_ACTION_ITEMS: OpenActionItemsView,
    REPORT_SLUG_OVERDUE_ACTION_ITEMS: OverdueActionItemsView,
    REPORT_SLUG_DEPARTMENT_ACTION_ITEMS: DepartmentActionItemsView,
    REPORT_SLUG_MEETING_READINESS: MeetingReadinessView,
    REPORT_SLUG_SALES_PERFORMANCE: SalesPerformanceView,
    REPORT_SLUG_WEEKLY_COMMITMENTS: WeeklyCommitmentsView,
    REPORT_SLUG_MEETING_HISTORY: MeetingHistoryView,
    REPORT_SLUG_AUTHORIZED_AUDIT_REPORT: AuthorizedAuditReportView,
}


def _base_view_for(slug: str) -> type[BaseReportView]:
    if slug not in _BASE_REPORT_VIEWS:
        raise Http404(f"Unknown report slug: {slug}")
    return _BASE_REPORT_VIEWS[slug]


# ============================================================================
# Generic export CBVs — resolve slug and dispatch to format-specific mixin
# ============================================================================


class PrintableHtmlView(View):
    def dispatch(self, request, *args, **kwargs):
        slug = kwargs.get("report")
        if slug not in CATALOG:
            raise Http404(f"Unknown report slug: {slug}")
        base_cls = _base_view_for(slug)

        class _PrintableView(PrintableHtmlMixin, base_cls):  # type: ignore[valid-type,misc]
            pass

        view = _PrintableView.as_view()
        return view(request, *args, **kwargs)


class ExcelExportView(View):
    def dispatch(self, request, *args, **kwargs):
        slug = kwargs.get("report")
        if slug not in CATALOG:
            raise Http404(f"Unknown report slug: {slug}")
        base_cls = _base_view_for(slug)

        class _ExcelView(ExcelExportMixin, base_cls):  # type: ignore[valid-type,misc]
            pass

        view = _ExcelView.as_view()
        return view(request, *args, **kwargs)


class WordExportView(View):
    def dispatch(self, request, *args, **kwargs):
        slug = kwargs.get("report")
        if slug not in CATALOG:
            raise Http404(f"Unknown report slug: {slug}")
        base_cls = _base_view_for(slug)

        class _WordView(WordExportMixin, base_cls):  # type: ignore[valid-type,misc]
            pass

        view = _WordView.as_view()
        return view(request, *args, **kwargs)


class PdfExportView(View):
    def dispatch(self, request, *args, **kwargs):
        slug = kwargs.get("report")
        if slug not in CATALOG:
            raise Http404(f"Unknown report slug: {slug}")
        base_cls = _base_view_for(slug)

        class _PdfView(PdfExportMixin, base_cls):  # type: ignore[valid-type,misc]
            pass

        view = _PdfView.as_view()
        return view(request, *args, **kwargs)
