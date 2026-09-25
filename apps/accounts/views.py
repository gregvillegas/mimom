from django import forms
from django.contrib import messages
from django.contrib.auth import get_user_model, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db import models, transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from apps.audit.models import AuditLog
from apps.audit.services import log_audit_event
from apps.core.permissions import (
    DepartmentAssignmentManagementRequiredMixin,
    OrgManagementRequiredMixin,
    UserManagementRequiredMixin,
    can_view_org,
)

from .forms import (
    PasswordChangeForm,
    ProfileUpdateForm,
    UserCreateForm,
    UserUpdateForm,
    build_membership_formset,
)
from .models import Department, ManagementTeam, Position

User = get_user_model()


def _client_ip(request) -> str | None:
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


class UserListView(LoginRequiredMixin, UserManagementRequiredMixin, ListView):
    model = User
    template_name = "accounts/user_list.html"
    context_object_name = "users"
    paginate_by = 25

    def get_queryset(self):
        qs = (
            User.objects.all()
            .prefetch_related("groups", "department_memberships__department")
            .order_by("username")
        )
        query = self.request.GET.get("q", "").strip()
        if query:
            qs = qs.filter(
                models.Q(username__icontains=query)
                | models.Q(email__icontains=query)
                | models.Q(first_name__icontains=query)
                | models.Q(last_name__icontains=query)
                | models.Q(display_name__icontains=query)
            )
        is_active_filter = self.request.GET.get("status")
        if is_active_filter == "active":
            qs = qs.filter(is_active=True)
        elif is_active_filter == "inactive":
            qs = qs.filter(is_active=False)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"] = "Users"
        ctx["query"] = self.request.GET.get("q", "")
        ctx["status"] = self.request.GET.get("status", "")
        ctx["breadcrumbs"] = [("Home", reverse("home")), ("Users", None)]
        return ctx


class UserCreateView(LoginRequiredMixin, UserManagementRequiredMixin, CreateView):
    model = User
    form_class = UserCreateForm
    template_name = "accounts/user_form.html"
    success_url = reverse_lazy("accounts:user_list")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"] = "Create User"
        ctx["form_mode"] = "create"
        ctx["breadcrumbs"] = [
            ("Home", reverse("home")),
            ("Users", reverse("accounts:user_list")),
            ("Create", None),
        ]
        return ctx

    def form_valid(self, form):
        with transaction.atomic():
            response = super().form_valid(form)
            log_audit_event(
                record_type="accounts.User",
                record=self.object,
                action=AuditLog.ACTION_CREATE,
                user=self.request.user,
                target_user=self.object,
                ip_address=_client_ip(self.request),
                new_values={
                    "username": self.object.username,
                    "email": self.object.email,
                    "display_name": self.object.display_name,
                    "groups": list(self.object.groups.values_list("name", flat=True)),
                },
                reason="Created via user management UI",
            )
        messages.success(
            self.request, f"User {self.object.get_display_name()} created successfully."
        )
        return response


class UserUpdateView(LoginRequiredMixin, UserManagementRequiredMixin, UpdateView):
    model = User
    form_class = UserUpdateForm
    template_name = "accounts/user_form.html"
    success_url = reverse_lazy("accounts:user_list")
    pk_url_kwarg = "pk"
    context_object_name = "target_user"

    def get_object(self, queryset=None):
        obj = get_object_or_404(User, pk=self.kwargs["pk"])
        obj._previous_values = {  # type: ignore[attr-defined]
            "username": obj.username,
            "email": obj.email,
            "display_name": obj.display_name,
            "is_active": obj.is_active,
            "is_staff": obj.is_staff,
            "groups": list(obj.groups.values_list("name", flat=True)),
            "first_name": obj.first_name,
            "last_name": obj.last_name,
            "theme": obj.theme,
            "phone": obj.phone,
            "signature_text": obj.signature_text,
            "bio": obj.bio,
        }
        return obj

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"] = f"Edit User: {self.object.get_display_name()}"
        ctx["form_mode"] = "edit"
        ctx["breadcrumbs"] = [
            ("Home", reverse("home")),
            ("Users", reverse("accounts:user_list")),
            (f"Edit {self.object.username}", None),
        ]
        return ctx

    def form_valid(self, form):
        previous = getattr(self.object, "_previous_values", {})
        with transaction.atomic():
            response = super().form_valid(form)
            new_values = {
                "username": self.object.username,
                "email": self.object.email,
                "display_name": self.object.display_name,
                "is_active": self.object.is_active,
                "is_staff": self.object.is_staff,
                "groups": list(self.object.groups.values_list("name", flat=True)),
                "first_name": self.object.first_name,
                "last_name": self.object.last_name,
                "theme": self.object.theme,
                "phone": self.object.phone,
                "signature_text": self.object.signature_text,
                "bio": self.object.bio,
            }
            log_audit_event(
                record_type="accounts.User",
                record=self.object,
                action=AuditLog.ACTION_UPDATE,
                user=self.request.user,
                target_user=self.object,
                ip_address=_client_ip(self.request),
                previous_values=previous,
                new_values=new_values,
                reason="Updated via user management UI",
            )
        messages.success(
            self.request, f"User {self.object.get_display_name()} updated successfully."
        )
        return response


