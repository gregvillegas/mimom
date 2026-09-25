from __future__ import annotations

from django.core.management.base import BaseCommand, CommandParser
from django.db import transaction

from apps.accounts.models import Department, Position
from apps.sales_updates.models import SalesGroup, SalesTeam


DEPARTMENTS: list[tuple[str, str, str | None]] = [
    ("EXEC", "Executive", "C-Suite and executive leadership (President, GM)."),
    ("ENG", "Engineering", "Engineering, technical design, and service delivery."),
    ("SALES", "Sales", "Sales teams, revenue generation, client partnerships."),
    ("MKT", "Marketing", "Brand, communications, digital marketing, demand gen."),
    ("ACC", "Accounting", "Finance, accounting, treasury, and reporting."),
    ("PUR", "Purchasing", "Procurement, vendor management, purchasing operations."),
    ("WH", "Warehouse", "Warehouse operations, inventory, shipping/receiving."),
]


POSITIONS: list[tuple[str, str, int, str]] = [
    ("PRES", "President", 1, "Executive-level corporate leadership."),
    ("GM", "General Manager", 2, "Overall operations leadership."),
    ("AVP", "AVP", 3, "Assistant Vice President — senior divisional leadership."),
    ("SM", "Sales Manager", 5, "Sales department manager."),
    ("SUPV", "Supervisor", 7, "Generic front-line/operational supervisor."),
    ("TL", "Team Lead", 8, "First-line team lead for project or production."),
    ("AM", "Accounting Manager", 6, "Accounting department head."),
    ("ASUPV", "Accounting Supervisor", 8, "Accounting team supervisor."),
    ("WSUPV", "Warehouse Supervisor", 8, "Warehouse operations supervisor."),
    ("PSUPV", "Purchasing Supervisor", 8, "Procurement & purchasing supervisor."),
    ("OPSM", "Operations Manager", 5, "Operations department head."),
    ("TM", "Technical Manager", 5, "Engineering/technical function manager."),
    ("ASTM", "Asst. Technical Manager", 6, "Reporting to Technical Manager."),
]


SALES_TEAMS: dict[str, list[str]] = {
    "Team A": ["CSG-A", "CSG-B", "CSG-C", "CSG-D", "CSG-I"],
    "Team B": ["CSG-E", "CSG-F", "CSG-H", "CSG-G"],
}


class Command(BaseCommand):
    help = (
        "Idempotently seed the organizational hierarchy: Departments, Positions, "
        "Sales Teams (A/B) and Sales Groups (CSG-A…I). Safe to re-run."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--delete-extra",
            action="store_true",
            help="Delete any CSG sales groups not listed in the spec.",
        )

    @transaction.atomic
    def handle(self, *args, **options) -> None:
        verbosity = int(options.get("verbosity", 1)) or 1
        created_departments = self._upsert_departments(verbosity)
        created_positions = self._upsert_positions(verbosity)
        created_teams, created_groups = self._upsert_sales_teams(
            verbosity, options.get("delete_extra", False)
        )
        self.stdout.write(self.style.SUCCESS(
            "Organization hierarchy seeded OK: "
            f"{created_departments} departments created/updated, "
            f"{created_positions} positions, "
            f"{created_teams} sales teams, {created_groups} sales groups."
        ))

    def _upsert_departments(self, verbosity: int) -> int:
        created = 0
        for order, (code, name, desc) in enumerate(DEPARTMENTS, start=1):
            dept, was_created = Department.objects.update_or_create(
                code__iexact=code,
                defaults={
                    "code": code.upper(),
                    "name": name,
                    "description": desc or "",
                    "is_active": True,
                },
            )
            # Position in parent list order; we want parent=None for all (flat structure).
            dept.parent = None
            if dept.parent_id is None:
                dept.save(update_fields=["parent"])
            created += 1 if was_created else 0
            if verbosity >= 2:
                self.stdout.write(
                    f"  Department {'+' if was_created else '='} {code:<5} {name}"
                )
        return created

    def _upsert_positions(self, verbosity: int) -> int:
        created = 0
        for code, name, level, desc in POSITIONS:
            _pos, was_created = Position.objects.update_or_create(
                code__iexact=code,
                defaults={
                    "code": code.upper(),
                    "name": name,
                    "level": level,
                    "description": desc,
                    "is_active": True,
                },
            )
            created += 1 if was_created else 0
            if verbosity >= 2:
                self.stdout.write(
                    f"  Position  {'+' if was_created else '='} {code:<6} L{level:<2} {name}"
                )
        return created

    def _upsert_sales_teams(self, verbosity: int, delete_extra: bool) -> tuple[int, int]:
        created_teams = 0
        created_groups = 0
        seen_group_codes: set[str] = set()
        for team_name, group_codes in SALES_TEAMS.items():
            team_code = team_name.replace(" ", "")
            team, was_team = SalesTeam.objects.update_or_create(
                code__iexact=team_code,
                defaults={
                    "code": team_code.upper(),
                    "name": team_name,
                    "description": f"Sales organization — {team_name}.",
                    "is_active": True,
                },
            )
            created_teams += 1 if was_team else 0
            if verbosity >= 2:
                self.stdout.write(
                    f"  SalesTeam {'+' if was_team else '='} {team_code:<7} ({team_name})"
                )
            for code in group_codes:
                seen_group_codes.add(code.upper())
                group, was_group = SalesGroup.objects.update_or_create(
                    code__iexact=code,
                    defaults={
                        "code": code.upper(),
                        "name": f"{code} Group",
                        "team": team,
                        "description": f"Sales reporting group — {code} under {team_name}.",
                    },
                )
                created_groups += 1 if was_group else 0
                if verbosity >= 2:
                    self.stdout.write(
                        f"    Group {'+' if was_group else '='} {code:<6} under {team_code}"
                    )
        if delete_extra:
            extra = SalesGroup.objects.exclude(code__in=list(seen_group_codes))
            deleted = extra.delete()[0] if extra.exists() else 0
            if deleted and verbosity >= 1:
                self.stdout.write(f"  Deleted {deleted} unexpected CSG sales groups.")
        return created_teams, created_groups
