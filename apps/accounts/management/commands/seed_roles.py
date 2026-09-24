from django.apps import apps
from django.contrib.auth.management import create_permissions
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand

from apps.accounts.models import (
    Department,
    DepartmentMembership,
    ManagementTeam,
    ManagementTeamMembership,
    Position,
    User,
)

SYSTEM_ADMIN = "System Administrator"
MANAGEMENT_ADMIN = "Management Administrator"
MEETING_CHAIR = "Meeting Chairperson"
MINUTES_SECRETARY = "Minutes Secretary"
DEPT_CONTRIBUTOR = "Department Contributor"
VIEWER = "Viewer"

ROLE_NAMES = [
    SYSTEM_ADMIN,
    MANAGEMENT_ADMIN,
    MEETING_CHAIR,
    MINUTES_SECRETARY,
    DEPT_CONTRIBUTOR,
    VIEWER,
]


def _ct(model_cls) -> ContentType:
    return ContentType.objects.get_for_model(model_cls)


def _ensure_default_permissions():
    for app_config in apps.get_app_configs():
        create_permissions(app_config, verbosity=0)


def _perms(models, *, codenames=None):
    result = []
    for model in models:
        ct = _ct(model)
        if codenames is None:
            lookups = [
                f"add_{model._meta.model_name}",
                f"change_{model._meta.model_name}",
                f"delete_{model._meta.model_name}",
                f"view_{model._meta.model_name}",
            ]
        else:
            lookups = list(codenames)
        for codename in lookups:
            p = Permission.objects.filter(content_type=ct, codename=codename).first()
            if p is not None:
                result.append(p)
    return result


class Command(BaseCommand):
    help = "Idempotently create the 6 standard role groups and assign their default permissions."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset-perms",
            action="store_true",
            help="Revoke existing permissions for each role before re-assigning defaults (rare).",
        )

    def handle(self, *args, **options):
        _ensure_default_permissions()
        reset = options.get("reset_perms")
        created_count = 0

        role_config = self._role_permission_config()

        for role_name in ROLE_NAMES:
            group, created = Group.objects.get_or_create(name=role_name)
            if created:
                created_count += 1
                self.stdout.write(self.style.SUCCESS(f"Created group: {role_name}"))
            else:
                self.stdout.write(f"Group exists: {role_name}")

            if reset:
                group.permissions.clear()

            perms_needed = role_config.get(role_name, [])
            group.permissions.add(*perms_needed)
            self.stdout.write(
                self.style.WARNING(
                    f"  + Ensured {group.permissions.count()} permissions for {role_name}"
                )
            )

        self.stdout.write(
            self.style.SUCCESS(f"Done. {created_count} group(s) created, 6 role(s) ensured.")
        )

    def _role_permission_config(self) -> dict[str, list[Permission]]:
        all_accounts = _perms(
            [
                User,
                Department,
                Position,
                ManagementTeam,
                DepartmentMembership,
                ManagementTeamMembership,
            ]
        )

        view_accounts = _perms(
            [
                User,
                Department,
                Position,
                ManagementTeam,
                DepartmentMembership,
                ManagementTeamMembership,
            ],
            codenames=[
                f"view_{m._meta.model_name}"
                for m in [
                    User,
                    Department,
                    Position,
                    ManagementTeam,
                    DepartmentMembership,
                    ManagementTeamMembership,
                ]
            ],
        )
        edit_accounts = _perms(
            [
                User,
                Department,
                Position,
                ManagementTeam,
                DepartmentMembership,
                ManagementTeamMembership,
            ],
            codenames=[
                f"view_{m._meta.model_name}"
                for m in [
                    User,
                    Department,
                    Position,
                    ManagementTeam,
                    DepartmentMembership,
                    ManagementTeamMembership,
                ]
            ]
            + [
                f"add_{m._meta.model_name}"
                for m in [DepartmentMembership, ManagementTeamMembership]
            ]
            + [
                f"change_{m._meta.model_name}"
                for m in [User, DepartmentMembership, ManagementTeamMembership]
            ],
        )

        view_audit = _perms(
            apps.get_app_config("audit").get_models(),
            codenames=[
                f"view_{m._meta.model_name}" for m in apps.get_app_config("audit").get_models()
            ],
        )

        # Placeholder perms for future apps (meetings, action_items, sales_updates)
        # These are safe because we only add perms that exist; get_or_create would error.
        # We skip them until models are defined so the command is safe to run early.
        future_model_perms: list[Permission] = []

        return {
            SYSTEM_ADMIN: sorted(
                list(set(all_accounts + view_audit + future_model_perms)),
                key=lambda p: (p.content_type.app_label, p.codename),
            ),
            MANAGEMENT_ADMIN: sorted(
                list(set(edit_accounts + view_audit + future_model_perms)),
                key=lambda p: (p.content_type.app_label, p.codename),
            ),
            MEETING_CHAIR: sorted(
                list(set(view_accounts)), key=lambda p: (p.content_type.app_label, p.codename)
            ),
            MINUTES_SECRETARY: sorted(
                list(set(view_accounts)), key=lambda p: (p.content_type.app_label, p.codename)
            ),
            DEPT_CONTRIBUTOR: sorted(
                list(set(view_accounts)), key=lambda p: (p.content_type.app_label, p.codename)
            ),
            VIEWER: sorted(
                list(set(view_accounts)), key=lambda p: (p.content_type.app_label, p.codename)
            ),
        }
