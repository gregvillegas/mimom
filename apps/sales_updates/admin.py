from django.contrib import admin

from apps.sales_updates.models import (
    DeliveryPerformance,
    GroupPerformanceSnapshot,
    PerformanceTarget,
    ReportingPeriod,
    SalesGroup,
    SalesGroupMembership,
    SalesOrderPerformance,
    SalesTeam,
    WeeklyCommitment,
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


@admin.register(ReportingPeriod)
class ReportingPeriodAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "start_date",
        "end_date",
        "cut_off_date",
        "weeks_count",
        "status",
        "currency",
        "days_until_cutoff",
    )
    list_filter = ("status", "currency", "weeks_count")
    search_fields = ("name",)
    raw_id_fields = ("created_by",)
    date_hierarchy = "start_date"


@admin.register(SalesTeam)
class SalesTeamAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "leader", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "code")
    raw_id_fields = ("leader",)


class SalesGroupMembershipInline(ReadOnlyInlineMixin, admin.TabularInline):
    model = SalesGroupMembership
    fields = ("user", "role", "is_active", "joined_on", "left_on")
    raw_id_fields = ("user",)


@admin.register(SalesGroup)
class SalesGroupAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "team", "manager", "is_active")
    list_filter = ("team", "is_active")
    search_fields = ("name", "code")
    raw_id_fields = ("manager",)
    inlines = [SalesGroupMembershipInline]


@admin.register(PerformanceTarget)
class PerformanceTargetAdmin(admin.ModelAdmin):
    list_display = (
        "group",
        "period",
        "revenue_target",
        "profit_target",
        "orders_target",
        "deliveries_target",
        "currency",
    )
    list_filter = ("period__status", "currency")
    search_fields = ("group__name", "group__code", "period__name")
    raw_id_fields = ("group", "period", "last_modified_by")


@admin.register(DeliveryPerformance)
class DeliveryPerformanceAdmin(admin.ModelAdmin):
    list_display = (
        "group",
        "period",
        "deliveries_planned",
        "deliveries_achieved",
        "deliveries_on_time",
        "delivery_achievement_pct",
        "on_time_pct",
    )
    list_filter = ("period__status",)
    search_fields = ("group__name", "period__name")
    raw_id_fields = ("group", "period", "last_modified_by")


@admin.register(SalesOrderPerformance)
class SalesOrderPerformanceAdmin(admin.ModelAdmin):
    list_display = (
        "group",
        "period",
        "revenue_actual",
        "profit_actual",
        "margin_pct_actual",
        "orders_actual",
        "currency",
    )
    list_filter = ("period__status", "currency")
    search_fields = ("group__name", "period__name")
    raw_id_fields = ("group", "period", "last_modified_by")


class WeeklyCommitmentInline(ReadOnlyInlineMixin, admin.TabularInline):
    model = WeeklyCommitment
    fields = (
        "week_number",
        "committed_revenue",
        "committed_profit",
        "actual_revenue",
        "actual_profit",
    )


@admin.register(GroupPerformanceSnapshot)
class GroupPerformanceSnapshotAdmin(admin.ModelAdmin):
    list_display = (
        "group",
        "period",
        "meeting",
        "revenue_target",
        "revenue_actual",
        "revenue_pct_achieved",
        "revenue_deficit",
        "currency",
        "is_locked",
    )
    list_filter = ("period__status", "currency")
    search_fields = ("group__name", "period__name", "meeting__reference")
    raw_id_fields = ("group", "period", "meeting", "created_by")
    inlines = [WeeklyCommitmentInline]
    readonly_fields = (
        "revenue_pct_achieved",
        "revenue_deficit",
        "profit_pct_achieved",
        "profit_deficit",
        "is_locked",
    )
