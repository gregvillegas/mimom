from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.db import models
from django.db.models.signals import m2m_changed, post_delete, post_save

from apps.audit.models import AuditLog
from apps.audit.services import log_audit_event

from .models import DepartmentMembership, ManagementTeamMembership

User = get_user_model()


def _safe_json_value(value):
    if value is None:
        return None
    if isinstance(value, models.Model):
        pk = getattr(value, "pk", None)
        return str(pk) if pk is not None else None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, (list, tuple)):
        return [_safe_json_value(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _safe_json_value(v) for k, v in value.items()}
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _snapshot_fields(instance, fields):
    data = {}
    for name in fields:
        value = getattr(instance, name, None)
        data[name] = _safe_json_value(value)
    return data


def _record_type(instance):
    meta = instance._meta
    return f"{meta.app_label}.{meta.object_name}"


def on_user_saved(sender, instance, created, **kwargs):
    if created:
        log_audit_event(
            record_type=_record_type(instance),
            record=instance,
            action=AuditLog.ACTION_CREATE,
            target_user=instance,
            new_values=_snapshot_fields(
                instance,
                [
                    "username",
                    "email",
                    "first_name",
                    "last_name",
                    "display_name",
                    "is_active",
                    "is_staff",
                ],
            ),
            reason="User created",
        )
    else:
        previous = kwargs.get("update_fields")
        if previous:
            # When only update_fields is provided, snapshot only the listed fields
            field_set = list(previous)
        else:
            field_set = [
                "username",
                "email",
                "first_name",
                "last_name",
                "display_name",
                "is_active",
                "is_staff",
                "phone",
                "theme",
                "bio",
            ]
        log_audit_event(
            record_type=_record_type(instance),
            record=instance,
            action=AuditLog.ACTION_UPDATE,
            target_user=instance,
            new_values=_snapshot_fields(instance, field_set),
            reason="User updated",
        )


def on_user_deleted(sender, instance, **kwargs):
    log_audit_event(
        record_type=_record_type(instance),
        record=instance,
        action=AuditLog.ACTION_DELETE,
        target_user=instance,
        previous_values=_snapshot_fields(
            instance,
            ["username", "email", "display_name", "is_active", "date_joined"],
        ),
        reason="User deleted",
        immediate=True,
    )


def on_user_groups_changed(sender, instance, action, reverse, model, pk_set, **kwargs):
    if action not in {"post_add", "post_remove", "post_clear"}:
        return
    if model != Group:
        return
    group_names = list(
        Group.objects.filter(pk__in=(pk_set or set())).values_list("name", flat=True)
    )
    log_audit_event(
        record_type="auth.Group",
        record=instance,
        action=AuditLog.ACTION_ROLE,
        target_user=instance,
        new_values={
            "action": action,
            "reverse": bool(reverse),
            "groups": group_names,
        },
        reason=f"Group membership changed ({action})",
    )


def on_department_membership_saved(sender, instance, created, **kwargs):
    log_audit_event(
        record_type=_record_type(instance),
        record=instance,
        action=AuditLog.ACTION_CREATE if created else AuditLog.ACTION_UPDATE,
        target_user=getattr(instance, "user", None),
        previous_values={} if created else None,
        new_values=_snapshot_fields(
            instance,
            ["department", "position", "is_primary", "is_contributor", "is_active", "date_joined"],
        ),
        reason="Department membership saved",
    )


def on_department_membership_deleted(sender, instance, **kwargs):
    log_audit_event(
        record_type=_record_type(instance),
        record=instance,
        action=AuditLog.ACTION_DELETE,
        target_user=getattr(instance, "user", None),
        previous_values=_snapshot_fields(
            instance,
            ["department", "position", "is_primary", "is_contributor", "is_active"],
        ),
        reason="Department membership deleted",
        immediate=True,
    )


def on_team_membership_saved(sender, instance, created, **kwargs):
    log_audit_event(
        record_type=_record_type(instance),
        record=instance,
        action=AuditLog.ACTION_CREATE if created else AuditLog.ACTION_UPDATE,
        target_user=getattr(instance, "user", None),
        new_values=_snapshot_fields(instance, ["team", "role", "date_joined", "is_active"]),
        reason="Management team membership saved",
    )


def on_team_membership_deleted(sender, instance, **kwargs):
    log_audit_event(
        record_type=_record_type(instance),
        record=instance,
        action=AuditLog.ACTION_DELETE,
        target_user=getattr(instance, "user", None),
        previous_values=_snapshot_fields(instance, ["team", "role", "is_active"]),
        reason="Management team membership deleted",
        immediate=True,
    )


def on_user_login(sender, request, user, **kwargs):
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    ip = xff.split(",")[0].strip() if xff else request.META.get("REMOTE_ADDR")
    log_audit_event(
        record_type="accounts.User",
        record=user,
        action=AuditLog.ACTION_LOGIN,
        user=user,
        target_user=user,
        ip_address=ip,
        reason="User logged in",
        immediate=True,
    )


def on_user_logout(sender, request, user, **kwargs):
    if user is None or not getattr(user, "is_authenticated", False):
        return
    xff = request.META.get("HTTP_X_FORWARDED_FOR") if request else None
    ip = (
        xff.split(",")[0].strip() if xff else (request.META.get("REMOTE_ADDR") if request else None)
    )
    log_audit_event(
        record_type="accounts.User",
        record=user,
        action=AuditLog.ACTION_LOGOUT,
        user=user,
        target_user=user,
        ip_address=ip,
        reason="User logged out",
        immediate=True,
    )


def register_signals():
    post_save.connect(on_user_saved, sender=User, weak=False, dispatch_uid="accounts:user:saved")
    post_delete.connect(
        on_user_deleted, sender=User, weak=False, dispatch_uid="accounts:user:deleted"
    )
    m2m_changed.connect(
        on_user_groups_changed,
        sender=User.groups.through,
        weak=False,
        dispatch_uid="accounts:user:groups",
    )

    post_save.connect(
        on_department_membership_saved,
        sender=DepartmentMembership,
        weak=False,
        dispatch_uid="accounts:deptmembership:saved",
    )
    post_delete.connect(
        on_department_membership_deleted,
        sender=DepartmentMembership,
        weak=False,
        dispatch_uid="accounts:deptmembership:deleted",
    )

    post_save.connect(
        on_team_membership_saved,
        sender=ManagementTeamMembership,
        weak=False,
        dispatch_uid="accounts:teammembership:saved",
    )
    post_delete.connect(
        on_team_membership_deleted,
        sender=ManagementTeamMembership,
        weak=False,
        dispatch_uid="accounts:teammembership:deleted",
    )

    user_logged_in.connect(on_user_login, weak=False, dispatch_uid="accounts:user:login")
    user_logged_out.connect(on_user_logout, weak=False, dispatch_uid="accounts:user:logout")
