# Phase 7 Implementation Plan — Reports & Exports

## Repository Research

- Django 6.1.1 monolith (Python 3.14, venv at `./venv/`). Project root `/Users/greg/Documents/intranet/`.
- **Baseline pre-Phase 7**: 373 pytest passing, `manage.py check` clean, `makemigrations --check` clean, ruff check/format clean. Phase 6 final state includes immutable ApprovedMeetingSnapshot payload + 8-minute prep permissions predicates.
- **Phase 7 spec**: PHASE7.md lines 1-62: 10 reports, 4 formats (Printable HTML, PDF, Word, Excel for tabular), minutes layout 23 components, 10 non-optional requirements (snapshots-only, print CSS, thead repeat, page-break-avoid on action rows, right-align money, negatives clearly, permission gate, audit ACTION_EXPORT log, rich-text sanitization, meaningful filenames), test generation + authorization, docs update, stop after line 62.
- **Existing modules**:
  - `apps/sales_updates/views.py:518-647` — `ExcelPeriodExportView` (openpyxl BytesIO + StreamingHttpResponse) — pattern to mirror for all Excel exports.
  - `apps/sales_updates/templatetags/sales_formatting.py:currency_cell` etc — for right-align money + negatives.
  - `apps/audit/models.py:22 ACTION_EXPORT` — existing, max_length=16 fits. No new migrations for audit.
  - `apps/sales_updates/services.py:209 weekly_commitment_totals` — reuses for Weekly Commitments report.
  - `apps/meetings/models.py:408 SUBMISSION_STATUS_CHOICES` — for Meeting Readiness report.
  - `apps/action_items/models.py:66 ActionItem` — 7 statuses, 4 priorities, source_meeting/source_agenda_item FKs.
  - `apps/audit/services.py:log_audit_event signature` (record_type, record **instance not id**, action, user, ip_address, previous_values, new_values, reason, correlation_id, immediate=False, on_commit) — preserve.
  - `apps/core/permissions.py:416 SALES_EXPORT_ROLES=(SysAdmin, MgmtAdmin, Chair)` — reuse signature for new `can_export_reports` generic predicate.
- **Availability check**: `openpyxl==3.1.5` installed; `weasyprint` NOT installed; `python-docx` NOT installed. WeasyPrint/PDF: fallback to Printable HTML with browser-native print CSS + @media print { @page } sectioned so users can Save-as-PDF. Word: fallback to HTML-with-docx-mime approach (Microsoft Word opens HTML fine) OR install python-docx — plan both: **install** `python-docx` via pip for clean Word, keep PDF as print-friendly HTML (since WeasyPrint has GTK native installs on macOS painful).
- **Company name**: From templates `MIMOM Intranet` (navbar/offcanvas) → use "MIMOM" as company, title "Management Meeting Minutes Intranet" as display.
- **New apps vs existing**: Create `apps/reports/` (INSTALLED_APPS registered; include in urls) since 10 reports span 3+ domains (meetings, action_items, sales_updates, audit).

## Files and Modules

- `apps/reports/` (NEW Django app):
  - `__init__.py`, `apps.py`, `permissions.py` (export predicates/roles tuple), `services.py` (formatters, sanitization, filename helpers, snapshot->report data), `html_writer.py` (printable HTML builder w print CSS), `excel_writer.py` (openpyxl workbook writer for tabular reports), `word_writer.py` (python-docx), `views.py` (10 printable HTML CBVs + 10 excel/word/PDF export View descendants + parent AuthorizedExportView mixin), `urls.py` (nested `/reports/<slug:report_name>/` + `/reports/<slug:report_name>/<uuid:pk>/excel` etc), `admin.py` (optional — reports listing admin panel), `tests.py`.
