from functools import wraps

from django.contrib.auth.mixins import AccessMixin, UserPassesTestMixin
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest

ROLE_SYSTEM_ADMIN = "System Administrator"
ROLE_MANAGEMENT_ADMIN = "Management Administrator"
ROLE_MEETING_CHAIR = "Meeting Chairperson"
ROLE_MINUTES_SECRETARY = "Minutes Secretary"
ROLE_DEPT_CONTRIBUTOR = "Department Contributor"
ROLE_VIEWER = "Viewer"

MANAGEMENT_ROLES = [ROLE_SYSTEM_ADMIN, ROLE_MANAGEMENT_ADMIN, ROLE_MEETING_CHAIR]
READ_ONLY_ROLES = [ROLE_VIEWER]


def _active_authenticated(user) -> bool:
    return bool(user and user.is_authenticated and getattr(user, "is_active", False))


def is_system_admin(user) -> bool:
    return _active_authenticated(user) and user.has_role(ROLE_SYSTEM_ADMIN)


def is_management_admin(user) -> bool:
    return _active_authenticated(user) and user.has_role(ROLE_MANAGEMENT_ADMIN)


def is_meeting_chair(user) -> bool:
    return _active_authenticated(user) and user.has_role(ROLE_MEETING_CHAIR)


def is_minutes_secretary(user) -> bool:
    return _active_authenticated(user) and user.has_role(ROLE_MINUTES_SECRETARY)


def is_department_contributor(user) -> bool:
    return _active_authenticated(user) and user.has_role(ROLE_DEPT_CONTRIBUTOR)


def is_viewer(user) -> bool:
    return _active_authenticated(user) and user.has_role(ROLE_VIEWER)


def can_manage_users(user) -> bool:
    return _active_authenticated(user) and (
        getattr(user, "is_superuser", False)
        or user.has_role(ROLE_SYSTEM_ADMIN, ROLE_MANAGEMENT_ADMIN)
    )


def can_manage_department_assignments(user) -> bool:
    return can_manage_users(user) or (
        _active_authenticated(user) and user.has_role(ROLE_MEETING_CHAIR)
    )


def user_in_department_contributors(user, department) -> bool:
    """Return True if `user` is an active contributor for `department`."""
    if not _active_authenticated(user):
        return False
    if getattr(user, "is_superuser", False):
        return True
    return (
        user.get_contributor_departments().filter(pk=getattr(department, "pk", department)).exists()
    )


class RoleRequiredMixin(UserPassesTestMixin):
    """View mixin that requires the user to have at least one of the given roles."""

    required_roles: list[str] | tuple[str, ...] = ()

    def get_required_roles(self):
        return tuple(self.required_roles)

    def test_func(self):
        user = self.request.user
        if not _active_authenticated(user):
            return False
        if getattr(user, "is_superuser", False):
            return True
        required = self.get_required_roles()
        if not required:
            return True
        return user.has_role(*required)


class ManagementRoleRequiredMixin(RoleRequiredMixin):
    required_roles = (ROLE_SYSTEM_ADMIN, ROLE_MANAGEMENT_ADMIN, ROLE_MEETING_CHAIR)


class UserManagementRequiredMixin(RoleRequiredMixin):
    required_roles = (ROLE_SYSTEM_ADMIN, ROLE_MANAGEMENT_ADMIN)


class DepartmentAssignmentManagementRequiredMixin(RoleRequiredMixin):
    required_roles = (
        ROLE_SYSTEM_ADMIN,
        ROLE_MANAGEMENT_ADMIN,
        ROLE_MEETING_CHAIR,
    )


class DepartmentContributorRequiredMixin(AccessMixin):
    """Restrict views to contributors of a specific department.

    Subclasses must override `get_department()` returning a Department or PK
    (or rely on a `department_pk` kwarg in the URL).
    """

    def get_department(self):
        dept_pk = self.kwargs.get("department_pk")  # type: ignore[attr-defined]
        if dept_pk is not None:
            return dept_pk
        raise AttributeError(
            "DepartmentContributorRequiredMixin requires department_pk or get_department()"
        )

    def dispatch(self, request, *args, **kwargs):
        user = request.user
        if not _active_authenticated(user):
            return self.handle_no_permission()
        if getattr(user, "is_superuser", False):
            return super().dispatch(request, *args, **kwargs)
        dept = self.get_department()
        if not user_in_department_contributors(user, dept):
            raise PermissionDenied()
        return super().dispatch(request, *args, **kwargs)


