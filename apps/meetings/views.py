from __future__ import annotations

from calendar import month_name
from datetime import date, timedelta
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    FormView,
    ListView,
    UpdateView,
    View,
)

from apps.accounts.models import Department
from apps.action_items.models import ActionItem
from apps.audit.models import AuditLog
from apps.audit.services import log_audit_event
from apps.core.permissions import (
    ArchiveAuthorizedMixin,
    MeetingAuthorRequiredMixin,
    MinutesApproverRequiredMixin,
    MinutesEditRequiredMixin,
    MinutesReviewRequiredMixin,
    ReopenAuthorizedMixin,
    can_approve_meeting,
    can_archive_meeting,
    can_close_meeting,
    can_create_meeting,
    can_edit_meeting,
    can_publish_meeting,
    can_reopen_meeting,
    can_resubmit_minutes,
    can_return_minutes,
    can_submit_minutes,
    can_transition_meeting,
    can_view_confidential_items,
)
from apps.meetings.forms import (
    ActionItemCreateFromMinutesForm,
    AgendaCategoryForm,
    AgendaItemAttachmentForm,
    AgendaItemForm,
    AgendaOrderForm,
    MeetingAttachmentForm,
    MeetingForm,
    MinutesEditorForm,
    ReturnForCorrectionForm,
    TransitionForm,
    build_attendance_formset,
)
from apps.meetings.models import (
    STATUS_APPROVED,
    STATUS_ARCHIVED,
    STATUS_CHOICES,
    STATUS_CLOSED,
    STATUS_DRAFT,
    STATUS_PUBLISHED,
    STATUS_RETURNED_FOR_CORRECTION,
    ActionItemLink,
    AgendaCategory,
    AgendaItem,
    AgendaItemAttachment,
    ApprovedMeetingSnapshot,
    DepartmentSubmission,
    Meeting,
    MeetingAttachment,
    MinutesSectionSpec,
)
from apps.meetings.services import (
    VALID_TRANSITIONS,
    agenda_completeness,
    approve_meeting,
    build_calendar,
    carry_forward_agenda_items,
    close_meeting,
    dept_submission_upsert,
    meetings_prep_dashboard_data,
    publish_meeting,
    reopen_meeting,
    resubmit_for_review,
    return_for_correction,
    submit_for_review,
    transition_meeting,
)


def _client_ip(request):
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def _record_type(instance) -> str:
    return f"{instance._meta.app_label}.{instance._meta.object_name}"


def dashboard_summary_counts(request=None) -> dict:
    """Return dashboard counts grouped by status. Callable from home dashboard view."""
    qs = Meeting.objects.all()
    if request is not None:
        user = getattr(request, "user", None)
        if user and not (
            getattr(user, "is_superuser", False)
            or user.has_role(
                "System Administrator",
                "Management Administrator",
                "Meeting Chairperson",
                "Minutes Secretary",
            )
        ):
            visible_depts = (
                user.get_assigned_departments() if getattr(user, "is_authenticated", False) else []
            )
            qs = qs.filter(
                models.Q(department__in=list(visible_depts)) | models.Q(department__isnull=True)
            )
    counts_by_status = dict(qs.values_list("status").annotate(count=models.Count("id")))
    upcoming = list(
        qs.filter(start_at__gte=timezone.now())
        .select_related("type", "chair", "department")
        .order_by("start_at")[:5]
    )
    return {
        "meeting_counts": {k: counts_by_status.get(k, 0) for k, _ in STATUS_CHOICES},
        "upcoming_meetings": upcoming,
        "meeting_total": sum(counts_by_status.values()),
        "status_choices": STATUS_CHOICES,
        "meeting_create_url": reverse("meetings:meeting_create"),
    }


class _MeetingFormMixin:
    """Snapshots previous values on retrieve so update views can diff for audit."""

    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        obj._previous_values = {  # type: ignore[attr-defined]
            f.name: getattr(obj, f.name)
            for f in obj._meta.concrete_fields
            if f.concrete and not f.many_to_many
        }
        return obj