class ProfileView(LoginRequiredMixin, DetailView):
    model = User
    template_name = "accounts/profile.html"
    context_object_name = "profile_user"

    def get_object(self, queryset=None):
        pk = self.kwargs.get("pk")
        if pk:
            return get_object_or_404(User, pk=pk)
        return self.request.user

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        target = self.object
        is_self = target == self.request.user
        ctx["page_title"] = "Profile" if is_self else f"Profile: {target.get_display_name()}"
        ctx["is_self"] = is_self
        ctx["breadcrumbs"] = [("Home", reverse("home")), (ctx["page_title"], None)]
        ctx["memberships"] = target.department_memberships.select_related(
            "department", "position"
        ).order_by("-is_primary", "department__name")
        ctx["team_memberships"] = target.team_memberships.select_related("team").order_by(
            "team__name"
        )
        ctx["role_groups"] = list(target.groups.order_by("name"))
        return ctx


class ProfileEditView(LoginRequiredMixin, UpdateView):
    model = User
    form_class = ProfileUpdateForm
    template_name = "accounts/profile_edit.html"

    def get_object(self, queryset=None):
        return self.request.user

    def get_success_url(self):
        return reverse("accounts:profile_me")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"] = "Edit Profile"
        ctx["breadcrumbs"] = [
            ("Home", reverse("home")),
            ("Profile", reverse("accounts:profile_me")),
            ("Edit", None),
        ]
        return ctx

    def form_valid(self, form):
        previous = {
            "display_name": self.request.user.display_name,
            "first_name": self.request.user.first_name,
            "last_name": self.request.user.last_name,
            "phone": self.request.user.phone,
            "signature_text": self.request.user.signature_text,
            "theme": self.request.user.theme,
            "bio": self.request.user.bio,
            "initials": self.request.user.initials,
        }
        with transaction.atomic():
            response = super().form_valid(form)
            log_audit_event(
                record_type="accounts.User",
                record=self.object,
                action=AuditLog.ACTION_UPDATE,
                user=self.request.user,
                target_user=self.object,
                ip_address=_client_ip(self.request),
                previous_values=previous,
                new_values={
                    "display_name": self.object.display_name,
                    "first_name": self.object.first_name,
                    "last_name": self.object.last_name,
                    "phone": self.object.phone,
                    "signature_text": self.object.signature_text,
                    "theme": self.object.theme,
                    "bio": self.object.bio,
                    "initials": self.object.initials,
                },
                reason="Profile updated by user",
            )
        messages.success(self.request, "Profile updated.")
        return response


