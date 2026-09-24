from django.conf import settings
from django.db import models
from django.utils import timezone


class AuditLog(models.Model):
    ACTION_CREATE = "CREATE"
    ACTION_UPDATE = "UPDATE"
    ACTION_DELETE = "DELETE"
    ACTION_APPROVE = "APPROVE"
    ACTION_PUBLISH = "PUBLISH"
    ACTION_LOGIN = "LOGIN"
    ACTION_LOGOUT = "LOGOUT"
    ACTION_ASSIGN = "ASSIGN"
    ACTION_ROLE = "ROLE"
    ACTION_TRANSITION = "TRANSITION"
    ACTION_ARCHIVE = "ARCHIVE"
    ACTION_COMPLETE = "COMPLETE"
    ACTION_REOPEN = "REOPEN"
    ACTION_CARRY_FORWARD = "CARRY_FORWARD"
    ACTION_LOCK = "LOCK"
    ACTION_EXPORT = "EXPORT"

    ACTION_CHOICES = [
        (ACTION_CREATE, "Create"),
        (ACTION_UPDATE, "Update"),
        (ACTION_DELETE, "Delete"),
        (ACTION_APPROVE, "Approve"),
        (ACTION_PUBLISH, "Publish"),
        (ACTION_LOGIN, "Login"),
        (ACTION_LOGOUT, "Logout"),
        (ACTION_ASSIGN, "Assign"),
        (ACTION_ROLE, "Role Change"),
        (ACTION_TRANSITION, "Workflow Transition"),
        (ACTION_ARCHIVE, "Archive"),
        (ACTION_COMPLETE, "Complete"),
        (ACTION_REOPEN, "Reopen"),
        (ACTION_CARRY_FORWARD, "Carry Forward"),
        (ACTION_LOCK, "Lock Record"),
        (ACTION_EXPORT, "Export Data"),
    ]

    id = models.BigAutoField(primary_key=True)
    record_type = models.CharField(
        max_length=100,
        db_index=True,
        help_text="e.g. accounts.User, accounts.DepartmentMembership, auth.Group",
    )
    record_id = models.CharField(
        max_length=128, db_index=True, help_text="Primary key (UUID as string or int)"
    )
    action = models.CharField(max_length=16, choices=ACTION_CHOICES, db_index=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_events_initiated",
    )
    target_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_events_about",
        help_text="If the record relates to a user, this holds their reference.",
    )
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    previous_values = models.JSONField(default=dict, blank=True)
    new_values = models.JSONField(default=dict, blank=True)
    changes = models.JSONField(default=dict, blank=True)
    reason = models.TextField(blank=True)
    correlation_id = models.CharField(max_length=64, blank=True, db_index=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True, editable=False)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Audit Log"
        verbose_name_plural = "Audit Logs"
        indexes = [
            models.Index(fields=["record_type", "record_id"]),
            models.Index(fields=["created_at", "action"]),
            models.Index(fields=["user", "action"]),
        ]

    def __str__(self) -> str:
        user = self.user.get_display_name() if self.user else "system"
        return f"[{self.created_at:%Y-%m-%d %H:%M:%S}] {self.action} {self.record_type} id={self.record_id} by {user}"