class MeetingListView(LoginRequiredMixin, ListView):
    model = Meeting
    context_object_name = "meetings"
    template_name = "meetings/meeting_list.html"
    paginate_by = 20

    def get_queryset(self):
        qs = (
            Meeting.objects.all()
            .select_related("type", "chair", "department", "created_by")
            .prefetch_related("attendance", "agenda_items")
        )
        user = self.request.user
        if not (
            getattr(user, "is_superuser", False)
            or user.has_role(
                "System Administrator",
                "Management Administrator",
                "Meeting Chairperson",
                "Minutes Secretary",
            )
        ):
            visible_depts = (
                set(user.get_assigned_departments().values_list("pk", flat=True))
                if getattr(user, "is_authenticated", False)
                else set()
            )
            qs = qs.filter(
                models.Q(department_id__in=visible_depts) | models.Q(department__isnull=True)
            )
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(
                models.Q(title__icontains=q)
                | models.Q(reference__icontains=q)
                | models.Q(location__icontains=q)
            )
        status = self.request.GET.get("status", "").strip()
        if status:
            qs = qs.filter(status=status)
        department = self.request.GET.get("department", "").strip()
        if department:
            qs = qs.filter(department_id=department)
        order = self.request.GET.get("order", "-start_at")
        allowed = {"-start_at", "start_at", "-updated_at", "title", "status"}
        if order not in allowed:
            order = "-start_at"
        return qs.order_by(order)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        view_mode = self.request.GET.get("view", "list")
        ctx["view_mode"] = view_mode
        ctx["status_choices"] = STATUS_CHOICES
        ctx["departments"] = Department.objects.filter(is_active=True).order_by("name")
        ctx["can_create"] = can_create_meeting(self.request.user)
        q = self.request.GET.get("q", "")
        status = self.request.GET.get("status", "")
        dept = self.request.GET.get("department", "")
        base = {"q": q, "status": status, "department": dept}
        list_args = {k: v for k, v in {**base, "view": "list"}.items() if v}
        cal_args = {k: v for k, v in {**base, "view": "calendar"}.items() if v}
        ctx["list_view_url"] = reverse("meetings:meeting_list") + (
            "?" + urlencode(list_args) if list_args else ""
        )
        ctx["calendar_view_url"] = reverse("meetings:meeting_list") + (
            "?" + urlencode(cal_args) if cal_args else ""
        )
        if view_mode == "calendar":
            try:
                year = int(self.request.GET.get("year", 0) or timezone.localdate().year)
                month = int(self.request.GET.get("month", 0) or timezone.localdate().month)
            except ValueError:
                year, month = timezone.localdate().year, timezone.localdate().month
            month_start = date(year, month, 1)
            month_end = date(
                year + (month // 12),
                month % 12 + 1,
                1,
            )
            meetings_for_cal = list(
                self.get_queryset().filter(
                    start_at__date__gte=month_start, start_at__date__lt=month_end
                )
            )
            ctx["calendar_cells"] = build_calendar(month_start, meetings_for_cal)
            ctx["month_start"] = month_start
            ctx["month_name_year"] = f"{month_name[month]} {year}"
            prev_month = month - 1 or 12
            prev_year = year - (1 if prev_month == 12 else 0)
            next_month = month + 1 if month < 12 else 1
            next_year = year + (1 if next_month == 1 else 0)
            prev_args = {**cal_args, "year": prev_year, "month": prev_month}
            next_args = {**cal_args, "year": next_year, "month": next_month}
            ctx["prev_month_url"] = reverse("meetings:meeting_list") + "?" + urlencode(prev_args)
            ctx["next_month_url"] = reverse("meetings:meeting_list") + "?" + urlencode(next_args)
        return ctx


class MeetingDetailView(LoginRequiredMixin, DetailView):
    model = Meeting
    context_object_name = "meeting"
    template_name = "meetings/meeting_detail.html"

    def get_queryset(self):
        return (
            Meeting.objects.all()
            .select_related("type", "chair", "department", "created_by", "last_modified_by")
            .prefetch_related(
                "attendance__user",
                "agenda_items__category",
                "agenda_items__owner",
                "agenda_items__attachments",
                "attachments",
                "status_history__transitioned_by",
            )
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        meeting: Meeting = self.object
        user = self.request.user
        ctx["can_edit"] = can_edit_meeting(user, meeting)
        ctx["can_archive"] = can_archive_meeting(user, meeting)
        ctx["can_transition"] = can_transition_meeting(user, meeting)
        ctx["can_view_confidential"] = can_view_confidential_items(user, meeting=meeting)
        current = meeting.status
        targets = VALID_TRANSITIONS.get(current, set())
        from apps.core.permissions import REOPEN_AUTHORIZED_ROLES

        is_admin = bool(
            getattr(user, "is_superuser", False) or user.has_role(*REOPEN_AUTHORIZED_ROLES)
        )
        allowed = {s for s in targets if is_admin or s not in {STATUS_ARCHIVED, "RETURNED"}}
        ctx["available_target_statuses"] = [
            (val, label) for val, label in STATUS_CHOICES if val in allowed
        ]
        ctx["status_label_map"] = dict(STATUS_CHOICES)
        ctx["transition_form"] = TransitionForm(meeting=meeting, by_user=user)
        ctx["carry_forward_candidates"] = (
            Meeting.objects.filter(status__in={STATUS_DRAFT})
            .exclude(pk=meeting.pk)
            .select_related("type")
            .order_by("-start_at")[:10]
        )
        return ctx


class MeetingCreateView(LoginRequiredMixin, MeetingAuthorRequiredMixin, CreateView):
    model = Meeting
    form_class = MeetingForm
    template_name = "meetings/meeting_form.html"
    context_object_name = "meeting"

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw["by_user"] = self.request.user
        return kw

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        form.instance.last_modified_by = self.request.user
        response = super().form_valid(form)
        log_audit_event(
            record_type=_record_type(self.object),
            record=self.object,
            action=AuditLog.ACTION_CREATE,
            user=self.request.user,
            new_values={
                "title": self.object.title,
                "reference": self.object.reference,
                "status": self.object.status,
                "start_at": getattr(
                    self.object.start_at, "isoformat", lambda: str(self.object.start_at)
                )(),
                "end_at": getattr(
                    self.object.end_at, "isoformat", lambda: str(self.object.end_at)
                )(),
            },
            ip_address=_client_ip(self.request),
        )
        messages.success(self.request, f"Meeting created: {self.object.reference}.")
        return response

    def get_success_url(self):
        return reverse("meetings:meeting_detail", args=[self.object.pk])


class MeetingUpdateView(
    LoginRequiredMixin,
    MeetingAuthorRequiredMixin,
    _MeetingFormMixin,
    UpdateView,
):
    model = Meeting
    form_class = MeetingForm
    template_name = "meetings/meeting_form.html"
    context_object_name = "meeting"

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw["by_user"] = self.request.user
        return kw

    def dispatch(self, request, *args, **kwargs):
        meeting = self.get_object()
        if not can_edit_meeting(request.user, meeting):
            from django.core.exceptions import PermissionDenied

            raise PermissionDenied("This meeting is locked or you are not authorized to edit it.")
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        form.instance.last_modified_by = self.request.user
        previous = getattr(form.instance, "_previous_values", {})
        changes = {}
        prev_safe = {}
        new_safe = {}
        for field in [
            "title",
            "description",
            "start_at",
            "end_at",
            "location",
            "type_id",
            "chair_id",
            "department_id",
            "status",
            "is_locked",
            "notes",
        ]:
            old = previous.get(field)
            new = getattr(form.instance, field, None)
            if field.endswith("_at") and old is not None:
                old = old.isoformat() if hasattr(old, "isoformat") else str(old)
                new = new.isoformat() if hasattr(new, "isoformat") else str(new)
            if old != new:
                changes[field] = {
                    "old": str(old) if old is not None else None,
                    "new": str(new) if new is not None else None,
                }
            prev_safe[field] = str(old) if old is not None else None
            new_safe[field] = str(new) if new is not None else None
        response = super().form_valid(form)
        if changes:
            log_audit_event(
                record_type=_record_type(self.object),
                record=self.object,
                action=AuditLog.ACTION_UPDATE,
                user=self.request.user,
                previous_values=prev_safe,
                new_values=new_safe,
                ip_address=_client_ip(self.request),
            )
        messages.success(self.request, f"Meeting {self.object.reference} updated.")
        return response

    def get_success_url(self):
        return reverse("meetings:meeting_detail", args=[self.object.pk])


class MeetingArchiveView(
    LoginRequiredMixin,
    ArchiveAuthorizedMixin,
    DetailView,
):
    model = Meeting
    http_method_names = ["post"]

    def post(self, request, *args, **kwargs):
        meeting = self.get_object()
        reason = request.POST.get("reason", "").strip() or (
            f"Archived by {request.user.get_display_name()}"
        )
        try:
            transition_meeting(meeting, STATUS_ARCHIVED, by_user=request.user, reason=reason)
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
            return redirect("meetings:meeting_detail", pk=meeting.pk)
        messages.success(request, f"Meeting {meeting.reference} archived.")
        return redirect("meetings:meeting_detail", pk=meeting.pk)


class MeetingTransitionView(LoginRequiredMixin, DetailView):
    model = Meeting
    http_method_names = ["post"]

    def post(self, request, *args, **kwargs):
        meeting = self.get_object()
        form = TransitionForm(request.POST, meeting=meeting, by_user=request.user)
        if not form.is_valid():
            for field, errs in form.errors.items():
                for err in errs:
                    messages.error(request, f"{field}: {err}" if field != "__all__" else err)
            return redirect("meetings:meeting_detail", pk=meeting.pk)
        target = form.cleaned_data["target_status"]
        reason = form.cleaned_data.get("reason", "")
        if not can_transition_meeting(request.user, meeting, target):
            from django.core.exceptions import PermissionDenied

            raise PermissionDenied("You are not authorized to perform this transition.")
        try:
            transition_meeting(meeting, target, by_user=request.user, reason=reason)
        except ValidationError as exc:
            for msg in exc.messages:
                messages.error(request, msg)
            return redirect("meetings:meeting_detail", pk=meeting.pk)
        messages.success(
            request, f"Meeting {meeting.reference} moved to {meeting.get_status_display()}."
        )
        return redirect("meetings:meeting_detail", pk=meeting.pk)


class MeetingAttendanceView(LoginRequiredMixin, DetailView):
    model = Meeting
    template_name = "meetings/meeting_attendance.html"
    context_object_name = "meeting"

    def dispatch(self, request, *args, **kwargs):
        meeting = self.get_object()
        if not (
            can_edit_meeting(request.user, meeting) or can_transition_meeting(request.user, meeting)
        ):
            from django.core.exceptions import PermissionDenied

            raise PermissionDenied()
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["formset"] = build_attendance_formset(self.object)
        return ctx

    def post(self, request, *args, **kwargs):
        meeting = self.get_object()
        self.object = meeting
        formset = build_attendance_formset(meeting, request.POST)
        if not formset.is_valid():
            for form in formset.forms:
                for field, errs in form.errors.items():
                    for err in errs:
                        messages.error(request, f"Row {form.prefix or ''} {field}: {err}")
            ctx = self.get_context_data(object=meeting)
            ctx["formset"] = formset
            return self.render_to_response(ctx)
        rows = formset.save()
        saved_pks = {obj.pk for obj in rows if hasattr(obj, "pk")}
        for form in formset.forms:
            if not getattr(form.instance, "pk", None):
                continue
            if formset.can_delete and formset._should_delete_form(form):
                continue
            if form.instance.pk in saved_pks or form.has_changed():
                log_audit_event(
                    record_type=_record_type(form.instance),
                    record=form.instance,
                    action=AuditLog.ACTION_ASSIGN,
                    user=request.user,
                    reason="Attendance update",
                    ip_address=_client_ip(request),
                )
        log_audit_event(
            record_type=_record_type(meeting),
            record=meeting,
            action=AuditLog.ACTION_ASSIGN,
            user=request.user,
            reason="Meeting attendance rows saved",
            ip_address=_client_ip(request),
        )
        messages.success(request, "Attendance saved.")
        return redirect("meetings:meeting_detail", pk=meeting.pk)


class AgendaCategoryListView(LoginRequiredMixin, MeetingAuthorRequiredMixin, ListView):
    model = AgendaCategory
    context_object_name = "categories"
    template_name = "meetings/agenda_categories.html"

    def get_queryset(self):
        return AgendaCategory.objects.select_related("scope_department").order_by("order", "name")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["new_form"] = AgendaCategoryForm()
        return ctx


class AgendaCategoryCreateView(LoginRequiredMixin, MeetingAuthorRequiredMixin, CreateView):
    model = AgendaCategory
    form_class = AgendaCategoryForm
    success_url = reverse_lazy("meetings:agenda_category_list")

    def form_valid(self, form):
        response = super().form_valid(form)
        log_audit_event(
            record_type=_record_type(self.object),
            record=self.object,
            action=AuditLog.ACTION_CREATE,
            user=self.request.user,
            new_values={"name": self.object.name, "order": self.object.order},
            ip_address=_client_ip(self.request),
        )
        messages.success(self.request, f"Agenda category created: {self.object.name}.")
        return response


class AgendaCategoryUpdateView(LoginRequiredMixin, MeetingAuthorRequiredMixin, UpdateView):
    model = AgendaCategory
    form_class = AgendaCategoryForm
    success_url = reverse_lazy("meetings:agenda_category_list")

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, f"Agenda category updated: {self.object.name}.")
        return response


class AgendaItemCreateView(LoginRequiredMixin, MeetingAuthorRequiredMixin, CreateView):
    model = AgendaItem
    form_class = AgendaItemForm
    template_name = "meetings/agenda_item_form.html"

    def dispatch(self, request, *args, **kwargs):
        self.meeting = get_object_or_404(Meeting, pk=self.kwargs["meeting_pk"])
        if not can_edit_meeting(request.user, self.meeting):
            from django.core.exceptions import PermissionDenied

            raise PermissionDenied("This meeting is locked for agenda edits.")
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw["meeting"] = self.meeting
        kw["by_user"] = self.request.user
        return kw

    def get_initial(self):
        initial = super().get_initial()
        max_order = AgendaItem.objects.filter(meeting=self.meeting).aggregate(
            m=models.Max("order")
        )["m"]
        initial["order"] = (max_order or -1) + 1
        return initial

    def form_valid(self, form):
        form.instance.meeting = self.meeting
        response = super().form_valid(form)
        log_audit_event(
            record_type=_record_type(self.object),
            record=self.object,
            action=AuditLog.ACTION_CREATE,
            user=self.request.user,
            new_values={
                "meeting": str(self.meeting.pk),
                "title": self.object.title,
                "order": self.object.order,
            },
            ip_address=_client_ip(self.request),
        )
        messages.success(self.request, f"Agenda item added: {self.object.title}.")
        return response

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["meeting"] = self.meeting
        return ctx

    def get_success_url(self):
        return reverse("meetings:meeting_detail", args=[self.meeting.pk]) + "#agenda"


class AgendaItemUpdateView(LoginRequiredMixin, MeetingAuthorRequiredMixin, UpdateView):
    model = AgendaItem
    form_class = AgendaItemForm
    template_name = "meetings/agenda_item_form.html"
    context_object_name = "item"

    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        if not can_edit_meeting(self.request.user, obj.meeting):
            from django.core.exceptions import PermissionDenied

            raise PermissionDenied("Cannot edit agenda items for a locked meeting.")
        return obj

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw["meeting"] = self.object.meeting
        kw["by_user"] = self.request.user
        return kw

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["meeting"] = self.object.meeting
        return ctx

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, f"Agenda item updated: {self.object.title}.")
        return response

    def get_success_url(self):
        return reverse("meetings:meeting_detail", args=[self.object.meeting_id]) + "#agenda"


