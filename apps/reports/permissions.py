from apps.core.permissions import REPORT_EXPORT_ROLES as _CORE_REPORT_EXPORT_ROLES
from apps.core.permissions import (
    ROLE_DEPT_CONTRIBUTOR,
    ROLE_MANAGEMENT_ADMIN,
    ROLE_MEETING_CHAIR,
    ROLE_MINUTES_SECRETARY,
    ROLE_SYSTEM_ADMIN,
    ROLE_VIEWER,
)
from apps.core.permissions import can_export_reports as _core_can_export_reports

REPORT_VIEW_ROLES = (
    ROLE_SYSTEM_ADMIN,
    ROLE_MANAGEMENT_ADMIN,
    ROLE_MEETING_CHAIR,
    ROLE_MINUTES_SECRETARY,
    ROLE_DEPT_CONTRIBUTOR,
    ROLE_VIEWER,
)

REPORT_EXPORT_ROLES = _CORE_REPORT_EXPORT_ROLES

can_export_reports = _core_can_export_reports


def _active_authenticated(user) -> bool:
    return bool(user and user.is_authenticated and getattr(user, "is_active", False))


REPORT_SLUG_AUTHORIZED_AUDIT = "authorized-audit-report"

AUDIT_REPORT_VIEW_ROLES = (
    ROLE_SYSTEM_ADMIN,
    ROLE_MANAGEMENT_ADMIN,
    ROLE_MEETING_CHAIR,
    ROLE_MINUTES_SECRETARY,
    ROLE_DEPT_CONTRIBUTOR,
)


def can_view_report(user, report_slug: str) -> bool:
    if not _active_authenticated(user):
        return False
    if getattr(user, "is_superuser", False):
        return True
    if report_slug == REPORT_SLUG_AUTHORIZED_AUDIT:
        return user.has_role(*AUDIT_REPORT_VIEW_ROLES)
    return user.has_role(*REPORT_VIEW_ROLES)


def can_export_report(user, report_slug: str) -> bool:
    return can_export_reports(user)
