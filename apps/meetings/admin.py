from django.contrib import admin

from apps.meetings.models import (
    ActionItemLink,
    AgendaCategory,
    AgendaItem,
    AgendaItemAttachment,
    ApprovedMeetingSnapshot,
    DepartmentSubmission,
    Meeting,
    MeetingAttachment,
    MeetingAttendance,
    MeetingStatusHistory,
    MeetingType,
    MinutesSectionSpec,
)


class ReadOnlyInlineMixin:
    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class MeetingStatusHistoryInline(ReadOnlyInlineMixin, admin.TabularInline):
    model = MeetingStatusHistory
    extra = 0
    fields = ("from_status", "to_status", "transitioned_at", "transitioned_by", "reason")
    ordering = ("-transitioned_at",)


class MeetingAttendanceInline(admin.TabularInline):
    model = MeetingAttendance
    extra = 0
    fields = (
        "user",
        "is_invited",
        "is_attended",
        "rsvp_status",
        "arrived_at",
        "departed_at",
    )
    autocomplete_fields = ("user",)


class AgendaItemInline(admin.TabularInline):
    model = AgendaItem
    extra = 0
    fields = (
        "order",
        "title",
        "category",
        "item_status",
        "owner",
        "is_confidential",
    )
    ordering = ("order",)


class MeetingAttachmentInline(admin.TabularInline):
    model = MeetingAttachment
    extra = 0
    fields = ("file", "display_name", "uploaded_by", "is_confidential")
    readonly_fields = ("uploaded_by",)


class DepartmentSubmissionInline(admin.TabularInline):
    model = DepartmentSubmission
    extra = 0
    fields = (
        "department",
        "contributor",
        "submission_state",
        "last_updated_at",
        "last_submitted_at",
        "submitted_by",
        "missing_info",
        "management_remarks",
    )
    readonly_fields = ("last_updated_at", "last_submitted_at")
    autocomplete_fields = ("department", "contributor", "submitted_by")


class ActionItemLinkInline(admin.TabularInline):
    model = ActionItemLink
    extra = 0
    fields = ("agenda_item", "action_item", "created_by", "created_at")
    readonly_fields = ("created_by", "created_at")
    autocomplete_fields = ("agenda_item", "action_item")


@admin.register(MeetingType)
class MeetingTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "is_active", "default_duration_minutes")
    list_filter = ("is_active",)
    search_fields = ("name", "code")
    prepopulated_fields = {"code": ("name",)}


@admin.register(Meeting)
class MeetingAdmin(admin.ModelAdmin):
    list_display = (
        "reference",
        "title",
        "type",
        "status",
        "start_at",
        "chair",
        "department",
        "is_locked",
    )
    list_filter = (
        "status",
        "type",
        "is_locked",
        "department",
        "chair",
        "start_at",
    )
    search_fields = ("reference", "title", "location", "description")
    date_hierarchy = "start_at"
    readonly_fields = (
        "reference",
        "published_at",
        "closed_at",
        "archived_at",
        "created_by",
        "last_modified_by",
    )
    autocomplete_fields = ("chair", "department", "type", "created_by", "last_modified_by")
    inlines = [
        MeetingStatusHistoryInline,
        MeetingAttendanceInline,
        AgendaItemInline,
        DepartmentSubmissionInline,
        MeetingAttachmentInline,
    ]


@admin.register(MeetingStatusHistory)
class MeetingStatusHistoryAdmin(ReadOnlyInlineMixin if False else admin.ModelAdmin):
    list_display = ("meeting", "from_status", "to_status", "transitioned_at", "transitioned_by")
    list_filter = ("from_status", "to_status", "transitioned_at")
    search_fields = ("meeting__reference", "meeting__title", "reason")
    date_hierarchy = "transitioned_at"
    readonly_fields = (
        "meeting",
        "from_status",
        "to_status",
        "transitioned_at",
        "transitioned_by",
        "reason",
    )

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(MeetingAttendance)
class MeetingAttendanceAdmin(admin.ModelAdmin):
    list_display = ("meeting", "user", "is_invited", "is_attended", "rsvp_status")
    list_filter = ("is_invited", "is_attended", "rsvp_status", "meeting__status")
    search_fields = ("meeting__reference", "meeting__title", "user__username")
    autocomplete_fields = ("meeting", "user")