class AgendaItemDeleteView(LoginRequiredMixin, MeetingAuthorRequiredMixin, DeleteView):
    model = AgendaItem
    context_object_name = "item"

    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        if not can_edit_meeting(self.request.user, obj.meeting):
            from django.core.exceptions import PermissionDenied

            raise PermissionDenied("Cannot delete agenda items for a locked meeting.")
        return obj

    def delete(self, request, *args, **kwargs):
        title = self.get_object().title
        messages.success(request, f"Agenda item deleted: {title}.")
        response = super().delete(request, *args, **kwargs)
        return response

    def get_success_url(self):
        return reverse("meetings:meeting_detail", args=[self.object.meeting_id]) + "#agenda"


class AgendaOrderSaveView(LoginRequiredMixin, MeetingAuthorRequiredMixin, View):
    http_method_names = ["post"]

    def post(self, request, meeting_pk):
        meeting = get_object_or_404(Meeting, pk=meeting_pk)
        if not can_edit_meeting(request.user, meeting):
            from django.core.exceptions import PermissionDenied

            raise PermissionDenied()
        form = AgendaOrderForm(request.POST)
        if not form.is_valid():
            return HttpResponseBadRequest(str(form.errors))
        ordered_pks = form.cleaned_data["item_order"]
        if not ordered_pks:
            return redirect(reverse("meetings:meeting_detail", args=[meeting.pk]) + "#agenda")
        with_meeting = list(
            AgendaItem.objects.filter(meeting=meeting, pk__in=ordered_pks).values_list(
                "pk", flat=True
            )
        )
        positions = {pk: idx for idx, pk in enumerate(ordered_pks) if pk in with_meeting}
        ordered_items = {
            item.pk: item for item in AgendaItem.objects.filter(pk__in=list(positions.keys()))
        }
        phase1 = []
        safe_offset = 2**31 - 1 - len(positions)
        for pk, item in ordered_items.items():
            item.order = safe_offset + positions[pk]
            phase1.append(item)
        AgendaItem.objects.bulk_update(phase1, ["order"])
        phase2 = []
        for pk, item in ordered_items.items():
            item.order = positions[pk]
            phase2.append(item)
        AgendaItem.objects.bulk_update(phase2, ["order"])
        messages.success(request, "Agenda order saved.")
        return redirect(reverse("meetings:meeting_detail", args=[meeting.pk]) + "#agenda")


