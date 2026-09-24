from __future__ import annotations

import contextlib
import uuid

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    ListView,
    UpdateView,
    View,
)

from apps.accounts.models import Department
from apps.action_items.forms import (
    ActionItemAttachmentForm,
    ActionItemCompleteForm,
    ActionItemCreateForm,
    ActionItemReopenForm,
    ActionItemTransitionForm,
    CarryForwardActionItemsForm,
    build_assignees_formset,
)
from apps.action_items.forms import (
    ActionItemUpdateForm as ActionItemEditForm,
)
from apps.action_items.forms import (
    ActionItemUpdateFormCreate as ActionItemNewUpdateForm,
)
from apps.action_items.models import (
    PRIORITY_CHOICES,
    STATUS_CHOICES,
    STATUS_COMPLETED,
    STATUS_IN_PROGRESS,
    STATUS_REOPENED,
    ActionItem,
    ActionItemAttachment,
    ActionItemUpdate,
)
from apps.action_items.services import (
    carry_forward_action_items,
    dashboard_action_counts,
    overdue_action_items_queryset,
    transition_actionitem,
)
from apps.audit.models import AuditLog
from apps.audit.services import log_audit_event
from apps.core.permissions import (
    ACTION_AUTHOR_ROLES,
    ROLE_MANAGEMENT_ADMIN,
    ROLE_SYSTEM_ADMIN,
    ActionItemAuthorRequiredMixin,
    ActionItemCompleteMixin,
    can_complete_actionitem,
    can_create_actionitem,
    can_edit_actionitem,
    can_reopen_actionitem,
    can_view_actionitem,
)
from apps.meetings.models import AgendaItem


def _client_ip(request) -> str | None:
    return request.META.get("REMOTE_ADDR")


def _record_type(instance) -> str:
    class_name = instance.__class__.__name__.lower()
    return f"action_items.{class_name}"


class ActionItemQuerysetHelpers:
    def get_base_queryset(self):
        return ActionItem.objects.select_related(
            "owner",
            "department",
            "created_by",
            "source_meeting",
            "source_agenda_item",
            "carried_forward_from",
        ).prefetch_related("assignees__user")

    def get_visible_for_user(self, qs, user):
        if getattr(user, "is_superuser", False) or user.has_role(
            ROLE_SYSTEM_ADMIN, ROLE_MANAGEMENT_ADMIN
        ):
            return qs
        if user.has_role(*ACTION_AUTHOR_ROLES):
            depts = set(user.get_contributor_departments().values_list("pk", flat=True))
            return qs.filter(
                pk__in=self._related_qs_for_user(user).values_list("pk", flat=True)
            ) | qs.filter(department_id__in=[*list(depts), None])
        return qs.filter(pk__in=self._related_qs_for_user(user).values_list("pk", flat=True))

    def _related_qs_for_user(self, user):
        return ActionItem.objects.filter(assignees__user=user) | ActionItem.objects.filter(
            owner_id=getattr(user, "pk", None)
        )


class ActionItemListView(LoginRequiredMixin, ActionItemQuerysetHelpers, ListView):
    model = ActionItem
    context_object_name = "actions"
    template_name = "action_items/actionitem_list.html"
    paginate_by = 25

    def get_queryset(self):
        qs = self.get_base_queryset()
        qs = self.get_visible_for_user(qs, self.request.user)
        status = self.request.GET.get("status", "").strip()
        if status and any(status == s for s, _ in STATUS_CHOICES):
            qs = qs.filter(status=status)
        priority = self.request.GET.get("priority", "").strip()
        if priority and any(priority == p for p, _ in PRIORITY_CHOICES):
            qs = qs.filter(priority=priority)
        dept = self.request.GET.get("department", "").strip()
        if dept:
            qs = qs.filter(department_id=dept)
        due_from = self.request.GET.get("due_from", "").strip()
        if due_from:
            with contextlib.suppress(ValidationError):
                qs = qs.filter(due_date__gte=due_from)
        due_to = self.request.GET.get("due_to", "").strip()
        if due_to:
            with contextlib.suppress(ValidationError):
                qs = qs.filter(due_date__lte=due_to)
        search = self.request.GET.get("q", "").strip()
        if search:
            qs = qs.filter(title__icontains=search) | qs.filter(description__icontains=search)
        return qs.distinct()

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["status_choices"] = STATUS_CHOICES
        ctx["priority_choices"] = PRIORITY_CHOICES
        ctx["departments"] = Department.objects.filter(is_active=True).order_by("name")
        ctx["filter_applied"] = any(
            self.request.GET.get(k, "")
            for k in ("status", "priority", "department", "due_from", "due_to", "q")
        )
        ctx["can_create"] = can_create_actionitem(self.request.user)
        return ctx


