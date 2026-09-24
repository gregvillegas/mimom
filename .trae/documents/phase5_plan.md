# Phase 5: Sales Updates & Commitments Implementation Plan

## Repository Research

Project state at plan creation:
- Django 6.1.1 monolith (Python 3.14) at `/Users/greg/Documents/intranet/`.
- Base architecture recap:
  - `AUTH_USER_MODEL = accounts.User` — BigAutoField PK (not UUID).
  - `apps/core/models.py` — `TimeStampedModel` abstract with UUID PK + created/updated timestamps; `BaseNamedModel` (name + is_active) inherits it. All previous domain models (meetings/action_items) use TimeStampedModel → UUID PKs, so every sales_updates domain model MUST inherit TimeStampedModel (UUID) and use `<uuid:pk>` URL converters in routes. User FKs are BigInt (no change).
  - Global `DEFAULT_AUTO_FIELD = BigAutoField`, `ATOMIC_REQUESTS = True`.
  - Audit service signature from Phase 2–4 established: `log_audit_event(*, record_type: str, record: Model instance, action: str, user=None, target_user=None, ip_address=None, previous_values=None, new_values=None, reason="", correlation_id=None, immediate=False)`. DO NOT pass `changes=`; diff computed from previous_values/new_values.
- Installed scaffolding already present:
  - `INSTALLED_APPS` already registers `apps.sales_updates` + `apps.notifications` ([config/settings/base.py](../config/settings/base.py#L39-L40)).
  - `config/urls.py` already includes `path("sales/", include("apps.sales_updates.urls"))` (namespace "sales_updates" in existing [apps/sales_updates/urls.py](../apps/sales_updates/urls.py)).
  - Package `apps/sales_updates/` has empty `models.py`, `views.py`, `admin.py`, `apps.py` (Config declares default BigAutoField + verbose_name "Sales Updates"), `migrations/__init__.py`.
- Dependencies already installed/available:
  - `openpyxl>=3.1` in `pyproject.toml` — use for Excel export (PHASE5 item 15).
  - WeasyPrint mentioned optional for PDFs (README.md) — use Django template rendering for Printable Minutes HTML fragment (item 16) and do NOT require WeasyPrint; just expose a `?printable=1` style-switch view that the meeting minutes template can include or a link to `sales/export/<snapshot>/printable.html`.
- Navigation placeholders: sidebar.html#52-60 + offcanvas.html#66-70 have 3 Sales href="#" (Sales Performance, Commitments, Export) — need rewiring (mirror action_items step).
- Dashboard home.html has two rows of KPIs (meetings + action items). Phase 5 appends a THIRD row of 4 sales KPI cards + right-side table "Next Cut-Off / Current Period Deficit".
- Existing hard rules (NEVER relax, carry forward from phases 2–4):
  1. Phase 5 audit action constants may add: ACTION_LOCK / ACTION_EXPORT. AuditLog.action max_length=16 already; verify new strings fit. Do NOT alter field length unless needed.
  2. Phase 5 also uses Decimal (max_digits=16, decimal_places=2 per P5 rules 42-43). Do NOT use float anywhere for money. PHP (Philippine Peso) locale formatting helpers in templates via `django.contrib.humanize` + custom `currency_format` filter.
  3. No 4-week hard-coded columns (P5 rule 44). WeeklyCommitment rows are separate related records (a GroupPerformanceSnapshot has N WeeklyCommitment rows via FK, not 4 static columns on snapshot itself).
  4. Permit 4/5-week periods via ReportingPeriod.weeks_count PositiveSmallInteger (4 or 5 only) validated in clean(); WeeklyCommitment.week_number 1..weeks_count.
  5. Stored snapshots justified (P5 rule 46): only GroupPerformanceSnapshot is persisted (freezed values at meeting link time) — all other totals/subtotals/percents are @property / service computed.
  6. Duplicate group-period UNIQUE validation via unique_together on PerformanceTarget & DeliveryPerformance & SalesOrderPerformance (group, period) — rule 47.
  7. Negative values consistently display with red text + `(₱ -1,234.56)` format (CSS `.text-negative` + filter).

## Files and Modules

**Create / overwrite (sales_updates app core):**
- `apps/sales_updates/models.py` — 9 domain models: ReportingPeriod, SalesTeam, SalesGroup, SalesGroupMembership, PerformanceTarget, DeliveryPerformance, SalesOrderPerformance, WeeklyCommitment, GroupPerformanceSnapshot. Module-level STATUS constants for period statuses (DRAFT, OPEN, CLOSED) + snapshot lock statuses. Currency constants (PHP/USD/EUR/JPY) with choice tuples.
- `apps/sales_updates/migrations/0001_initial.py` — auto-generated after models written; applies indexes + unique_together + FK on_delete (SET_NULL for period deletion preserving data where needed).
- `apps/sales_updates/services.py` — tested calculation functions: `percentage_achieved(target, actual)`, `deficit(target, actual)` (negative when behind, positive when ahead), `group_period_subtotals(group, period)`, `team_period_totals(team, period)`, `overall_period_totals(period)`, `monthly_average(values_list, months_count)`, `weekly_commitment_totals(snapshot)`, `currency_format(value, currency, *, with_sign=True, negative_parens=False)`, `take_snapshot(group, period, *, meeting=None, by_user)`, `is_snapshot_locked(snapshot)` → True when linked Meeting status is APPROVED/PUBLISHED (rule 14 lock).
- `apps/sales_updates/forms.py` — 7 forms: ReportingPeriodForm, SalesTeamForm, SalesGroupForm+MembershipFormSet, PerformanceTargetForm, DeliveryPerformanceForm, SalesOrderPerformanceForm, SnapshotCreateForm, BulkWeeklyCommitmentForm (DynamicFormSet for N-weeks). Include CurrencySelect for fields with currency; use DecimalField widget with 2dp step.
- `apps/sales_updates/views.py` — ~15 CBVs: ReportingPeriod list/create/update, SalesTeam+Group list/create/update + memberships edit, PerformanceTarget create-update-for-period, DeliveryPerformance create-update, SalesOrderPerformance create-update, GroupPeriodView (combines target/delivery/sales-order/weekly table, charts JSON, cut-off widget), SnapshotView, ExcelExportView (StreamingHttpResponse + openpyxl), PrintableMinutesView (HTML fragment), PeriodDashboard summary.
- `apps/sales_updates/urls.py` — 16 namespaced routes `sales_updates:`; use `<uuid:pk>` + `<uuid:period_id>` + `<uuid:group_id>` URL converters.
- `apps/sales_updates/admin.py` — 9 @admin.register() with ReadOnlyInlineMixin + 4 inlines (Memberships, Targets, WeeklyCommitments, Snapshots).
- `apps/sales_updates/templatetags/sales_formatting.py` — `@register.filter currency_format(value, currency)`, `@register.filter percentage(value, digits=1)`, `@register.filter negative_class(value)` → `text-danger` / `text-success`.
- `apps/sales_updates/signals.py` + `apps/sales_updates/apps.py:ready()` — on Snapshot post-save, if meeting is APPROVED/PUBLISHED, log audit ACTION_LOCK.

**Permissions layer (apps/core):**
- `apps/core/permissions.py` — append `SALES_AUTHOR_ROLES = (Sys, Mgmt)` + `SALES_VIEWER_ROLES = (*SALES_AUTHOR_ROLES, Chair, Sec, DeptContrib, Viewer)`; predicates `can_view_sales_period(user)`, `can_edit_sales_period(user)`, `can_export_sales(user)`, `can_lock_snapshot(user)`; mixin `SalesEditRequiredMixin`.
- `apps/core/templatetags/permissions.py` — 4 new sales simple tags mirroring `_user_from_context` pattern.

**Navigation / Dashboard:**
- `templates/includes/sidebar.html` lines 52, 56, 60 — 3 href="#" → `url 'sales_updates:period_list'`, `sales_updates:group_dashboard`, `sales_updates:exports_page`.
- `templates/includes/offcanvas.html` lines 66, 70, + adjacent — same rewiring, preserving `data-bs-dismiss="offcanvas"`.
- `templates/dashboard/home.html` — append third KPI row of 4 cards (Current Period Revenue, Profit %, Deficit, Weeks Left); append right-side bottom "Current Reporting Period" card with cut-off date.
- `apps/core/views.py:home()` — lazy import `sales_dashboard_data(user)` with dict fallback (500 guard, same pattern as meetings/actions).

**Templates sales folder:**
- `templates/sales_updates/reportingperiod_list.html`, `reportingperiod_form.html`, `salesteam_list+form`, `salesgroup_list+form`, `group_period_detail.html` (TABS: Summary, Deliveries, Sales Orders, Weekly Commitments, Charts, Snapshots), `snapshot_detail.html`, `snapshot_printable.html`, `export_page.html`.
- `templates/sales_updates/_partials/currency_cell.html`, `target_vs_actual_chart.html` (pure SVG + Chart.js `<canvas data-targets=...>` progressive enhancement).

**Tests (comprehensive calculation tests, rule 53):**
- `tests/test_sales_models.py` — 9 models full_clean(), duplicate group-period IntegrityError, 4/5 week validations, Decimal vs float enforcement (test that assigning float raises error? no — django will coerce, use `type(value) is Decimal` in service assertions), snapshot lock propagation.
- `tests/test_sales_calculations.py` — ~25 tests: percentage_achieved (Decimal, rounds 2dp, division-safe when target=0 → 0 or 100 depending), deficit signed (negative behind / positive ahead), group subtotals 4 groups 1 period, team totals 3 groups, overall totals, monthly_average over 6mo, weekly_totals for 4-week and 5-week periods, currency_format PHP 3 decim, USD 2 decim, negatives class returns text-danger, is_snapshot_locked (meeting APPROVED=True/PUBLISHED=True→ locked; DRAFT→unlocked).
- `tests/test_sales_permissions.py` — Viewer can_view=True/can_edit=False; Dept Contributor can_view True; Sales Authors export True; only Sys/Mgmt can_lock.
- `tests/test_sales_exports.py` — Excel export 200 + contains header rows + correct number of data rows; StreamingHttpResponse content_type application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.
- `tests/test_sales_views.py` — list views 200, period detail 200, POST snapshot then meeting publish locks it.
- `tests/test_sales_pages.py` — smoke page GETs.

**Docs (Phase 5, rule 54 append):**
- `docs/permissions.md` — append "Sales Updates Domain Role Matrix" (6 roles × 6 actions: view, edit periods, edit targets/performance, lock snapshot, export, memberships edit).
- `docs/workflows.md` — append §11 Sales Reporting Workflow, §12 Weekly Commitments & Snapshots.
- NEW file `docs/sales_data_model.md` — 9 entities ER-style table, 4/5 week handling, weekly commitments as rows (no hardcoded 4 cols), calculation rules, snapshot lock propagation matrix.

## Implementation Steps (Dependency order)

1. Audit expansion check + new actions: verify AuditLog.action max_length fits ACTION_LOCK=4, ACTION_EXPORT=6 (yes). No migration needed unless changing field. Skip if no expansion; otherwise write actions + generate audit.0004 migration.
2. Write `apps/sales_updates/models.py` (9 models, constants, clean()s, @properties for percentage/deficit/locked).
3. `python manage.py makemigrations sales_updates` → `apps/sales_updates/migrations/0001_initial.py`; run `migrate`.
4. Write `apps/core/permissions.py` sales predicates + mixins; `apps/core/templatetags/permissions.py` 4 tags; Ruff clean.
5. Write `apps/sales_updates/services.py` — tested calculation layer, snapshot_take+lock propagation; `signals.py` + wire apps.py ready().
6. Write `apps/sales_updates/forms.py` + `templatetags/sales_formatting.py` filters.
7. Write `apps/sales_updates/views.py` + `urls.py` 16 named routes (UUID pk). Include Excel StreamingHttpResponse via openpyxl + Printable view.
8. Write `apps/sales_updates/admin.py` 9 registrations + read-only inlines.
9. Write templates directory: `templates/sales_updates/**/*.html` + partials.
10. Dashboard + navigation wires: sidebar/offcanvas 3 links each, home.html 4-card KPI row + Current Cutoff card, core/views.py home() lazy import.
11. Write tests (6 modules listed), run with pytest until cumulative ≥ 241 + 60+ sales tests = ~300 green.
12. Verification chain: `ruff check`, `ruff format --check`, `manage.py check`, `makemigrations --check`, full pytest.
13. Docs append (permissions.md, workflows.md, new sales_data_model.md).

## Dependencies and Considerations

- openpyxl already present (pyproject.toml pinned). Only use it inside ExcelExportView; guard import in services for CI (though it's installed).
- Decimal handling: every `models.DecimalField(max_digits=16, decimal_places=2, default=Decimal("0.00"))`. Pass `from decimal import Decimal, ROUND_HALF_UP` in all services; `.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)` at API edges. Division by zero: if target == 0 return Decimal("0.00") not raise (services return zero; UI shows "N/A" badge).
- Philippine peso formatting: PHP uses "₱ " prefix, 2 decimals, comma thousands; foreign USD/EUR/JPY use $/€/¥. No locale module (platform-dependent); implement `currency_format` pure Python string formatting inside templatetag filter + services.
- 4-week vs 5-week: `ReportingPeriod.weeks_count in {4, 5}` in clean(). `WeeklyCommitment.week_number` validated `1 <= week_number <= period.weeks_count`.
- Snapshot lock propagation: `GroupPerformanceSnapshot.is_locked` property reads `snapshot.meeting.status in NON_EDITABLE_STATUSES` (imported from meetings app lazy). Snapshots with no meeting link are editable.
- Phase 5 audit service: reuse existing `apps.audit.services.log_audit_event(record_type="sales_updates.groupperformancesnapshot", record=snapshot, action=ACTION_LOCK, ...)`.
- Wide-tables on mobile (rule 51): BS5 `.table-responsive` wrapper around every `<table>`. Horizontal scroll enabled automatically; include sticky first column via CSS `.sticky-col { position: sticky; left: 0; background: inherit; z-index: 2; }`.

## Validation

After plan execution:
1. `python manage.py check` → 0 issues.
2. `python manage.py makemigrations --check --dry-run` → No changes detected.
3. `ruff check apps config tests manage.py` → All passed.
4. `ruff format --check apps config tests manage.py` → 95+ files formatted.
5. `python -m pytest tests/ --tb=short` → ALL pass; cumulative count ≥ 301 (Phase4 final 243 + ≥60 new sales tests).
6. Manual smoke page GETs: `period_list`, `group_period_detail`, `export_page`, `snapshot_printable` → 200.
7. openpyxl response: `content_type` correct, file bytes xlsx magic `PK..` check in test.

## Risks

- **Risk:** 9 models with 20+ relationships produce auto-migration with ordering issues. Mitigation: write models in topological dependency order (Period → Team → Group → Membership → Target/Delivery/SalesOrder → Weekly → Snapshot).
- **Risk:** Snapshot lock references meetings NON_EDITABLE_STATUSES causing circular import between sales_updates + meetings. Mitigation: lazy `from apps.meetings.models import NON_EDITABLE_STATUSES` inside `is_snapshot_locked()` function body; never import at module top in sales services.
- **Risk:** WeeklyCommitment rows for 5-week periods cause UI bugs where templates expect 4 items in formsets. Mitigation: build `WeeklyCommitmentFormSet` dynamically using `formset_factory` with `extra = period.weeks_count`; never hardcode count in templates.
- **Risk:** `percentage_achieved / deficit` sign inconsistency (some callers expect deficit positive when under, others expect negative). Mitigation: document function contract via docstring and test 25+ edge cases explicitly (negative deficit = behind target; negative % delta = under 100).
- **Risk:** openpyxl writes fail in test due to missing binary wheels. Mitigation: pyproject.toml pins openpyxl>=3.1 and all previous test runs (Phase 4) succeeded. Guard view import with try/except returning HttpResponseServerError only as last-resort (not primary).