class MeetingAttachmentUploadView(LoginRequiredMixin, MeetingAuthorRequiredMixin, View):
    http_method_names = ["post"]

    def post(self, request, meeting_pk):
        meeting = get_object_or_404(Meeting, pk=meeting_pk)
        if not can_edit_meeting(request.user, meeting):
            from django.core.exceptions import PermissionDenied

            raise PermissionDenied()
        form = MeetingAttachmentForm(request.POST, request.FILES, by_user=request.user)
        if not form.is_valid():
            for msg in form.errors.get("__all__", []):
                messages.error(request, msg)
            return redirect(reverse("meetings:meeting_detail", args=[meeting.pk]) + "#attachments")
        att = form.save(commit=False)
        att.meeting = meeting
        att.uploaded_by = request.user
        att.save()
        messages.success(request, "Attachment uploaded.")
        return redirect(reverse("meetings:meeting_detail", args=[meeting.pk]) + "#attachments")


class MeetingAttachmentDeleteView(LoginRequiredMixin, MeetingAuthorRequiredMixin, DeleteView):
    model = MeetingAttachment

    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        if not can_edit_meeting(self.request.user, obj.meeting):
            from django.core.exceptions import PermissionDenied

            raise PermissionDenied()
        return obj

    def get_success_url(self):
        return reverse("meetings:meeting_detail", args=[self.object.meeting_id]) + "#attachments"