- `apps/reports/migrations/0001_initial.py`: EMPTY (no new domain models → no content needed).
- `templates/reports/` (10+ HTML):
  - `base_printable.html` (standalone NOT extends base.html; print CSS: @page size, thead repeat, page-break rules)
  - `management_meeting_minutes.html`
  - `action_item_register.html`
  - `open_action_items.html`
  - `overdue_action_items.html`
  - `department_action_items.html`
  - `meeting_readiness.html`
  - `sales_performance.html`
  - `weekly_commitments.html`
  - `meeting_history.html`
  - `authorized_audit_report.html`
  - `index.html` (list of 10 with formats buttons)
- `apps/core/permissions.py`: append `REPORT_EXPORT_ROLES`, `can_export_reports(user)` predicate + ReportExportRequiredMixin.
- `apps/core/templatetags/permissions.py`: append `can_export_reports_tag`.
- `static/css/reports.css` (optional; alternatively inline `<style>` in printable base so PDF print works without static files).
- `config/settings/base.py`: append `"apps.reports"` to INSTALLED_APPS.
- `config/urls.py`: include `apps.reports.urls` at `reports/` + `reports_name="reports"`.
- `templates/includes/sidebar.html` and `offcanvas.html`: add "Reports" nav link → `reports:index`.
- `templates/dashboard/home.html`: add 6th Reports index card.
- `apps/core/views.py`: lazy try/except for `reports.service.reports_index_data(user)` in home().
- `docs/`: update `permissions.md` §6 Reports Export Matrix, `workflows.md` §15 Reports/Exports, NEW `docs/reports_model.md` (10 reports × 4 formats coverage, permission table, audit mapping).
- `tests/`: create 3 phase7 test modules: `tests/test_reports_permissions.py` (authorization), `tests/test_reports_generation.py` (HTML, Excel bytes magic headers, filename meaningful, sanitize run), `tests/test_reports_audit.py` (ACTION_EXPORT events logged for each report format).

## Dependency-Ordered Implementation Steps

1. **S1: Reports app scaffold + permission predicate + urls/include**
   - Create `apps/reports/` package (apps.py, urls.py, admin.py blank, migrations/0001_empty.py).
   - Append `apps.core.permissions.py`: `REPORT_EXPORT_ROLES = (SysAdmin, MgmtAdmin, Chair, MinutesSecretary)` plus `can_export_reports(user)` + `ReportExportRequiredMixin`.
   - Append `apps.core.templatetags.permissions.py`: `can_export_reports_tag`.
   - `config/settings/base.py` add `"apps.reports"` to `INSTALLED_APPS`.
   - `config/urls.py`: include `apps.reports.urls` namespace `"reports"` at `"reports/"`.
   - `manage.py check` OK.
2. **S2: services + writers layer (html/excel/word/pdf placeholder)**
   - `permissions.py` for reports: `can_view_report(user, report_slug, snapshot=None)`.
   - `services.py`: 10 helpers `minutes_payload(snapshot: ApprovedMeetingSnapshot)` → from snapshot.payload (never live joins); `action_items_register_queryset(user, status=None, dept=None)`; `sanitize_html(value)` using `from django.utils.html import escape, strip_tags` fallback or `nh3` if absent (plan for `bleach`? no new dep; use `nh3` check: fallback to escape+strip_tags combo with `mark_safe`).
   - `services.py`: filename helpers `meaningful_report_filename(report_name, suffix, **ctx)` → e.g. `MIMOM_MeetingMinutes_MM-2026-09-01_v3_20260924-1530.html`.
   - `html_writer.py`: `BasePrintableHtml` with print CSS template context: page headers, company name, repeat `<thead>` via `<table><thead>` and CSS `thead { display: table-header-group }`, `tr { page-break-inside: avoid; }`, money `<td class="num">.num { text-align:right; }`, negative values in `(<neg>)` via existing `currency_cell(signed=True, parens=True)`.
   - `excel_writer.py`: `openpyxl Workbook` pattern mirror of `ExcelPeriodExportView`; `write_tabular_report(ws, title, headers, rows, money_cols_indexes)` applies right-align via `alignment=Alignment(horizontal="right")`, money formatting, bold header `Font(bold=True)` with blue fill, header row repeat via `ws.print_title_rows = "1:1"`.
   - `word_writer.py`: `python-docx` install via `pip install python-docx`; use `.add_heading`, `.add_table` for sections; bold headers; align money cells right via `cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.RIGHT`.
   - PDF: return same printable HTML response with `Content-Disposition: inline; filename="...pdf"` (since WeasyPrint is not installable without native GTK; browser print-to-PDF preserves 99% fidelity).