def group_required(*group_names: str):
    """Decorator for function-based views: require user has any of the named roles (groups)."""

    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request: HttpRequest, *args, **kwargs):
            user = request.user
            if not _active_authenticated(user):
                from django.contrib.auth.views import redirect_to_login

                return redirect_to_login(request.get_full_path())
            if getattr(user, "is_superuser", False):
                return view_func(request, *args, **kwargs)
            if group_names and not user.has_role(*group_names):
                raise PermissionDenied()
            return view_func(request, *args, **kwargs)

        return _wrapped_view

    return decorator


MEETING_AUTHOR_ROLES = (
    ROLE_SYSTEM_ADMIN,
    ROLE_MANAGEMENT_ADMIN,
    ROLE_MEETING_CHAIR,
    ROLE_MINUTES_SECRETARY,
)

CONFIDENTIAL_VIEWER_ROLES = (
    ROLE_SYSTEM_ADMIN,
    ROLE_MANAGEMENT_ADMIN,
    ROLE_MEETING_CHAIR,
    ROLE_MINUTES_SECRETARY,
)

REOPEN_AUTHORIZED_ROLES = (ROLE_SYSTEM_ADMIN, ROLE_MANAGEMENT_ADMIN)


def _get_pk(obj):
    return getattr(obj, "pk", obj) if obj is not None else None


def can_create_meeting(user) -> bool:
    return _active_authenticated(user) and (
        getattr(user, "is_superuser", False) or user.has_role(*MEETING_AUTHOR_ROLES)
    )


def can_edit_meeting(user, meeting) -> bool:
    if not _active_authenticated(user):
        return False
    if getattr(user, "is_superuser", False):
        return True
    if not getattr(meeting, "is_editable", True):
        return False
    if getattr(meeting, "is_locked", False):
        return user.has_role(ROLE_SYSTEM_ADMIN, ROLE_MANAGEMENT_ADMIN)
    if user.has_role(*MEETING_AUTHOR_ROLES):
        return True
    chair_pk = _get_pk(getattr(meeting, "chair", None))
    creator_pk = _get_pk(getattr(meeting, "created_by", None))
    user_pk = _get_pk(user)
    return (chair_pk is not None and chair_pk == user_pk) or (
        creator_pk is not None and creator_pk == user_pk
    )


def can_archive_meeting(user, meeting=None) -> bool:
    return _active_authenticated(user) and (
        getattr(user, "is_superuser", False)
        or user.has_role(ROLE_SYSTEM_ADMIN, ROLE_MANAGEMENT_ADMIN)
    )


def can_transition_meeting(user, meeting, target_status: str | None = None) -> bool:
    if not _active_authenticated(user):
        return False
    if getattr(user, "is_superuser", False):
        return True
    if not can_edit_meeting(user, meeting) and not user.has_role(*MEETING_AUTHOR_ROLES):
        return False
    from apps.meetings.models import (
        STATUS_APPROVED,
        STATUS_PUBLISHED,
        STATUS_RETURNED_FOR_CORRECTION,
    )

    if target_status in {STATUS_RETURNED_FOR_CORRECTION}:
        return user.has_role(*REOPEN_AUTHORIZED_ROLES)
    current = getattr(meeting, "status", None)
    if current in {STATUS_APPROVED, STATUS_PUBLISHED} and target_status in {
        STATUS_RETURNED_FOR_CORRECTION
    }:
        return user.has_role(*REOPEN_AUTHORIZED_ROLES)
    return True


def can_view_confidential_items(user, meeting=None, agenda_item=None) -> bool:
    if not _active_authenticated(user):
        return False
    if getattr(user, "is_superuser", False):
        return True
    if user.has_role(*CONFIDENTIAL_VIEWER_ROLES):
        return True
    if agenda_item is not None:
        owner_pk = _get_pk(getattr(agenda_item, "owner", None))
        user_pk = _get_pk(user)
        if owner_pk is not None and owner_pk == user_pk:
            return True
        dept = getattr(agenda_item, "department", None)
        if dept is not None:
            head_pk = _get_pk(getattr(dept, "head", None))
            if head_pk is not None and head_pk == user_pk:
                return True
    if meeting is not None:
        chair_pk = _get_pk(getattr(meeting, "chair", None))
        if chair_pk is not None and chair_pk == _get_pk(user):
            return True
    return False