class AgendaItemAttachmentUploadView(LoginRequiredMixin, MeetingAuthorRequiredMixin, View):
    http_method_names = ["post"]

    def post(self, request, item_pk):
        item = get_object_or_404(AgendaItem, pk=item_pk)
        if not can_edit_meeting(request.user, item.meeting):
            from django.core.exceptions import PermissionDenied

            raise PermissionDenied()
        form = AgendaItemAttachmentForm(request.POST, request.FILES, by_user=request.user)
        if not form.is_valid():
            return redirect(reverse("meetings:meeting_detail", args=[item.meeting_id]) + "#agenda")
        att = form.save(commit=False)
        att.item = item
        att.uploaded_by = request.user
        att.save()
        messages.success(request, "Agenda attachment uploaded.")
        return redirect(reverse("meetings:meeting_detail", args=[item.meeting_id]) + "#agenda")


class AgendaItemAttachmentDeleteView(LoginRequiredMixin, MeetingAuthorRequiredMixin, DeleteView):
    model = AgendaItemAttachment

    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        if not can_edit_meeting(self.request.user, obj.item.meeting):
            from django.core.exceptions import PermissionDenied

            raise PermissionDenied()
        return obj

    def get_success_url(self):
        return reverse("meetings:meeting_detail", args=[self.object.item.meeting_id]) + "#agenda"


class MeetingCarryForwardView(LoginRequiredMixin, MeetingAuthorRequiredMixin, View):
    http_method_names = ["post"]

    def post(self, request, pk):
        target = get_object_or_404(Meeting, pk=pk)
        if not can_edit_meeting(request.user, target):
            from django.core.exceptions import PermissionDenied

            raise PermissionDenied("Target meeting must be editable to carry items forward.")
        source_pk = request.POST.get("source_meeting")
        item_ids_raw = request.POST.get("item_ids", "") or ""
        import contextlib
        import uuid

        item_ids = []
        for part in [p.strip() for p in item_ids_raw.split(",") if p.strip()]:
            with contextlib.suppress(ValueError):
                item_ids.append(uuid.UUID(part))
        if not source_pk or not item_ids:
            messages.error(request, "Select a source meeting and at least one agenda item.")
            return redirect(reverse("meetings:meeting_detail", args=[target.pk]) + "#agenda")
        source = get_object_or_404(Meeting, pk=source_pk)
        copied = carry_forward_agenda_items(source, target, item_ids, by_user=request.user)
        messages.success(request, f"Carried forward {len(copied)} agenda item(s).")
        return redirect(reverse("meetings:meeting_detail", args=[target.pk]) + "#agenda")


class PrepDashboard(LoginRequiredMixin, ListView):
    model = Meeting
    context_object_name = "meetings"
    template_name = "meetings/prep_dashboard.html"
    paginate_by = 30

    def get_queryset(self):
        now = timezone.now()
        window_start = now.date()
        window_end = window_start + timedelta(days=60)
        qs = (
            Meeting.objects.filter(
                start_at__date__gte=window_start,
                start_at__date__lte=window_end,
            )
            .select_related("type", "chair", "department", "created_by")
            .prefetch_related(
                "department_submissions__department",
                "department_submissions__contributor",
                "agenda_items",
            )
            .order_by("start_at")
        )
        user = self.request.user
        if not (
            getattr(user, "is_superuser", False)
            or user.has_role(
                "System Administrator",
                "Management Administrator",
                "Meeting Chairperson",
                "Minutes Secretary",
            )
        ):
            visible_depts = (
                set(user.get_assigned_departments().values_list("pk", flat=True))
                if getattr(user, "is_authenticated", False)
                else set()
            )
            qs = qs.filter(
                models.Q(department_id__in=visible_depts) | models.Q(department__isnull=True)
            )
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        counts, _ = meetings_prep_dashboard_data(self.request.user)
        ctx["dashboard_counts"] = counts
        ctx["status_choices"] = STATUS_CHOICES
        return ctx