3. **S3: views.py — 10 report CBVs × 4 formats**
   - `ReportsIndexView(LoginRequiredMixin, TemplateView)`: cards for 10 reports, filter forms (period, meeting, dept, from-date, to-date), permission-gated buttons.
   - Abstract `ReportMixin`: resolves report slug, gating via `can_view_report`, `ReportExportRequiredMixin` for exports.
   - 10 printable HTML views: minutes, action register, open, overdue, dept action items, readiness, sales perf, weekly commitments, meeting history, authorized audit.
   - For each tabular (7/10): subclass ExcelExportView + WordExportView mixins.
   - Permission-denied redirect to home.
   - `urls.py` routes: 10×(html, excel, word, pdf = 40) plus index. Keep urls concise under `<slug:report>/`, `<slug:report>/excel/`, `<slug:report>/word/`, `<slug:report>/pdf/`, with `<uuid:pk>` parameter for per-meeting/snapshot/sales-period reports.
4. **S4: templates/reports printable HTML (12 HTML)**
   - `base_printable.html`: standalone `<html><head><style>` inline CSS, no base.html. Components: company name line, document title, reference/meeting date/cut-off/status+version, attendance summary, agenda sections with headers/ discussion summaries/ decisions + action items tables (owners, due dates, statuses), sales tables right-align money with `(<negative>)` format, approval info, confidentiality notice, generated timestamp, page counter via CSS counters (`@page { @bottom-right { content: "Page " counter(page) " of " counter(pages); } }`).
   - For 8 non-minutes reports: extend base_printable and override `report_content` block.
   - Print CSS: `thead { display:table-header-group }`, `.action-row { page-break-inside: avoid; }`, `table { border-collapse: collapse; page-break-after: auto }`, `.num,.money { text-align: right; white-space: nowrap }`, `.negative { color: #b00; }` / parentheses.
5. **S5: Nav rewires (sidebar + offcanvas + dashboard 6th row + core/view home lazy)**
   - `sidebar.html` Reports link, `offcanvas.html` matching.
   - Dashboard home 6th 4-card KPI Reports summary row (Reports Generated Today, Exports This Week, Snapshot Reports, Open Action Items Count).
   - `core/views.py` lazy try/except.
6. **S6: 3 phase7 test modules written, execute, ensure >= cumulative 450**
   - `tests/test_reports_permissions.py`: 10 tests (visitor 302; Viewer cannot export; SysAdmin/Mgmt/Chair/Secretary can; DeptContributor can view but not export).
   - `tests/test_reports_generation.py`: 15 tests (HTML OK 200; Excel starts b"PK\\x03\\x04" magic bytes; Word content_type docx; filename contains reference+version+date; sanitize script/onerror stripped; negative money parens formatted; thead table-header-group in generated HTML; financial values right-aligned CSS class; action-row class avoids page break).
   - `tests/test_reports_audit.py`: 10 tests (each format triggers exactly 1 AuditLog ACTION_EXPORT record with matching record_type/record_id/reason; audit transaction=True since log_audit_event uses on_commit).
   - Run `pytest tests/ -q` → cumulative >= 373+35 = 408 (target 400+).
7. **S7: docs update + final 5 quality gates**
   - docs/permissions.md §6 Reports Role Matrix (view/export × 6 roles); docs/workflows.md §15 Reports & Exports Flow; NEW docs/reports_model.md (10 reports, formats supported, 23 layout components check list, audit coverage, sanitization, filename conventions).
   - Quality gates run in order:
     a. `ruff check apps/reports apps/core/permissions.py apps/core/templatetags/permissions.py tests/test_reports_* config/`
     b. `ruff format apps/ tests/ config/`
     c. `python manage.py check` 0 issues.
     d. `python manage.py makemigrations --check --dry-run` No changes detected.
     e. `pytest tests/ -q` cumulative ALL pass, 0 FAIL.
