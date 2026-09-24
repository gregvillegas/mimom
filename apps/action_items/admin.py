from django.contrib import admin

from apps.action_items.models import (
    ActionItem,
    ActionItemAssignee,
    ActionItemAttachment,
    ActionItemCarryForwardLink,
    ActionItemStatusHistory,
    ActionItemUpdate,
)


class ReadOnlyInlineMixin:
    extra = 0
    can_delete = False
    show_change_link = False

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class ActionItemAssigneeInline(ReadOnlyInlineMixin, admin.TabularInline):
    model = ActionItemAssignee
    fields = ("user", "is_primary", "is_supporting", "notes")
    raw_id_fields = ("user",)


class ActionItemStatusHistoryInline(ReadOnlyInlineMixin, admin.TabularInline):
    model = ActionItemStatusHistory
    fields = (
        "from_status",
        "to_status",
        "progress_before",
        "progress_after",
        "transitioned_at",
        "transitioned_by",
        "reason",
    )
    raw_id_fields = ("transitioned_by",)


class ActionItemUpdateInline(ReadOnlyInlineMixin, admin.TabularInline):
    model = ActionItemUpdate
    fields = ("created_at", "author", "status_snapshot", "progress_snapshot", "body", "attachment")
    raw_id_fields = ("author",)


class ActionItemAttachmentInline(ReadOnlyInlineMixin, admin.TabularInline):
    model = ActionItemAttachment
    fields = ("created_at", "uploaded_by", "file", "caption")
    raw_id_fields = ("uploaded_by",)


class ActionItemCarryForwardLinkInline(ReadOnlyInlineMixin, admin.TabularInline):
    model = ActionItemCarryForwardLink
    fk_name = "source_item"
    fields = (
        "carried_at",
        "carried_by",
        "new_item",
        "target_meeting",
        "target_scope_key",
        "reason",
    )
    raw_id_fields = ("carried_by", "new_item", "target_meeting")


@admin.register(ActionItem)
class ActionItemAdmin(admin.ModelAdmin):
    list_display = (
        "reference",
        "title",
        "status",
        "priority",
        "progress_pct",
        "due_date",
        "department",
        "owner",
    )
    list_filter = ("status", "priority", "department")
    search_fields = ("reference", "title", "description")
    ordering = ("priority", "due_date", "created_at")
    date_hierarchy = "created_at"
    raw_id_fields = (
        "created_by",
        "last_modified_by",
        "owner",
        "department",
        "source_meeting",
        "source_agenda_item",
        "carried_forward_from",
    )
    readonly_fields = ("reference", "completed_at", "reopened_count")
    inlines = (
        ActionItemAssigneeInline,
        ActionItemStatusHistoryInline,
        ActionItemUpdateInline,
        ActionItemAttachmentInline,
        ActionItemCarryForwardLinkInline,
    )


@admin.register(ActionItemAssignee)
class ActionItemAssigneeAdmin(admin.ModelAdmin):
    list_display = ("action_item", "user", "is_primary", "is_supporting")
    list_filter = ("is_primary", "is_supporting")
    raw_id_fields = ("action_item", "user")
    search_fields = ("action_item__reference", "user__username")


@admin.register(ActionItemUpdate)
class ActionItemUpdateAdmin(admin.ModelAdmin):
    list_display = ("action_item", "created_at", "author", "status_snapshot", "progress_snapshot")
    list_filter = ("status_snapshot",)
    raw_id_fields = ("action_item", "author")
    search_fields = ("action_item__reference", "body")
    date_hierarchy = "created_at"


@admin.register(ActionItemAttachment)
class ActionItemAttachmentAdmin(admin.ModelAdmin):
    list_display = ("action_item", "filename", "caption", "uploaded_by", "created_at")
    raw_id_fields = ("action_item", "uploaded_by")
    search_fields = ("action_item__reference", "caption")


@admin.register(ActionItemStatusHistory)
class ActionItemStatusHistoryAdmin(admin.ModelAdmin):
    list_display = (
        "action_item",
        "from_status",
        "to_status",
        "progress_before",
        "progress_after",
        "transitioned_at",
        "transitioned_by",
    )
    list_filter = ("from_status", "to_status")
    raw_id_fields = ("action_item", "transitioned_by")
    search_fields = ("action_item__reference", "reason")


@admin.register(ActionItemCarryForwardLink)
class ActionItemCarryForwardLinkAdmin(admin.ModelAdmin):
    list_display = ("source_item", "new_item", "target_meeting", "carried_at", "carried_by")
    list_filter = ("target_scope_key",)
    raw_id_fields = ("source_item", "new_item", "target_meeting", "carried_by")
    search_fields = ("source_item__reference", "new_item__reference", "reason")