class DeptSubmissionStatusDetail(LoginRequiredMixin, DetailView):
    model = Meeting
    context_object_name = "meeting"
    template_name = "meetings/dept_submission_status.html"

    def get_queryset(self):
        return (
            Meeting.objects.all()
            .select_related("type", "chair", "department")
            .prefetch_related(
                "department_submissions__department",
                "department_submissions__contributor",
                "department_submissions__submitted_by",
                "type__section_specs",
            )
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        meeting = self.object
        ctx["submissions"] = list(meeting.department_submissions.all())
        ctx["section_specs"] = list(
            MinutesSectionSpec.objects.filter(meeting_type=meeting.type_id).order_by("order")
        )
        ctx["can_edit"] = can_submit_minutes(self.request.user, meeting)
        return ctx


class DeptSubmissionUpsert(LoginRequiredMixin, MinutesEditRequiredMixin, FormView):
    template_name = "meetings/dept_submission_form.html"
    fields = [
        "department",
        "contributor",
        "submission_state",
        "missing_info",
        "management_remarks",
        "notes",
    ]

    def get_meeting(self):
        return get_object_or_404(Meeting, pk=self.kwargs["pk"])

    def dispatch(self, request, *args, **kwargs):
        self.meeting = self.get_meeting()
        if not can_submit_minutes(request.user, self.meeting):
            from django.core.exceptions import PermissionDenied

            raise PermissionDenied()
        return super().dispatch(request, *args, **kwargs)

    def get_form_class(self):
        from django import forms as dj_forms

        from apps.meetings.models import SUBMISSION_STATUS_CHOICES

        class _DeptSubmissionForm(dj_forms.ModelForm):
            class Meta:
                model = DepartmentSubmission
                fields = [
                    "department",
                    "contributor",
                    "submission_state",
                    "missing_info",
                    "management_remarks",
                    "notes",
                ]
                widgets = {
                    "submission_state": dj_forms.Select(attrs={"class": "form-select"}),
                    "department": dj_forms.Select(attrs={"class": "form-select"}),
                    "contributor": dj_forms.Select(attrs={"class": "form-select"}),
                    "missing_info": dj_forms.Textarea(attrs={"class": "form-control", "rows": 2}),
                    "management_remarks": dj_forms.Textarea(
                        attrs={"class": "form-control", "rows": 2}
                    ),
                    "notes": dj_forms.Textarea(attrs={"class": "form-control", "rows": 2}),
                }

            def __init__(self_inner, *args, **kwargs):
                super().__init__(*args, **kwargs)
                from django.contrib.auth import get_user_model

                User = get_user_model()
                self_inner.fields["department"].queryset = Department.objects.filter(
                    is_active=True
                ).order_by("name")
                self_inner.fields["contributor"].queryset = User.objects.filter(
                    is_active=True
                ).order_by("username")
                self_inner.fields["submission_state"].choices = SUBMISSION_STATUS_CHOICES

        return _DeptSubmissionForm

    def get_initial(self):
        initial = super().get_initial()
        dept_pk = self.request.GET.get("department") or self.request.POST.get("department")
        if dept_pk:
            try:
                existing = DepartmentSubmission.objects.get(
                    meeting=self.meeting, department_id=dept_pk
                )
                for f in self.fields:
                    if hasattr(existing, f):
                        val = getattr(existing, f)
                        if hasattr(val, "pk"):
                            initial[f] = val.pk
                        else:
                            initial[f] = val
            except DepartmentSubmission.DoesNotExist:
                pass
        return initial

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["meeting"] = self.meeting
        return ctx

    def form_valid(self, form):
        data = form.cleaned_data
        try:
            dept_submission_upsert(
                self.meeting,
                data["department"],
                by_user=self.request.user,
                submission_state=data["submission_state"],
                missing_info=data.get("missing_info", ""),
                management_remarks=data.get("management_remarks", ""),
                notes=data.get("notes", ""),
                contributor=data.get("contributor"),
            )
        except ValidationError as exc:
            for msg in exc.messages:
                messages.error(self.request, msg)
            return self.form_invalid(form)
        messages.success(self.request, "Department submission saved.")
        return redirect("meetings:dept_submission_status_detail", pk=self.meeting.pk)


class MinutesEditorView(LoginRequiredMixin, MinutesEditRequiredMixin, UpdateView):
    model = Meeting
    form_class = MinutesEditorForm
    context_object_name = "meeting"
    template_name = "meetings/minutes_editor.html"

    def get_queryset(self):
        return (
            Meeting.objects.all()
            .select_related("type", "chair", "department", "created_by", "last_modified_by")
            .prefetch_related(
                "agenda_items__category",
                "agenda_items__owner",
                "agenda_items__action_item_links__action_item",
                "department_submissions",
                "attachments",
            )
        )

    def dispatch(self, request, *args, **kwargs):
        meeting = self.get_object()
        if not can_submit_minutes(request.user, meeting):
            from django.core.exceptions import PermissionDenied

            raise PermissionDenied()
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        meeting = self.object
        ctx["agenda_items"] = list(
            meeting.agenda_items.all()
            .order_by("order")
            .select_related("category", "owner", "department")
        )
        ctx["validation_rows"] = agenda_completeness(meeting)
        ctx["can_submit"] = can_submit_minutes(self.request.user, meeting)
        ctx["can_return"] = can_return_minutes(self.request.user, meeting)
        return ctx

    def form_valid(self, form):
        form.instance.last_modified_by = self.request.user
        response = super().form_valid(form)
        messages.success(self.request, f"Minutes notes updated for {self.object.reference}.")
        return response

    def get_success_url(self):
        return reverse("meetings:minutes_editor", args=[self.object.pk])


class ActionItemFromMinutesCreate(LoginRequiredMixin, MinutesEditRequiredMixin, CreateView):
    model = ActionItem
    form_class = ActionItemCreateFromMinutesForm
    template_name = "meetings/actionitem_create_from_minutes.html"

    def get_meeting(self):
        return get_object_or_404(Meeting, pk=self.kwargs["meeting_pk"])

    def dispatch(self, request, *args, **kwargs):
        self.meeting = self.get_meeting()
        self.agenda_item = None
        agenda_pk = request.GET.get("agenda_item") or request.POST.get("agenda_item")
        if agenda_pk:
            self.agenda_item = get_object_or_404(AgendaItem, pk=agenda_pk, meeting=self.meeting)
        if not can_submit_minutes(request.user, self.meeting):
            from django.core.exceptions import PermissionDenied

            raise PermissionDenied()
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw["source_meeting"] = self.meeting
        kw["source_agenda_item"] = self.agenda_item
        return kw

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["meeting"] = self.meeting
        ctx["agenda_item"] = self.agenda_item
        return ctx

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        form.instance.last_modified_by = self.request.user
        with transaction.atomic():
            response = super().form_valid(form)
            if self.agenda_item is not None:
                ActionItemLink.objects.get_or_create(
                    agenda_item=self.agenda_item,
                    action_item=self.object,
                    defaults={"created_by": self.request.user},
                )
            log_audit_event(
                record_type=_record_type(self.object),
                record=self.object,
                action=AuditLog.ACTION_CREATE,
                user=self.request.user,
                new_values={
                    "title": self.object.title,
                    "reference": self.object.reference,
                    "source_meeting": str(self.meeting.pk),
                    "source_agenda_item": str(self.agenda_item.pk) if self.agenda_item else None,
                },
                ip_address=_client_ip(self.request),
            )
        messages.success(self.request, f"Action item {self.object.reference} created from minutes.")
        return response

    def get_success_url(self):
        return reverse("meetings:minutes_editor", args=[self.meeting.pk]) + "#agenda"


class MeetingPreviewView(LoginRequiredMixin, DetailView):
    model = Meeting
    context_object_name = "meeting"
    template_name = "meetings/meeting_preview.html"

    def get_queryset(self):
        return (
            Meeting.objects.all()
            .select_related("type", "chair", "department", "created_by", "last_modified_by")
            .prefetch_related(
                "attendance__user",
                "agenda_items__category",
                "agenda_items__owner",
                "agenda_items__department",
                "agenda_items__action_item_links__action_item__owner",
                "attachments",
                "approved_snapshots",
                "status_history__transitioned_by",
            )
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        meeting = self.object
        ctx["can_view_confidential"] = can_view_confidential_items(
            self.request.user, meeting=meeting
        )
        return ctx


class MeetingValidationSummaryView(LoginRequiredMixin, DetailView):
    model = Meeting
    context_object_name = "meeting"
    template_name = "meetings/validation_summary.html"

    def get_queryset(self):
        return (
            Meeting.objects.all()
            .select_related("type", "chair", "department")
            .prefetch_related(
                "type__section_specs",
                "department_submissions__department",
                "agenda_items",
            )
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        meeting = self.object
        rows = agenda_completeness(meeting)
        ctx["validation_rows"] = rows
        ctx["all_passed"] = all(r["passed"] for r in rows)
        ctx["can_submit"] = can_submit_minutes(self.request.user, meeting)
        return ctx


class SubmitForReviewView(LoginRequiredMixin, MinutesEditRequiredMixin, DetailView):
    model = Meeting
    http_method_names = ["post"]

    def post(self, request, *args, **kwargs):
        meeting = self.get_object()
        if not can_submit_minutes(request.user, meeting):
            from django.core.exceptions import PermissionDenied

            raise PermissionDenied()
        reason = request.POST.get("reason", "").strip()
        try:
            submit_for_review(meeting, by_user=request.user, reason=reason)
        except ValidationError as exc:
            for msg in exc.messages:
                messages.error(request, msg)
            return redirect("meetings:meeting_validation_summary", pk=meeting.pk)
        messages.success(request, f"Meeting {meeting.reference} submitted for review.")
        return redirect("meetings:meeting_detail", pk=meeting.pk)


class ReturnForCorrectionView(LoginRequiredMixin, MinutesReviewRequiredMixin, FormView):
    form_class = ReturnForCorrectionForm
    template_name = "meetings/return_for_correction_form.html"

    def get_meeting(self):
        return get_object_or_404(Meeting, pk=self.kwargs["pk"])

    def dispatch(self, request, *args, **kwargs):
        self.meeting = self.get_meeting()
        if not can_return_minutes(request.user, self.meeting):
            from django.core.exceptions import PermissionDenied

            raise PermissionDenied()
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["meeting"] = self.meeting
        return ctx

    def form_valid(self, form):
        data = form.cleaned_data
        marked = set(data.get("section_types") or [])
        try:
            return_for_correction(
                self.meeting,
                by_user=self.request.user,
                reason=data["reason"],
                marked_section_types=marked,
                management_remarks=data.get("management_remarks", ""),
            )
        except ValidationError as exc:
            for msg in exc.messages:
                messages.error(self.request, msg)
            return self.form_invalid(form)
        messages.success(
            self.request,
            f"Meeting {self.meeting.reference} returned for correction.",
        )
        return redirect("meetings:meeting_detail", pk=self.meeting.pk)


class ResubmitForReviewView(LoginRequiredMixin, MinutesEditRequiredMixin, DetailView):
    model = Meeting
    http_method_names = ["post"]

    def post(self, request, *args, **kwargs):
        meeting = self.get_object()
        if not can_resubmit_minutes(request.user, meeting):
            from django.core.exceptions import PermissionDenied

            raise PermissionDenied()
        reason = request.POST.get("reason", "").strip()
        try:
            resubmit_for_review(meeting, by_user=request.user, reason=reason)
        except ValidationError as exc:
            for msg in exc.messages:
                messages.error(request, msg)
            return redirect("meetings:meeting_detail", pk=meeting.pk)
        messages.success(request, f"Meeting {meeting.reference} resubmitted for review.")
        return redirect("meetings:meeting_detail", pk=meeting.pk)


class ApproveMeetingView(LoginRequiredMixin, MinutesApproverRequiredMixin, DetailView):
    model = Meeting
    http_method_names = ["post"]

    def post(self, request, *args, **kwargs):
        meeting = self.get_object()
        if not can_approve_meeting(request.user, meeting):
            from django.core.exceptions import PermissionDenied

            raise PermissionDenied()
        reason = request.POST.get("reason", "").strip()
        try:
            approve_meeting(meeting, by_user=request.user, reason=reason)
        except ValidationError as exc:
            for msg in exc.messages:
                messages.error(request, msg)
            return redirect("meetings:meeting_detail", pk=meeting.pk)
        messages.success(request, f"Meeting {meeting.reference} approved.")
        return redirect("meetings:meeting_detail", pk=meeting.pk)


class PublishMeetingView(LoginRequiredMixin, MinutesApproverRequiredMixin, DetailView):
    model = Meeting
    http_method_names = ["post"]

    def post(self, request, *args, **kwargs):
        meeting = self.get_object()
        if not can_publish_meeting(request.user, meeting):
            from django.core.exceptions import PermissionDenied

            raise PermissionDenied()
        reason = request.POST.get("reason", "").strip()
        try:
            publish_meeting(meeting, by_user=request.user, reason=reason)
        except ValidationError as exc:
            for msg in exc.messages:
                messages.error(request, msg)
            return redirect("meetings:meeting_detail", pk=meeting.pk)
        messages.success(request, f"Meeting {meeting.reference} published.")
        return redirect("meetings:meeting_detail", pk=meeting.pk)


class CloseMeetingView(LoginRequiredMixin, MinutesApproverRequiredMixin, DetailView):
    model = Meeting
    http_method_names = ["post"]

    def post(self, request, *args, **kwargs):
        meeting = self.get_object()
        if not can_close_meeting(request.user, meeting):
            from django.core.exceptions import PermissionDenied

            raise PermissionDenied()
        reason = request.POST.get("reason", "").strip()
        try:
            close_meeting(meeting, by_user=request.user, reason=reason)
        except ValidationError as exc:
            for msg in exc.messages:
                messages.error(request, msg)
            return redirect("meetings:meeting_detail", pk=meeting.pk)
        messages.success(request, f"Meeting {meeting.reference} closed.")
        return redirect("meetings:meeting_detail", pk=meeting.pk)


class ReopenMeetingView(LoginRequiredMixin, ReopenAuthorizedMixin, FormView):
    template_name = "meetings/return_for_correction_form.html"

    def get_form_class(self):
        from django import forms as dj_forms

        allowed = {
            STATUS_APPROVED: [
                STATUS_RETURNED_FOR_CORRECTION,
                STATUS_APPROVED,
                STATUS_CLOSED,
                STATUS_PUBLISHED,
            ],
            STATUS_PUBLISHED: [
                STATUS_RETURNED_FOR_CORRECTION,
                STATUS_APPROVED,
                STATUS_CLOSED,
                STATUS_PUBLISHED,
            ],
            STATUS_CLOSED: [
                STATUS_RETURNED_FOR_CORRECTION,
                STATUS_APPROVED,
                STATUS_PUBLISHED,
            ],
            STATUS_ARCHIVED: [STATUS_APPROVED, STATUS_PUBLISHED, STATUS_CLOSED],
        }
        current = self.meeting.status
        target_labels = [
            (s, label) for s, label in STATUS_CHOICES if s in allowed.get(current, set())
        ]

        class _ReopenForm(dj_forms.Form):
            reason = dj_forms.CharField(
                required=True,
                label="Reopen Reason (required)",
                widget=dj_forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            )
            target_status = dj_forms.ChoiceField(
                choices=target_labels,
                label="Target Status",
                widget=dj_forms.Select(attrs={"class": "form-select"}),
            )

        return _ReopenForm

    def get_meeting(self):
        return get_object_or_404(Meeting, pk=self.kwargs["pk"])

    def dispatch(self, request, *args, **kwargs):
        self.meeting = self.get_meeting()
        if not can_reopen_meeting(request.user, self.meeting):
            from django.core.exceptions import PermissionDenied

            raise PermissionDenied()
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["meeting"] = self.meeting
        return ctx

    def form_valid(self, form):
        data = form.cleaned_data
        try:
            reopen_meeting(
                self.meeting,
                by_user=self.request.user,
                target_status=data["target_status"],
                reason=data["reason"],
            )
        except ValidationError as exc:
            for msg in exc.messages:
                messages.error(self.request, msg)
            return self.form_invalid(form)
        messages.success(
            self.request,
            f"Meeting {self.meeting.reference} reopened to {dict(STATUS_CHOICES).get(data['target_status'], data['target_status'])}.",
        )
        return redirect("meetings:meeting_detail", pk=self.meeting.pk)


class MeetingVersionHistoryView(LoginRequiredMixin, DetailView):
    model = Meeting
    context_object_name = "meeting"
    template_name = "meetings/version_history.html"

    def get_queryset(self):
        return (
            Meeting.objects.all()
            .select_related("type", "chair", "department")
            .prefetch_related(
                "approved_snapshots__approved_by",
                "approved_snapshots__published_by",
                "status_history__transitioned_by",
            )
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        meeting = self.object
        timeline = []
        for h in meeting.status_history.all():
            timeline.append(
                {
                    "type": "status",
                    "timestamp": h.transitioned_at,
                    "actor": h.transitioned_by,
                    "title": f"{h.from_status or 'DRAFT'} → {h.to_status}",
                    "reason": h.reason,
                }
            )
        for s in meeting.approved_snapshots.all():
            timeline.append(
                {
                    "type": "snapshot",
                    "timestamp": s.approved_at or s.created_at,
                    "actor": s.approved_by or s.published_by,
                    "title": f"Snapshot v{s.version} ({s.get_trigger_display()})",
                    "snapshot": s,
                }
            )
        timeline.sort(key=lambda e: e["timestamp"] or timezone.now(), reverse=True)
        ctx["timeline"] = timeline
        ctx["snapshots"] = list(meeting.approved_snapshots.all().order_by("-version"))
        ctx["status_history"] = list(meeting.status_history.all().order_by("-transitioned_at"))
        return ctx


class ApprovedSnapshotDetailView(LoginRequiredMixin, DetailView):
    model = ApprovedMeetingSnapshot
    context_object_name = "snapshot"
    template_name = "meetings/approved_snapshot_detail.html"

    def get_queryset(self):
        return ApprovedMeetingSnapshot.objects.select_related(
            "meeting", "approved_by", "published_by"
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        snapshot = self.object
        payload = snapshot.payload or {}
        ctx["payload"] = payload
        ctx["meeting_meta"] = payload.get("meeting_meta", {})
        ctx["attendance"] = payload.get("attendance", [])
        ctx["agenda_items"] = payload.get("agenda_items", [])
        ctx["discussions"] = payload.get("discussions", [])
        ctx["decisions"] = payload.get("decisions", [])
        ctx["action_items"] = payload.get("action_items", [])
        ctx["sales_data"] = payload.get("sales_data", {})
        ctx["status_history"] = payload.get("status_history", [])
        ctx["approval_meta"] = payload.get("approval_meta", {})
        ctx["snapshot_version"] = payload.get("version", snapshot.version)
        return ctx


class SnapshotPrintableView(LoginRequiredMixin, DetailView):
    model = ApprovedMeetingSnapshot
    context_object_name = "snapshot"
    template_name = "meetings/snapshot_printable.html"

    def get_queryset(self):
        return ApprovedMeetingSnapshot.objects.select_related(
            "meeting", "approved_by", "published_by"
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        snapshot = self.object
        payload = snapshot.payload or {}
        ctx["payload"] = payload
        ctx["meeting_meta"] = payload.get("meeting_meta", {})
        ctx["attendance"] = payload.get("attendance", [])
        ctx["agenda_items"] = payload.get("agenda_items", [])
        ctx["discussions"] = payload.get("discussions", [])
        ctx["decisions"] = payload.get("decisions", [])
        ctx["action_items"] = payload.get("action_items", [])
        ctx["sales_data"] = payload.get("sales_data", {})
        ctx["approval_meta"] = payload.get("approval_meta", {})
        ctx["snapshot_version"] = payload.get("version", snapshot.version)
        return ctx
