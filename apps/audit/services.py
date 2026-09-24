import logging
import uuid
from typing import Any

from django.db import transaction

from .models import AuditLog

logger = logging.getLogger(__name__)


def _safe_model_pk(obj: Any) -> str:
    if obj is None:
        return ""
    pk = getattr(obj, "pk", None)
    if pk is None:
        return ""
    return str(pk)


def _diff_values(previous: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    changes: dict[str, Any] = {}
    keys = set(previous) | set(new)
    for key in keys:
        old = previous.get(key)
        new_val = new.get(key)
        if old != new_val:
            changes[key] = {"old": old, "new": new_val}
    return changes


def _write_audit_log(
    *,
    record_type: str,
    record_id: str,
    action: str,
    user_id: str | None = None,
    target_user_id: str | None = None,
    ip_address: str | None = None,
    previous_values: dict | None = None,
    new_values: dict | None = None,
    reason: str = "",
    correlation_id: str | None = None,
):
    try:
        previous_values = previous_values or {}
        new_values = new_values or {}
        AuditLog.objects.create(
            record_type=record_type,
            record_id=record_id,
            action=action,
            user_id=user_id,
            target_user_id=target_user_id,
            ip_address=ip_address,
            previous_values=previous_values,
            new_values=new_values,
            changes=_diff_values(previous_values, new_values),
            reason=reason,
            correlation_id=correlation_id or str(uuid.uuid4()),
        )
    except Exception as exc:
        logger.exception("Failed to write audit log event: %s", exc)


def log_audit_event(
    *,
    record_type: str,
    record,
    action: str,
    user=None,
    target_user=None,
    ip_address: str | None = None,
    previous_values: dict | None = None,
    new_values: dict | None = None,
    reason: str = "",
    correlation_id: str | None = None,
    immediate: bool = False,
) -> str:
    """Queue (or write immediately) an audit log event.

    When `immediate=False` (default) the write is scheduled via
    `transaction.on_commit` so the audit entry survives only if the enclosing
    transaction commits. When no transaction is active, the event is written
    immediately.
    """
    resolved_correlation = correlation_id or str(uuid.uuid4())
    payload = dict(
        record_type=record_type,
        record_id=_safe_model_pk(record),
        action=action,
        user_id=_safe_model_pk(user) or None,
        target_user_id=_safe_model_pk(target_user) or None,
        ip_address=ip_address,
        previous_values=previous_values or {},
        new_values=new_values or {},
        reason=reason,
        correlation_id=resolved_correlation,
    )

    def _writer():
        _write_audit_log(**payload)

    if immediate:
        _writer()
        return resolved_correlation

    try:
        transaction.on_commit(_writer)
    except transaction.TransactionManagementError:
        _writer()
    return resolved_correlation