class MeetingAuthorRequiredMixin(RoleRequiredMixin):
    required_roles = MEETING_AUTHOR_ROLES


class MeetingEditPermittedMixin(UserPassesTestMixin):
    def get_meeting(self):
        return getattr(self, "object", None) or self.get_object()

    def test_func(self):
        meeting = self.get_meeting()
        return can_edit_meeting(self.request.user, meeting)


class ReopenAuthorizedMixin(RoleRequiredMixin):
    required_roles = REOPEN_AUTHORIZED_ROLES


ACTION_AUTHOR_ROLES = (
    ROLE_SYSTEM_ADMIN,
    ROLE_MANAGEMENT_ADMIN,
    ROLE_MEETING_CHAIR,
    ROLE_MINUTES_SECRETARY,
    ROLE_DEPT_CONTRIBUTOR,
)

ACTION_VIEWER_ROLES = (*ACTION_AUTHOR_ROLES, ROLE_VIEWER)

ACTION_REOPEN_ROLES = (ROLE_SYSTEM_ADMIN, ROLE_MANAGEMENT_ADMIN)

ACTION_COMPLETE_ROLES = (
    ROLE_SYSTEM_ADMIN,
    ROLE_MANAGEMENT_ADMIN,
    ROLE_MEETING_CHAIR,
    ROLE_MINUTES_SECRETARY,
)


def _action_item_user_is_related(user, item) -> bool:
    """Return True if the user owns, created, is assignee, or chairs origin meeting."""
    if user is None or item is None:
        return False
    user_pk = _get_pk(user)
    if user_pk is None:
        return False
    for field in ("owner", "created_by"):
        related_pk = _get_pk(getattr(item, field, None))
        if related_pk is not None and related_pk == user_pk:
            return True
    assignees_qs = getattr(item, "assignees", None)
    if assignees_qs is not None and assignees_qs.filter(user_id=user_pk).exists():
        return True
    source_meeting = getattr(item, "source_meeting", None)
    if source_meeting is not None:
        chair_pk = _get_pk(getattr(source_meeting, "chair", None))
        if chair_pk is not None and chair_pk == user_pk:
            return True
    return False


def can_create_actionitem(user) -> bool:
    return _active_authenticated(user) and (
        getattr(user, "is_superuser", False) or user.has_role(*ACTION_AUTHOR_ROLES)
    )


def can_view_actionitem(user, item) -> bool:
    if not _active_authenticated(user):
        return False
    if getattr(user, "is_superuser", False):
        return True
    if user.has_role(*ACTION_VIEWER_ROLES):
        return True
    return _action_item_user_is_related(user, item)


def can_edit_actionitem(user, item) -> bool:
    if not _active_authenticated(user):
        return False
    if getattr(user, "is_superuser", False):
        return True
    if not getattr(item, "is_editable", True):
        return False
    if user.has_role(ROLE_SYSTEM_ADMIN, ROLE_MANAGEMENT_ADMIN):
        return True
    if _action_item_user_is_related(user, item):
        return True
    if user.has_role(*ACTION_AUTHOR_ROLES):
        dept = getattr(item, "department", None)
        if dept is None:
            return False
        return user_in_department_contributors(user, dept)
    return False


def can_complete_actionitem(user, item) -> bool:
    if not _active_authenticated(user):
        return False
    if getattr(user, "is_superuser", False):
        return True
    if user.has_role(*ACTION_COMPLETE_ROLES):
        return True
    user_pk = _get_pk(user)
    owner_pk = _get_pk(getattr(item, "owner", None))
    if owner_pk is not None and owner_pk == user_pk:
        return True
    primary = getattr(item, "primary_assignee", None)
    primary_pk = _get_pk(primary)
    return primary_pk is not None and primary_pk == user_pk


def can_reopen_actionitem(user, item=None) -> bool:
    return _active_authenticated(user) and (
        getattr(user, "is_superuser", False) or user.has_role(*ACTION_REOPEN_ROLES)
    )


class ActionItemAuthorRequiredMixin(UserPassesTestMixin):
    def get_action_item(self):
        return getattr(self, "object", None) or self.get_object()

    def test_func(self):
        user = self.request.user
        if not _active_authenticated(user):
            return False
        if getattr(user, "is_superuser", False):
            return True
        item = self.get_action_item()
        if can_edit_actionitem(user, item):
            return True
        return user.has_role(*ACTION_AUTHOR_ROLES) and _action_item_user_is_related(user, item)