class ActionItemMyView(ActionItemListView):
    template_name = "action_items/actionitem_list_my.html"
    paginate_by = 25

    def get_queryset(self):
        qs = super().get_queryset()
        return qs.filter(
            pk__in=self._related_qs_for_user(self.request.user).values_list("pk", flat=True)
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["heading"] = "My Action Items"
        ctx["badge"] = "Assigned to me"
        return ctx


class ActionItemDepartmentView(ActionItemListView):
    template_name = "action_items/actionitem_list_dept.html"
    paginate_by = 25

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        dept_pks = set(user.get_contributor_departments().values_list("pk", flat=True))
        if not dept_pks and not getattr(user, "is_superuser", False):
            return qs.none()
        if getattr(user, "is_superuser", False) or user.has_role(
            ROLE_SYSTEM_ADMIN, ROLE_MANAGEMENT_ADMIN
        ):
            return qs
        return qs.filter(department_id__in=dept_pks)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["heading"] = "Department Action Items"
        ctx["badge"] = "Contributor departments"
        return ctx


class ActionItemOverdueView(ActionItemListView):
    template_name = "action_items/actionitem_list_overdue.html"
    paginate_by = 25

    def get_queryset(self):
        base = overdue_action_items_queryset(self.request.user)
        return self.get_visible_for_user(base, self.request.user).distinct()

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["heading"] = "Overdue Action Items"
        ctx["badge"] = "Overdue"
        return ctx


class ActionItemDetailView(LoginRequiredMixin, DetailView):
    model = ActionItem
    context_object_name = "action"
    template_name = "action_items/actionitem_detail.html"

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        self.object = self.get_object()
        if not can_view_actionitem(request.user, self.object):
            raise PermissionDenied()
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return ActionItem.objects.select_related(
            "owner",
            "department",
            "created_by",
            "source_meeting",
            "source_agenda_item",
            "carried_forward_from",
        ).prefetch_related(
            "assignees__user",
            "updates__author",
            "attachments__uploaded_by",
            "status_history__transitioned_by",
            "carried_forward_links__source_item",
            "carry_forward_sources__new_item",
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["can_edit"] = can_edit_actionitem(self.request.user, self.object)
        ctx["can_complete"] = can_complete_actionitem(self.request.user, self.object)
        ctx["can_reopen"] = can_reopen_actionitem(self.request.user, self.object)
        ctx["transition_form"] = ActionItemTransitionForm(
            action_item=self.object,
            by_user=self.request.user,
        )
        ctx["assignee_formset"] = build_assignees_formset(self.object)
        ctx["update_form"] = ActionItemNewUpdateForm(by_user=self.request.user)
        ctx["attachment_form"] = ActionItemAttachmentForm(by_user=self.request.user)
        return ctx


class ActionItemCreateMixin(LoginRequiredMixin):
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not can_create_actionitem(request.user):
            raise PermissionDenied()
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        form.instance.last_modified_by = self.request.user
        resp = super().form_valid(form)
        log_audit_event(
            record_type=_record_type(form.instance),
            record=form.instance,
            action=AuditLog.ACTION_CREATE,
            user=self.request.user,
            reason="Created action item",
            ip_address=_client_ip(self.request),
        )
        return resp


class ActionItemCreateView(ActionItemCreateMixin, CreateView):
    model = ActionItem
    form_class = ActionItemCreateForm
    template_name = "action_items/actionitem_form.html"
    context_object_name = "action"

    def get_success_url(self):
        return reverse("action_items:actionitem_detail", args=[self.object.pk])

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["mode"] = "Create"
        ctx["assignee_formset"] = build_assignees_formset(self.object or ActionItem())
        return ctx

    def form_valid(self, form):
        resp = super().form_valid(form)
        formset = build_assignees_formset(self.object, self.request.POST)
        if formset.is_valid():
            formset.save()
        return resp


class ActionItemFromAgendaItemView(ActionItemCreateMixin, CreateView):
    model = ActionItem
    form_class = ActionItemCreateForm
    template_name = "action_items/actionitem_form.html"
    context_object_name = "action"

    def dispatch(self, request, *args, agenda_pk=None, **kwargs):
        self.agenda_item = get_object_or_404(AgendaItem, pk=agenda_pk)
        return super().dispatch(request, *args, **kwargs)

    def get_initial(self):
        initial = super().get_initial()
        agenda = self.agenda_item
        meeting = getattr(agenda, "meeting", None)
        initial["title"] = agenda.title
        initial["description"] = (
            f"From meeting {getattr(meeting, 'reference', '?')} — {agenda.discussion or ''}"
        ).strip()
        initial["owner"] = getattr(agenda, "owner_id", None)
        initial["department"] = getattr(agenda, "department_id", None) or getattr(
            meeting, "department_id", None
        )
        if meeting and getattr(meeting, "start_at", None):
            default_due = meeting.start_at.date() + timezone.timedelta(days=14)
            initial["due_date"] = default_due
        initial["status"] = STATUS_IN_PROGRESS
        return initial

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["mode"] = "Create from Agenda"
        ctx["from_agenda"] = self.agenda_item
        ctx["assignee_formset"] = build_assignees_formset(self.object or ActionItem())
        return ctx

    def form_valid(self, form):
        form.instance.source_agenda_item = self.agenda_item
        form.instance.source_meeting = getattr(self.agenda_item, "meeting", None)
        if form.instance.owner is None and getattr(self.agenda_item, "owner_id", None):
            form.instance.owner_id = self.agenda_item.owner_id
        resp = super().form_valid(form)
        if form.instance.owner_id:
            from apps.action_items.models import ActionItemAssignee

            ActionItemAssignee.objects.get_or_create(
                action_item=self.object,
                user_id=form.instance.owner_id,
                defaults={"is_primary": True, "is_supporting": False},
            )
        return resp

    def get_success_url(self):
        return reverse("action_items:actionitem_detail", args=[self.object.pk])


class ActionItemUpdateView(LoginRequiredMixin, ActionItemAuthorRequiredMixin, UpdateView):
    model = ActionItem
    form_class = ActionItemEditForm
    template_name = "action_items/actionitem_form.html"
    context_object_name = "action"

    def get_success_url(self):
        return reverse("action_items:actionitem_detail", args=[self.object.pk])

    def form_valid(self, form):
        form.instance.last_modified_by = self.request.user
        resp = super().form_valid(form)
        log_audit_event(
            record_type=_record_type(form.instance),
            record=form.instance,
            action=AuditLog.ACTION_UPDATE,
            user=self.request.user,
            ip_address=_client_ip(self.request),
            reason="Action item updated",
        )
        formset = build_assignees_formset(self.object, self.request.POST)
        if formset.is_valid():
            formset.save()
        return resp

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["mode"] = "Edit"
        ctx["assignee_formset"] = build_assignees_formset(self.object)
        return ctx


class ActionItemDeleteView(LoginRequiredMixin, ActionItemAuthorRequiredMixin, DeleteView):
    model = ActionItem
    success_url = reverse_lazy("action_items:actionitem_list")

    def delete(self, request, *args, **kwargs):
        obj = self.get_object()
        title = obj.title
        log_audit_event(
            record_type=_record_type(obj),
            record=obj,
            action=AuditLog.ACTION_DELETE,
            user=request.user,
            ip_address=_client_ip(request),
            reason=f"Deleted: {title[:80]}",
        )
        messages.success(request, f"Action item deleted: {title[:80]}.")
        return super().delete(request, *args, **kwargs)


class ActionItemAssigneeSaveView(LoginRequiredMixin, ActionItemAuthorRequiredMixin, View):
    http_method_names = ["post"]

    def post(self, request, pk):
        action = get_object_or_404(ActionItem, pk=pk)
        if not can_edit_actionitem(request.user, action):
            raise PermissionDenied()
        formset = build_assignees_formset(action, request.POST)
        if not formset.is_valid():
            for form in formset.forms:
                for field, errs in form.errors.items():
                    for err in errs:
                        messages.error(request, f"Row {field}: {err}")
            return redirect(
                reverse("action_items:actionitem_detail", args=[action.pk]) + "#assignees"
            )
        saved = formset.save()
        for form in formset.forms:
            if not getattr(form.instance, "pk", None):
                continue
            if formset.can_delete and formset._should_delete_form(form):
                continue
            pk_set = {getattr(o, "pk", None) for o in saved}
            if form.instance.pk in pk_set or form.has_changed():
                log_audit_event(
                    record_type=_record_type(form.instance),
                    record=form.instance,
                    action=AuditLog.ACTION_ASSIGN,
                    user=request.user,
                    reason="Assignee row updated",
                )
        log_audit_event(
            record_type=_record_type(action),
            record=action,
            action=AuditLog.ACTION_ASSIGN,
            user=request.user,
            reason="Assignees saved",
        )
        messages.success(request, "Assignees saved.")
        return redirect(reverse("action_items:actionitem_detail", args=[action.pk]) + "#assignees")


class ActionItemTransitionView(LoginRequiredMixin, View):
    http_method_names = ["post"]

    def post(self, request, pk):
        action = get_object_or_404(ActionItem, pk=pk)
        if not can_edit_actionitem(request.user, action):
            raise PermissionDenied()
        form = ActionItemTransitionForm(request.POST, action_item=action, by_user=request.user)
        form.by_user = request.user
        if not form.is_valid():
            for _, errs in form.errors.items():
                for err in errs:
                    messages.error(request, err)
            return redirect(reverse("action_items:actionitem_detail", args=[action.pk]) + "#status")
        target = form.cleaned_data["target_status"]
        reason = form.cleaned_data.get("reason", "")
        try:
            transition_actionitem(action, target, by_user=request.user, reason=reason)
        except ValidationError as err:
            for msg in err.messages:
                messages.error(request, msg)
            return redirect(reverse("action_items:actionitem_detail", args=[action.pk]) + "#status")
        messages.success(request, f"Status changed to {action.get_status_display()}.")
        return redirect(reverse("action_items:actionitem_detail", args=[action.pk]) + "#status")


class ActionItemCompleteView(LoginRequiredMixin, ActionItemCompleteMixin, View):
    http_method_names = ["post"]

    def get_action_item(self):
        pk = getattr(self, "kwargs", {}).get("pk")
        if pk is None:
            return None
        return ActionItem.objects.filter(pk=pk).first()

    def post(self, request, pk):
        action = get_object_or_404(ActionItem, pk=pk)
        if not can_complete_actionitem(request.user, action):
            raise PermissionDenied()
        form = ActionItemCompleteForm(request.POST)
        if not form.is_valid():
            for _, errs in form.errors.items():
                for err in errs:
                    messages.error(request, err)
            return redirect(
                reverse("action_items:actionitem_detail", args=[action.pk]) + "#complete"
            )
        try:
            transition_actionitem(action, STATUS_COMPLETED, by_user=request.user, reason="")
        except ValidationError as err:
            for msg in err.messages:
                messages.error(request, msg)
            return redirect(
                reverse("action_items:actionitem_detail", args=[action.pk]) + "#complete"
            )
        ActionItemUpdate.objects.create(
            action_item=action,
            author=request.user,
            status_snapshot=STATUS_COMPLETED,
            progress_snapshot=100,
            body=f"[Completion]\n{form.cleaned_data['completion_summary']}",
        )
        messages.success(request, "Action item marked complete.")
        return redirect(reverse("action_items:actionitem_detail", args=[action.pk]) + "#updates")


class ActionItemReopenView(LoginRequiredMixin, View):
    http_method_names = ["post"]

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not can_reopen_actionitem(request.user):
            raise PermissionDenied()
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, pk):
        action = get_object_or_404(ActionItem, pk=pk)
        form = ActionItemReopenForm(request.POST)
        if not form.is_valid():
            for _, errs in form.errors.items():
                for err in errs:
                    messages.error(request, err)
            return redirect(reverse("action_items:actionitem_detail", args=[action.pk]) + "#reopen")
        try:
            transition_actionitem(
                action,
                STATUS_REOPENED,
                by_user=request.user,
                reason=form.cleaned_data["reason"],
            )
        except ValidationError as err:
            for msg in err.messages:
                messages.error(request, msg)
            return redirect(reverse("action_items:actionitem_detail", args=[action.pk]) + "#reopen")
        if form.cleaned_data.get("new_priority"):
            action.priority = form.cleaned_data["new_priority"]
        if form.cleaned_data.get("new_due_date"):
            action.due_date = form.cleaned_data["new_due_date"]
        action.last_modified_by = request.user
        action.save(update_fields=["priority", "due_date", "last_modified_by", "updated_at"])
        messages.success(request, "Action item reopened.")
        return redirect(reverse("action_items:actionitem_detail", args=[action.pk]) + "#status")


class ActionItemAddUpdateView(LoginRequiredMixin, View):
    http_method_names = ["post"]

    def post(self, request, pk):
        action = get_object_or_404(ActionItem, pk=pk)
        if not can_edit_actionitem(request.user, action):
            raise PermissionDenied()
        form = ActionItemNewUpdateForm(request.POST, request.FILES, by_user=request.user)
        if not form.is_valid():
            for _, errs in form.errors.items():
                for err in errs:
                    messages.error(request, err)
            return redirect(
                reverse("action_items:actionitem_detail", args=[action.pk]) + "#updates"
            )
        upd = form.save(commit=False)
        upd.action_item = action
        upd.author = request.user
        upd.status_snapshot = action.status
        upd.progress_snapshot = action.progress_pct
        upd.save()
        log_audit_event(
            record_type=_record_type(upd),
            record=upd,
            action=AuditLog.ACTION_CREATE,
            user=request.user,
            reason="Update added",
        )
        messages.success(request, "Update added.")
        return redirect(reverse("action_items:actionitem_detail", args=[action.pk]) + "#updates")


class ActionItemAttachmentUploadView(LoginRequiredMixin, View):
    http_method_names = ["post"]

    def post(self, request, pk):
        action = get_object_or_404(ActionItem, pk=pk)
        if not can_edit_actionitem(request.user, action):
            raise PermissionDenied()
        form = ActionItemAttachmentForm(request.POST, request.FILES, by_user=request.user)
        if not form.is_valid():
            for msg in form.errors.get("__all__", []):
                messages.error(request, msg)
            return redirect(
                reverse("action_items:actionitem_detail", args=[action.pk]) + "#attachments"
            )
        att = form.save(commit=False)
        att.action_item = action
        att.uploaded_by = request.user
        att.save()
        log_audit_event(
            record_type=_record_type(att),
            record=att,
            action=AuditLog.ACTION_CREATE,
            user=request.user,
            reason="Attachment uploaded",
        )
        messages.success(request, "Attachment uploaded.")
        return redirect(
            reverse("action_items:actionitem_detail", args=[action.pk]) + "#attachments"
        )


class ActionItemAttachmentDeleteView(LoginRequiredMixin, DeleteView):
    model = ActionItemAttachment

    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        if not can_edit_actionitem(self.request.user, obj.action_item):
            raise PermissionDenied()
        return obj

    def delete(self, request, *args, **kwargs):
        obj = self.get_object()
        log_audit_event(
            record_type=_record_type(obj),
            record=obj,
            action=AuditLog.ACTION_DELETE,
            user=request.user,
            reason=f"Deleted attachment {obj.filename}",
        )
        messages.success(request, "Attachment deleted.")
        resp = super().delete(request, *args, **kwargs)
        return resp

    def get_success_url(self):
        action_id = self.object.action_item_id
        return reverse("action_items:actionitem_detail", args=[action_id]) + "#attachments"


class ActionItemCarryForwardView(LoginRequiredMixin, ActionItemQuerysetHelpers, View):
    http_method_names = ["post"]

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not can_create_actionitem(request.user):
            raise PermissionDenied()
        return super().dispatch(request, *args, **kwargs)

    def post(self, request):
        form = CarryForwardActionItemsForm(request.POST, by_user=request.user)
        if not form.is_valid():
            for _, errs in form.errors.items():
                for err in errs:
                    messages.error(request, err)
            return redirect(reverse("action_items:actionitem_list"))
        item_ids_raw = form.cleaned_data["item_ids"]
        item_ids = []
        for part in [p.strip() for p in item_ids_raw.split(",") if p.strip()]:
            with contextlib.suppress(ValueError):
                item_ids.append(uuid.UUID(part))
        include_completed = form.cleaned_data.get("include_completed", False)
        include_cancelled = form.cleaned_data.get("include_cancelled", False)
        target_meeting = form.cleaned_data.get("target_meeting", None)
        scope_parts = [str(include_completed), str(include_cancelled)]
        if target_meeting:
            scope_parts.insert(0, str(target_meeting.pk))
        target_scope_key = "|".join(scope_parts) or "default"
        reason = form.cleaned_data.get("reason", "")
        source_items = list(
            self.get_visible_for_user(ActionItem.objects.all(), request.user).filter(
                pk__in=item_ids
            )
        )
        if not source_items:
            messages.error(request, "Select at least one visible action item.")
            return redirect(reverse("action_items:actionitem_list"))
        try:
            created = carry_forward_action_items(
                source_items,
                target_meeting=target_meeting,
                target_scope_key=target_scope_key,
                include_completed=include_completed,
                include_cancelled=include_cancelled,
                by_user=request.user,
                reason=reason,
            )
        except ValidationError as err:
            for msg in err.messages:
                messages.error(request, msg)
            return redirect(reverse("action_items:actionitem_list"))
        messages.success(
            request,
            f"Carried forward {len(created)} action item(s) ({len(source_items)} selected).",
        )
        return redirect(reverse("action_items:actionitem_list"))


def dashboard_action_data(request_user) -> tuple[dict, list]:
    counts = dashboard_action_counts(request_user)
    next_overdue = list(overdue_action_items_queryset(request_user, limit=8))
    return counts, next_overdue
