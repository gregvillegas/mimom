from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import (
    Department,
    DepartmentMembership,
    ManagementTeam,
    ManagementTeamMembership,
    Position,
    User,
)


class DepartmentMembershipInline(admin.TabularInline):
    model = DepartmentMembership
    extra = 0
    raw_id_fields = ["user", "department", "position"]


class ManagementTeamMembershipInline(admin.TabularInline):
    model = ManagementTeamMembership
    extra = 0
    raw_id_fields = ["user", "team"]


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    list_display = [
        "username",
        "email",
        "get_display_name",
        "get_primary_dept",
        "get_role_groups",
        "is_active",
        "is_staff",
        "is_superuser",
        "date_joined",
    ]
    list_filter = ["is_active", "is_staff", "is_superuser", "theme", "groups"]
    search_fields = ["username", "email", "first_name", "last_name", "display_name"]
    ordering = ["username"]

    fieldsets = (
        (None, {"fields": ["username", "password"]}),
        ("Personal info", {"fields": ["first_name", "last_name", "email"]}),
        (
            "Intranet Profile",
            {"fields": ["display_name", "initials", "phone", "signature_text", "theme", "bio"]},
        ),
        (
            "Permissions",
            {
                "fields": [
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                ],
            },
        ),
        ("Important dates", {"fields": ["last_login", "date_joined"]}),
    )

    add_fieldsets = (
        (
            None,
            {
                "classes": ["wide"],
                "fields": ["username", "email", "password1", "password2"],
            },
        ),
    )

    inlines = [DepartmentMembershipInline, ManagementTeamMembershipInline]

    @admin.display(description="Name")
    def get_display_name(self, obj):
        return obj.get_display_name()

    @admin.display(description="Primary Dept")
    def get_primary_dept(self, obj):
        dept = obj.get_primary_department()
        return dept.name if dept else "—"

    @admin.display(description="Roles")
    def get_role_groups(self, obj):
        names = list(obj.groups.values_list("name", flat=True).order_by("name"))
        if not names:
            return "—"
        if len(names) <= 2:
            return ", ".join(names)
        return ", ".join(names[:2]) + f" +{len(names) - 2}"


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ["name", "code", "head", "parent", "is_active"]
    list_filter = ["is_active", "parent"]
    search_fields = ["name", "code", "description"]
    prepopulated_fields = {"code": ["name"]}


@admin.register(Position)
class PositionAdmin(admin.ModelAdmin):
    list_display = ["name", "code", "level", "is_active"]
    list_filter = ["is_active"]
    search_fields = ["name", "code", "description"]
    prepopulated_fields = {"code": ["name"]}


@admin.register(DepartmentMembership)
class DepartmentMembershipAdmin(admin.ModelAdmin):
    list_display = ["user", "department", "position", "is_primary", "is_contributor", "is_active"]
    list_filter = ["is_primary", "is_contributor", "department", "is_active"]
    search_fields = [
        "user__username",
        "user__email",
        "department__name",
        "position__name",
    ]
    raw_id_fields = ["user", "department", "position"]


@admin.register(ManagementTeam)
class ManagementTeamAdmin(admin.ModelAdmin):
    list_display = ["name", "is_active"]
    list_filter = ["is_active"]
    search_fields = ["name", "description"]
    inlines = [ManagementTeamMembershipInline]


@admin.register(ManagementTeamMembership)
class ManagementTeamMembershipAdmin(admin.ModelAdmin):
    list_display = ["team", "user", "role", "date_joined", "is_active"]
    list_filter = ["team", "is_active"]
    search_fields = ["team__name", "user__username", "role"]
    raw_id_fields = ["team", "user"]