@admin.register(AgendaCategory)
class AgendaCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "order", "scope_department", "is_active")
    list_filter = ("is_active", "scope_department")
    search_fields = ("name", "description")
    ordering = ("order", "name")


@admin.register(AgendaItem)
class AgendaItemAdmin(admin.ModelAdmin):
    list_display = (
        "meeting",
        "order",
        "title",
        "category",
        "item_status",
        "owner",
        "is_confidential",
    )
    list_filter = (
        "item_status",
        "is_confidential",
        "category",
        "meeting__status",
    )
    search_fields = ("meeting__reference", "meeting__title", "title", "discussion", "decision")
    autocomplete_fields = (
        "meeting",
        "category",
        "owner",
        "department",
        "parent_item",
        "carried_forward_from",
    )
    ordering = ("meeting__start_at", "order")
    inlines = [
        ActionItemLinkInline,
    ]


@admin.register(MeetingAttachment)
class MeetingAttachmentAdmin(admin.ModelAdmin):
    list_display = (
        "meeting",
        "display_name_or_file",
        "uploaded_by",
        "is_confidential",
        "is_active",
        "created_at",
    )
    list_filter = ("is_confidential", "is_active", "meeting__status")
    search_fields = ("meeting__reference", "meeting__title", "display_name", "description")
    readonly_fields = ("uploaded_by",)
    autocomplete_fields = ("meeting",)

    def display_name_or_file(self, obj):
        return obj.display_name or obj.file.name.split("/")[-1]

    display_name_or_file.short_description = "File"


@admin.register(AgendaItemAttachment)
class AgendaItemAttachmentAdmin(admin.ModelAdmin):
    list_display = (
        "item",
        "display_name_or_file",
        "uploaded_by",
        "is_confidential",
        "is_active",
        "created_at",
    )
    list_filter = ("is_confidential", "is_active")
    search_fields = ("item__title", "display_name", "description")
    readonly_fields = ("uploaded_by",)
    autocomplete_fields = ("item",)

    def display_name_or_file(self, obj):
        return obj.display_name or obj.file.name.split("/")[-1]

    display_name_or_file.short_description = "File"


@admin.register(MinutesSectionSpec)
class MinutesSectionSpecAdmin(admin.ModelAdmin):
    list_display = (
        "meeting_type",
        "section_type",
        "order",
        "name",
        "is_required",
    )
    list_filter = ("is_required", "section_type", "meeting_type")
    search_fields = ("name", "description", "meeting_type__name", "meeting_type__code")
    ordering = ("meeting_type", "order", "name")
    autocomplete_fields = ("meeting_type",)


@admin.register(DepartmentSubmission)
class DepartmentSubmissionAdmin(admin.ModelAdmin):
    list_display = (
        "meeting",
        "department",
        "contributor",
        "submission_state",
        "last_updated_at",
        "last_submitted_at",
        "submitted_by",
    )
    list_filter = (
        "submission_state",
        "meeting__status",
        "meeting__type",
        "department",
    )
    search_fields = (
        "meeting__reference",
        "meeting__title",
        "department__name",
        "missing_info",
        "management_remarks",
    )
    date_hierarchy = "last_submitted_at"
    readonly_fields = ("last_updated_at", "last_submitted_at")
    autocomplete_fields = ("meeting", "department", "contributor", "submitted_by")


@admin.register(ActionItemLink)
class ActionItemLinkAdmin(admin.ModelAdmin):
    list_display = (
        "agenda_item",
        "action_item",
        "created_by",
        "created_at",
    )
    list_filter = ("created_at",)
    search_fields = (
        "agenda_item__title",
        "agenda_item__meeting__reference",
        "action_item__reference",
        "action_item__title",
    )
    date_hierarchy = "created_at"
    readonly_fields = ("created_by", "created_at")
    autocomplete_fields = ("agenda_item", "action_item")


@admin.register(ApprovedMeetingSnapshot)
class ApprovedMeetingSnapshotAdmin(admin.ModelAdmin):
    list_display = (
        "meeting",
        "version",
        "trigger",
        "approved_at",
        "approved_by",
        "published_at",
    )
    list_filter = ("trigger", "approved_at", "published_at")
    search_fields = (
        "meeting__reference",
        "meeting__title",
        "notes",
    )
    date_hierarchy = "approved_at"
    readonly_fields = (
        "meeting",
        "version",
        "trigger",
        "payload",
        "approved_at",
        "approved_by",
        "published_at",
        "published_by",
    )

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
