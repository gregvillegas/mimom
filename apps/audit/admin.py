from django.contrib import admin

from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = [
        "created_at",
        "action",
        "record_type",
        "record_id_short",
        "user",
        "target_user",
        "ip_address",
    ]
    list_filter = [
        "action",
        "record_type",
        "created_at",
    ]
    search_fields = [
        "record_id",
        "user__username",
        "user__email",
        "target_user__username",
        "target_user__email",
        "reason",
        "correlation_id",
    ]
    readonly_fields = [
        "id",
        "created_at",
        "record_type",
        "record_id",
        "action",
        "user",
        "target_user",
        "ip_address",
        "previous_values_display",
        "new_values_display",
        "changes_display",
        "reason",
        "correlation_id",
    ]
    exclude = ["previous_values", "new_values", "changes"]
    ordering = ["-created_at"]
    list_select_related = ["user", "target_user"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description="Record ID")
    def record_id_short(self, obj: AuditLog) -> str:
        rid = obj.record_id or ""
        return rid[:12] + "…" if len(rid) > 12 else rid

    @admin.display(description="Previous values")
    def previous_values_display(self, obj: AuditLog) -> str:
        import json

        try:
            return json.dumps(obj.previous_values, indent=2, default=str)
        except Exception:
            return str(obj.previous_values)

    @admin.display(description="New values")
    def new_values_display(self, obj: AuditLog) -> str:
        import json

        try:
            return json.dumps(obj.new_values, indent=2, default=str)
        except Exception:
            return str(obj.new_values)

    @admin.display(description="Changes (diff)")
    def changes_display(self, obj: AuditLog) -> str:
        import json

        try:
            return json.dumps(obj.changes, indent=2, default=str)
        except Exception:
            return str(obj.changes)