class ActionItemCompleteMixin(UserPassesTestMixin):
    def get_action_item(self):
        return getattr(self, "object", None) or self.get_object()

    def test_func(self):
        user = self.request.user
        if not _active_authenticated(user):
            return False
        if getattr(user, "is_superuser", False):
            return True
        item = self.get_action_item()
        return can_complete_actionitem(user, item)


class ArchiveAuthorizedMixin(RoleRequiredMixin):
    required_roles = (ROLE_SYSTEM_ADMIN, ROLE_MANAGEMENT_ADMIN)


SALES_AUTHOR_ROLES = (
    ROLE_SYSTEM_ADMIN,
    ROLE_MANAGEMENT_ADMIN,
    ROLE_MEETING_CHAIR,
    ROLE_MINUTES_SECRETARY,
    ROLE_DEPT_CONTRIBUTOR,
)
SALES_VIEWER_ROLES = (
    *SALES_AUTHOR_ROLES,
    ROLE_VIEWER,
)
SALES_EXPORT_ROLES = (ROLE_SYSTEM_ADMIN, ROLE_MANAGEMENT_ADMIN, ROLE_MEETING_CHAIR)
SALES_LOCK_ROLES = (ROLE_SYSTEM_ADMIN, ROLE_MANAGEMENT_ADMIN, ROLE_MEETING_CHAIR)


def can_view_sales_period(user, period=None):
    if not _active_authenticated(user):
        return False
    if getattr(user, "is_superuser", False):
        return True
    return user.has_role(*SALES_VIEWER_ROLES)


def can_edit_sales_period(user, period=None):
    if not _active_authenticated(user):
        return False
    if getattr(user, "is_superuser", False):
        return True
    if period is not None and getattr(period, "is_locked", False):
        return False
    return user.has_role(*SALES_AUTHOR_ROLES)


def can_export_sales(user):
    if not _active_authenticated(user):
        return False
    if getattr(user, "is_superuser", False):
        return True
    return user.has_role(*SALES_EXPORT_ROLES)


def can_lock_sales_snapshot(user, snapshot=None):
    if not _active_authenticated(user):
        return False
    if getattr(user, "is_superuser", False):
        return True
    if snapshot is not None and getattr(snapshot, "is_locked", False):
        return False
    return user.has_role(*SALES_LOCK_ROLES)


def _sales_user_is_related(user, group):
    """True if user is a manager, team leader, or active group member."""
    if group is None or user is None or getattr(user, "pk", None) is None:
        return False
    if getattr(group, "manager_id", None) == user.pk:
        return True
    if getattr(getattr(group, "team", None), "leader_id", None) == user.pk:
        return True
    from apps.sales_updates.models import SalesGroupMembership

    return SalesGroupMembership.objects.filter(group=group, user=user, is_active=True).exists()


class SalesEditRequiredMixin(UserPassesTestMixin):
    def test_func(self):
        user = self.request.user
        if not _active_authenticated(user):
            return False
        if getattr(user, "is_superuser", False):
            return True
        return user.has_role(*SALES_AUTHOR_ROLES)


MINUTES_AUTHOR_ROLES = (
    ROLE_SYSTEM_ADMIN,
    ROLE_MANAGEMENT_ADMIN,
    ROLE_MEETING_CHAIR,
    ROLE_MINUTES_SECRETARY,
    ROLE_DEPT_CONTRIBUTOR,
)
MINUTES_VIEWER_ROLES = (
    *MINUTES_AUTHOR_ROLES,
    ROLE_VIEWER,
)
MINUTES_REVIEW_ROLES = (
    ROLE_SYSTEM_ADMIN,
    ROLE_MANAGEMENT_ADMIN,
    ROLE_MEETING_CHAIR,
)
MINUTES_APPROVER_ROLES = (
    ROLE_SYSTEM_ADMIN,
    ROLE_MANAGEMENT_ADMIN,
    ROLE_MEETING_CHAIR,
)
MINUTES_PUBLISHER_ROLES = (
    ROLE_SYSTEM_ADMIN,
    ROLE_MANAGEMENT_ADMIN,
    ROLE_MEETING_CHAIR,
)
MINUTES_SNAPSHOT_ROLES = (
    ROLE_SYSTEM_ADMIN,
    ROLE_MANAGEMENT_ADMIN,
    ROLE_MEETING_CHAIR,
    ROLE_MINUTES_SECRETARY,
)