class DepartmentAssignmentsView(
    LoginRequiredMixin, DepartmentAssignmentManagementRequiredMixin, View
):
    template_name = "accounts/department_assignments.html"

    def get(self, request, user_pk):
        target = get_object_or_404(User, pk=user_pk)
        formset = build_membership_formset(target)
        return self._render(request, target, formset)

    def post(self, request, user_pk):
        target = get_object_or_404(User, pk=user_pk)
        formset = build_membership_formset(target, request.POST)
        if not formset.is_valid():
            messages.error(request, "Please fix the errors below.")
            return self._render(request, target, formset, status=400)
        with transaction.atomic():
            previous = [
                {
                    "department_id": str(m.department_id),
                    "position_id": str(m.position_id) if m.position_id else None,
                    "is_primary": m.is_primary,
                    "is_contributor": m.is_contributor,
                    "is_active": m.is_active,
                }
                for m in list(target.department_memberships.all())
            ]
            formset.save()
            new_values = [
                {
                    "department_id": str(m.department_id),
                    "position_id": str(m.position_id) if m.position_id else None,
                    "is_primary": m.is_primary,
                    "is_contributor": m.is_contributor,
                    "is_active": m.is_active,
                }
                for m in list(target.department_memberships.all())
            ]
            log_audit_event(
                record_type="accounts.DepartmentMembership",
                record=target,
                action=AuditLog.ACTION_ASSIGN,
                user=request.user,
                target_user=target,
                ip_address=_client_ip(request),
                previous_values={"memberships": previous},
                new_values={"memberships": new_values},
                reason="Department assignments updated",
            )
        messages.success(request, f"Department assignments for {target.get_display_name()} saved.")
        return redirect(reverse("accounts:department_assignments", args=[str(target.pk)]))

    def _render(self, request, target, formset, status=200):
        ctx = {
            "page_title": f"Department Assignments: {target.get_display_name()}",
            "target_user": target,
            "formset": formset,
            "breadcrumbs": [
                ("Home", reverse("home")),
                ("Users", reverse("accounts:user_list")),
                (target.get_display_name(), reverse("accounts:user_edit", args=[str(target.pk)])),
                ("Department Assignments", None),
            ],
        }
        return render(request, self.template_name, ctx, status=status)


@login_required
def password_change_view(request):
    if request.method == "POST":
        form = PasswordChangeForm(user=request.user, data=request.POST)
        if form.is_valid():
            previous = {"user": request.user.username}
            user = form.save()
            update_session_auth_hash(request, user)
            log_audit_event(
                record_type="accounts.User",
                record=request.user,
                action=AuditLog.ACTION_UPDATE,
                user=request.user,
                target_user=request.user,
                ip_address=_client_ip(request),
                previous_values=previous,
                new_values={"password_changed": True},
                reason="Password changed",
            )
            messages.success(request, "Your password was changed successfully.")
            return redirect("accounts:password_change_done")
    else:
        form = PasswordChangeForm(user=request.user)

    breadcrumbs = [
        ("Home", reverse("home")),
        ("Profile", reverse("accounts:profile_me")),
        ("Change Password", None),
    ]
    return render(
        request,
        "registration/password_change_form.html",
        {"form": form, "breadcrumbs": breadcrumbs, "page_title": "Change Password"},
    )


@login_required
def password_change_done_view(request):
    breadcrumbs = [
        ("Home", reverse("home")),
        ("Profile", reverse("accounts:profile_me")),
        ("Password Changed", None),
    ]
    return render(
        request,
        "registration/password_change_done.html",
        {"breadcrumbs": breadcrumbs, "page_title": "Password Changed"},
    )


class DepartmentListView(LoginRequiredMixin, ListView):
    model = Department
    template_name = "accounts/org_department_list.html"
    context_object_name = "departments"
    paginate_by = 25

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and not can_view_org(request.user):
            raise PermissionDenied()
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        qs = Department.objects.select_related("head", "parent").order_by("name")
        query = self.request.GET.get("q", "").strip()
        if query:
            qs = qs.filter(
                models.Q(name__icontains=query) | models.Q(code__icontains=query)
            )
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"] = "Departments"
        ctx["query"] = self.request.GET.get("q", "")
        ctx["breadcrumbs"] = [
            ("Home", reverse("home")),
            ("Organization", None),
            ("Departments", None),
        ]
        return ctx