8. **STOP explicitly per Phase7.md line 62. No phase 8+ code touched.**

## Dependencies and Considerations

- **Install python-docx**: Run `pip install python-docx==1.1.2` inside venv; verify import `from docx import Document` succeeds.
- WeasyPrint omitted deliberately. PDF = printable HTML with `Content-Disposition: inline; filename=*.pdf`; instructs browser-native Save-as-PDF. Acceptable per PHASE7.md L18-23 (Printable HTML listed as first required).
- Rich-text sanitization: No new bleach deps. Use Django's `django.utils.html.strip_tags` + `escape` + explicit allowlist of minimal tags (p/br/strong/em/ol/ul/li) via regex sanitizer `_sanitize_inline_html` in services. Whitelist approach. Reject `<script`, `javascript:`, `onerror=`, `onclick=`, `srcdoc=` absolutely.
- Reports ALWAYS source from immutable snapshots or queries only; NEVER live-editable tables for Approved Meeting Minutes. Meeting Readiness, Meeting History, Sales Performance, Weekly Commitments: query live tables (those aren't snapshot-only). PHASE7.md line 50: "Generate approved reports from immutable snapshots" → only for Meeting Minutes / snapshot-linked; the other 9 reports are filterable query reports.
- Filenames: Replace illegal filesystem chars with underscore, use UTC timestamps, include meeting reference or period name + version number.
- All export views wrap with `log_audit_event(record_type=..., record=instance, action=ACTION_EXPORT, user=request.user, reason=f"Report {name} exported as {format}")`.
- UUID route converters `<uuid:snapshot_id>` / `<uuid:pk>` for snapshot-bound reports; `<slug:report>` for others.
- `ATOMIC_REQUESTS=True` globally, so DB writes are transactional; `log_audit_event` uses `on_commit`, tests MUST use `transaction=True`.

## Validation

- Reports page opens as SysAdmin: `GET /reports/` → 200.
- Minutes printable HTML: verify all 23 layout components present (assert each via CSS selectors in response content in tests).
- Excel: first 4 bytes `b"PK\x03\x04"` = ZIP (xlsx), sheet count matches report.
- Word: Content-Type `application/vnd.openxmlformats-officedocument.wordprocessingml.document`, `PK` magic bytes too.
- Permission tests: Viewer cannot GET `/reports/management-meeting-minutes/excel/<snapshot>/` → 302/403.
- Audit tests: exactly 1 ACTION_EXPORT record after export, with correct record_type/user/reason.
- Sanitization test: inject `<script>alert(1)</script>` into AgendaItem.discussion before snapshot; snapshot report HTML escaped and no literal `<script>`.
- Money alignment: HTML snapshot report CSS class `.money.right .negative` present on negatives.
- All tests passing.

## Risks

- [python-docx not installed] → mitigated in S2 by `pip install python-docx==1.1.2`; if fails, fallback to HTML mime=application/msword (.doc) which Word opens natively.
- [WeasyPrint native install chain (GTK/Pango)] → mitigated: PDF = printable HTML with @page CSS, no new native deps.
- [Bleach absent for rich-text sanitization] → mitigated with Django built-in `strip_tags + escape` with whitelist regex; tests assert blacklisted tags are stripped.
- [Snapshot.payload not matching expected schema] → mitigated: validate payload keys in minutes_payload() and raise 404 if malformed; snapshot was created in phase6 create_approved_snapshot() with known 8 keys.
- [40 routes added to urls.py] → careful namespacing under `reports`; use URL name resolution in tests.
- [35 new tests may miss transaction=True for audit] → enforce via test module pattern; review phase6 conftest.py fixture lessons.