def can_submit_minutes(user, meeting=None):
    if not _active_authenticated(user):
        return False
    if getattr(user, "is_superuser", False):
        return True
    if meeting is not None and not getattr(meeting, "is_editable", True):
        return False
    return user.has_role(*MINUTES_AUTHOR_ROLES)


def can_return_minutes(user, meeting=None):
    if not _active_authenticated(user):
        return False
    if getattr(user, "is_superuser", False):
        return True
    return user.has_role(*MINUTES_REVIEW_ROLES)


def can_resubmit_minutes(user, meeting=None):
    if not _active_authenticated(user):
        return False
    if getattr(user, "is_superuser", False):
        return True
    if meeting is not None and not getattr(meeting, "is_editable", True):
        return False
    return user.has_role(*MINUTES_AUTHOR_ROLES)


def can_approve_meeting(user, meeting=None):
    if not _active_authenticated(user):
        return False
    if getattr(user, "is_superuser", False):
        return True
    return user.has_role(*MINUTES_APPROVER_ROLES)


def can_publish_meeting(user, meeting=None):
    if not _active_authenticated(user):
        return False
    if getattr(user, "is_superuser", False):
        return True
    return user.has_role(*MINUTES_PUBLISHER_ROLES)


def can_close_meeting(user, meeting=None):
    if not _active_authenticated(user):
        return False
    if getattr(user, "is_superuser", False):
        return True
    return user.has_role(*MINUTES_PUBLISHER_ROLES)


def can_reopen_meeting(user, meeting=None):
    if not _active_authenticated(user):
        return False
    if getattr(user, "is_superuser", False):
        return True
    return user.has_role(*REOPEN_AUTHORIZED_ROLES)


def can_create_snapshot(user, meeting=None):
    if not _active_authenticated(user):
        return False
    if getattr(user, "is_superuser", False):
        return True
    return user.has_role(*MINUTES_SNAPSHOT_ROLES)


class MinutesEditRequiredMixin(UserPassesTestMixin):
    def get_meeting(self):
        return getattr(self, "object", None) or self.get_object()

    def test_func(self):
        meeting = self.get_meeting()
        return can_submit_minutes(self.request.user, meeting)


class MinutesReviewRequiredMixin(UserPassesTestMixin):
    def get_meeting(self):
        return getattr(self, "object", None) or self.get_object()

    def test_func(self):
        meeting = self.get_meeting()
        return can_return_minutes(self.request.user, meeting)


class MinutesApproverRequiredMixin(UserPassesTestMixin):
    def get_meeting(self):
        return getattr(self, "object", None) or self.get_object()

    def test_func(self):
        meeting = self.get_meeting()
        return can_approve_meeting(self.request.user, meeting)


REPORT_EXPORT_ROLES = (
    ROLE_SYSTEM_ADMIN,
    ROLE_MANAGEMENT_ADMIN,
    ROLE_MEETING_CHAIR,
    ROLE_MINUTES_SECRETARY,
)


def can_export_reports(user):
    if not _active_authenticated(user):
        return False
    if getattr(user, "is_superuser", False):
        return True
    return user.has_role(*REPORT_EXPORT_ROLES)


class ReportExportRequiredMixin(UserPassesTestMixin):
    def test_func(self):
        return can_export_reports(self.request.user)


ORG_MANAGEMENT_ROLES = (
    ROLE_SYSTEM_ADMIN,
    ROLE_MANAGEMENT_ADMIN,
    ROLE_MEETING_CHAIR,
    ROLE_MINUTES_SECRETARY,
)


def can_manage_departments(user) -> bool:
    return _active_authenticated(user) and (
        getattr(user, "is_superuser", False) or user.has_role(*ORG_MANAGEMENT_ROLES)
    )


def can_manage_positions(user) -> bool:
    return _active_authenticated(user) and (
        getattr(user, "is_superuser", False) or user.has_role(*ORG_MANAGEMENT_ROLES)
    )


def can_view_org(user) -> bool:
    return _active_authenticated(user)


class OrgManagementRequiredMixin(RoleRequiredMixin):
    required_roles = ORG_MANAGEMENT_ROLES