class DepartmentDetailView(LoginRequiredMixin, DetailView):
    model = Department
    template_name = "accounts/org_department_detail.html"
    context_object_name = "department"

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and not can_view_org(request.user):
            raise PermissionDenied()
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return Department.objects.prefetch_related(
            "memberships__user", "memberships__position"
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        obj = self.object
        ctx["page_title"] = f"Dept {obj.name}"
        ctx["memberships"] = obj.memberships.select_related("user", "position").order_by(
            "-is_primary", "user__display_name", "user__username"
        )
        ctx["breadcrumbs"] = [
            ("Home", reverse("home")),
            ("Organization", None),
            ("Departments", reverse("accounts:department_list")),
            (obj.name, None),
        ]
        return ctx


class _DepartmentForm(forms.ModelForm):
    class Meta:
        model = Department
        fields = ["name", "code", "description", "head", "parent", "is_active"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for fname, f in self.fields.items():
            if isinstance(f.widget, forms.CheckboxInput):
                continue
            f.widget.attrs.setdefault("class", "form-control")
        self.fields["head"].queryset = User.objects.filter(is_active=True).order_by(
            "display_name", "username"
        )
        self.fields["parent"].queryset = Department.objects.filter(is_active=True).order_by(
            "name"
        )


class DepartmentCreateView(LoginRequiredMixin, OrgManagementRequiredMixin, CreateView):
    model = Department
    form_class = _DepartmentForm
    template_name = "accounts/user_form.html"
    success_url = reverse_lazy("accounts:department_list")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"] = "Create Department"
        ctx["form_mode"] = "create"
        ctx["breadcrumbs"] = [
            ("Home", reverse("home")),
            ("Organization", None),
            ("Departments", reverse("accounts:department_list")),
            ("Create", None),
        ]
        return ctx

    def form_valid(self, form):
        with transaction.atomic():
            response = super().form_valid(form)
            log_audit_event(
                record_type="accounts.Department",
                record=self.object,
                action=AuditLog.ACTION_CREATE,
                user=self.request.user,
                ip_address=_client_ip(self.request),
                new_values={
                    "name": self.object.name,
                    "code": self.object.code,
                    "head_id": str(self.object.head_id) if self.object.head_id else None,
                    "parent_id": str(self.object.parent_id) if self.object.parent_id else None,
                    "is_active": self.object.is_active,
                },
                reason="Created via organization management UI",
            )
        messages.success(self.request, f"Department {self.object.name} created successfully.")
        return response


class DepartmentUpdateView(LoginRequiredMixin, OrgManagementRequiredMixin, UpdateView):
    model = Department
    form_class = _DepartmentForm
    template_name = "accounts/user_form.html"
    success_url = reverse_lazy("accounts:department_list")
    pk_url_kwarg = "pk"

    def get_object(self, queryset=None):
        obj = get_object_or_404(Department, pk=self.kwargs["pk"])
        obj._previous_values = {
            "name": obj.name,
            "code": obj.code,
            "description": obj.description,
            "head_id": str(obj.head_id) if obj.head_id else None,
            "parent_id": str(obj.parent_id) if obj.parent_id else None,
            "is_active": obj.is_active,
        }
        return obj

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"] = f"Edit Department: {self.object.name}"
        ctx["form_mode"] = "edit"
        ctx["breadcrumbs"] = [
            ("Home", reverse("home")),
            ("Organization", None),
            ("Departments", reverse("accounts:department_list")),
            (f"Edit {self.object.name}", None),
        ]
        return ctx

    def form_valid(self, form):
        previous = getattr(self.object, "_previous_values", {})
        with transaction.atomic():
            response = super().form_valid(form)
            log_audit_event(
                record_type="accounts.Department",
                record=self.object,
                action=AuditLog.ACTION_UPDATE,
                user=self.request.user,
                ip_address=_client_ip(self.request),
                previous_values=previous,
                new_values={
                    "name": self.object.name,
                    "code": self.object.code,
                    "description": self.object.description,
                    "head_id": str(self.object.head_id) if self.object.head_id else None,
                    "parent_id": str(self.object.parent_id) if self.object.parent_id else None,
                    "is_active": self.object.is_active,
                },
                reason="Updated via organization management UI",
            )
        messages.success(self.request, f"Department {self.object.name} updated successfully.")
        return response


class PositionListView(LoginRequiredMixin, ListView):
    model = Position
    template_name = "accounts/org_position_list.html"
    context_object_name = "positions"
    paginate_by = 25

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and not can_view_org(request.user):
            raise PermissionDenied()
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        qs = Position.objects.order_by("level", "name")
        query = self.request.GET.get("q", "").strip()
        if query:
            qs = qs.filter(
                models.Q(name__icontains=query) | models.Q(code__icontains=query)
            )
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"] = "Positions"
        ctx["query"] = self.request.GET.get("q", "")
        ctx["breadcrumbs"] = [
            ("Home", reverse("home")),
            ("Organization", None),
            ("Positions", None),
        ]
        return ctx


class PositionDetailView(LoginRequiredMixin, DetailView):
    model = Position
    template_name = "accounts/org_position_detail.html"
    context_object_name = "position"

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and not can_view_org(request.user):
            raise PermissionDenied()
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        obj = self.object
        ctx["page_title"] = f"Position {obj.name}"
        ctx["incumbents"] = obj.department_memberships.select_related(
            "user", "department"
        ).filter(is_active=True).order_by(
            "department__name", "user__display_name", "user__username"
        )
        ctx["breadcrumbs"] = [
            ("Home", reverse("home")),
            ("Organization", None),
            ("Positions", reverse("accounts:position_list")),
            (obj.name, None),
        ]
        return ctx


class _PositionForm(forms.ModelForm):
    class Meta:
        model = Position
        fields = ["name", "code", "description", "level", "is_active"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for fname, f in self.fields.items():
            if isinstance(f.widget, forms.CheckboxInput):
                continue
            f.widget.attrs.setdefault("class", "form-control")


class PositionCreateView(LoginRequiredMixin, OrgManagementRequiredMixin, CreateView):
    model = Position
    form_class = _PositionForm
    template_name = "accounts/user_form.html"
    success_url = reverse_lazy("accounts:position_list")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"] = "Create Position"
        ctx["form_mode"] = "create"
        ctx["breadcrumbs"] = [
            ("Home", reverse("home")),
            ("Organization", None),
            ("Positions", reverse("accounts:position_list")),
            ("Create", None),
        ]
        return ctx

    def form_valid(self, form):
        with transaction.atomic():
            response = super().form_valid(form)
            log_audit_event(
                record_type="accounts.Position",
                record=self.object,
                action=AuditLog.ACTION_CREATE,
                user=self.request.user,
                ip_address=_client_ip(self.request),
                new_values={
                    "name": self.object.name,
                    "code": self.object.code,
                    "level": self.object.level,
                    "is_active": self.object.is_active,
                },
                reason="Created via organization management UI",
            )
        messages.success(self.request, f"Position {self.object.name} created successfully.")
        return response


class PositionUpdateView(LoginRequiredMixin, OrgManagementRequiredMixin, UpdateView):
    model = Position
    form_class = _PositionForm
    template_name = "accounts/user_form.html"
    success_url = reverse_lazy("accounts:position_list")
    pk_url_kwarg = "pk"

    def get_object(self, queryset=None):
        obj = get_object_or_404(Position, pk=self.kwargs["pk"])
        obj._previous_values = {
            "name": obj.name,
            "code": obj.code,
            "description": obj.description,
            "level": obj.level,
            "is_active": obj.is_active,
        }
        return obj

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"] = f"Edit Position: {self.object.name}"
        ctx["form_mode"] = "edit"
        ctx["breadcrumbs"] = [
            ("Home", reverse("home")),
            ("Organization", None),
            ("Positions", reverse("accounts:position_list")),
            (f"Edit {self.object.name}", None),
        ]
        return ctx

    def form_valid(self, form):
        previous = getattr(self.object, "_previous_values", {})
        with transaction.atomic():
            response = super().form_valid(form)
            log_audit_event(
                record_type="accounts.Position",
                record=self.object,
                action=AuditLog.ACTION_UPDATE,
                user=self.request.user,
                ip_address=_client_ip(self.request),
                previous_values=previous,
                new_values={
                    "name": self.object.name,
                    "code": self.object.code,
                    "description": self.object.description,
                    "level": self.object.level,
                    "is_active": self.object.is_active,
                },
                reason="Updated via organization management UI",
            )
        messages.success(self.request, f"Position {self.object.name} updated successfully.")
        return response


class OrgTeamsListView(LoginRequiredMixin, ListView):
    template_name = "accounts/org_team_list.html"
    context_object_name = "management_teams"
    paginate_by = None

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and not can_view_org(request.user):
            raise PermissionDenied()
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return ManagementTeam.objects.prefetch_related(
            "memberships__user"
        ).order_by("name")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        from apps.sales_updates.models import SalesTeam

        ctx["page_title"] = "Teams"
        ctx["breadcrumbs"] = [
            ("Home", reverse("home")),
            ("Organization", None),
            ("Teams", None),
        ]
        ctx["sales_teams"] = SalesTeam.objects.prefetch_related(
            "groups__memberships__user"
        ).filter(is_active=True).order_by("name")
        ctx["management_teams_all"] = ManagementTeam.objects.prefetch_related(
            "memberships__user"
        ).filter(is_active=True).order_by("name")
        return ctx
