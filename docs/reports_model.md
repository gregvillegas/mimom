# Reports Model & Export Specification (Phase 7)

## §1 — Report × Format Coverage Grid

The Phase 7 reports subsystem ships **10 catalogued reports** × **4 export
formats**. Every cell below is covered by the corresponding view class in
`apps/reports/views.py` (base report class + format mixin composition at
dispatch time) and by at least one test in `tests/test_reports_generation.py`.

| #  | Report Name                         | Slug                           | HTML | PDF | Word | Excel |
|----|-------------------------------------|--------------------------------|:----:|:---:|:----:|:-----:|
|  1 | Management Meeting Minutes          | `management-meeting-minutes`   |  ✔   |  ✔  |  ✔   |   ✔   |
|  2 | Action Item Register                | `action-item-register`         |  ✔   |  ✔  |  ✔   |   ✔   |
|  3 | Open Action Items                   | `open-action-items`            |  ✔   |  ✔  |  ✔   |   ✔   |
|  4 | Overdue Action Items                | `overdue-action-items`         |  ✔   |  ✔  |  ✔   |   ✔   |
|  5 | Department Action Items             | `department-action-items`      |  ✔   |  ✔  |  ✔   |   ✔   |
|  6 | Meeting Readiness                   | `meeting-readiness`            |  ✔   |  ✔  |  ✔   |   ✔   |
|  7 | Sales Performance                   | `sales-performance`            |  ✔   |  ✔  |  ✔   |   ✔   |
|  8 | Weekly Commitments                  | `weekly-commitments`           |  ✔   |  ✔  |  ✔   |   ✔   |
|  9 | Meeting History                     | `meeting-history`              |  ✔   |  ✔  |  ✔   |   ✔   |
| 10 | Authorized Audit Report             | `authorized-audit-report`      |  ✔   |  ✔  |  ✔   |   ✔   |

**Total coverage:** 40/40 cells implemented. Each format is served from its
own dispatch view URL under the `/reports/` namespace.

---

## §2 — Filename Conventions

All exported files (HTML inline, PDF, Word DOCX, Excel XLSX) pass through
`apps/reports/services.py:meaningful_report_filename()` before being attached
to the HTTP response. The function guarantees a **stable, sortable,
filesystem-safe** name for every download.

### 2.1 — Name Structure

```
{prefix}_{reference}_{version}_{period}_{YYYYMMDD-HHMMSS}.{ext}
```

Parts are joined with `_` (underscore); empty optional parts are skipped so
the filename never has consecutive underscores. Every non-empty part is
scrubbed by `_FILENAME_BAD_CHARS` (see §2.3) before concatenation.

| Part              | Source                                                            | Required? |
|-------------------|-------------------------------------------------------------------|:---------:|
| `prefix`          | `_REPORT_SLUG_PREFIXES` map — stable prefix per report slug      |    Yes    |
| `reference`       | `meeting.reference` (e.g. `MRG-2026-0003`) or period.code        | Optional  |
| `version`         | `snapshot.version` formatted as `v1`, `v2`, …                    | Optional  |
| `period`          | `ReportingPeriod.name` or `ReportingPeriod.code`                 | Optional  |
| `YYYYMMDD-HHMMSS` | UTC timestamp, zero-padded, via `timezone.now().astimezone(UTC)` |    Yes    |
| `ext`             | `.html`, `.pdf`, `.docx`, `.xlsx` (always with leading dot)      |    Yes    |

### 2.2 — Prefix Map (`_REPORT_SLUG_PREFIXES`)

| Slug                           | Prefix                               |
|--------------------------------|--------------------------------------|
| `meeting_minutes`              | `MIMOM_MeetingMinutes`               |
| `action_item_register`         | `MIMOM_ActionItemRegister`           |
| `open_action_items`            | `MIMOM_OpenActionItems`              |
| `overdue_action_items`         | `MIMOM_OverdueActionItems`           |
| `department_action_items`      | `MIMOM_DeptActionItems`              |
| `meeting_readiness`            | `MIMOM_MeetingReadiness`             |
| `sales_performance`            | `MIMOM_SalesPerformance`             |
| `weekly_commitments`           | `MIMOM_WeeklyCommitments`            |
| `meeting_history`              | `MIMOM_MeetingHistory`               |
| `authorized_audit_report`      | `MIMOM_AuditReport`                  |
| *(unknown slug)*               | `MIMOM_{raw_slug}`                   |

### 2.3 — Forbidden Character Sanitization

Regex `_FILENAME_BAD_CHARS = re.compile(r"[\\/?*:|\"<>]")` — any match is
replaced with `_` (single underscore). These characters are forbidden on
Windows (`\ / : * ? " < > |`) and cause portability issues on POSIX filesystems
(`:` in HFS+, `?` in shells, `|` for pipes, etc.).

### 2.4 — Three Concrete Filename Examples

**Example 1: Management Meeting Minutes (Excel) — snapshot-linked meeting**

Input:
- `report_slug = "management_meeting_minutes"`
- `meeting.reference = "MRG-2026-0003"`
- `snapshot.version = 2`
- `timestamp = 2026-09-14 08:30:15 UTC`
- `suffix = ".xlsx"`

Output:
```
MIMOM_MeetingMinutes_MRG-2026-0003_v2_20260914-083015.xlsx
```

**Example 2: Sales Performance (PDF) — period-only, no snapshot**

Input:
- `report_slug = "sales_performance"`
- `period.name = "Q3 2026"`
- `timestamp = 2026-09-23 15:02:47 UTC`
- `suffix = ".pdf"`

Output:
```
MIMOM_SalesPerformance_Q3_2026_20260923-150247.pdf
```
*(Note: the space in "Q3 2026" is NOT a forbidden char, so it passes through
unchanged. Browser and OS file save dialogs preserve the space.)*

**Example 3: Authorized Audit Report (Word) — no context object, date range**

Input:
- `report_slug = "authorized_audit_report"`
- no meeting / snapshot / period (register-style report)
- `timestamp = 2026-09-24 00:05:01 UTC`
- `suffix = ".docx"`

Output:
```
MIMOM_AuditReport_20260924-000501.docx
```

---

## §3 — Sanitization Rules

Every **user-authored rich-text string** rendered in a report (HTML preview
or exported file) passes through `apps/reports/services.py:sanitize_html()`
before it reaches the template or document builder. The function returns a
`SafeString` so Django templates will not re-escape the allowlisted markup.

### 3.1 — Two-Phase Sanitization Pipeline

```
Input HTML string
    │
    ▼
Phase 1 — Dangerous-pattern strip (regex, order matters)
  1. Remove <script>…</script> blocks (DOTALL, case-insensitive)
  2. Remove <iframe> tags (opening or closing)
  3. Remove <style>…</style> blocks
  4. Remove <svg>…</svg> blocks (vector image injection vector)
  5. Strip on*="…" event handlers (double-quoted attr values)
  6. Strip on*='…' event handlers (single-quoted attr values)
  7. Strip srcdoc="…" iframe attribute (double-quoted)
  8. Strip srcdoc='…' iframe attribute (single-quoted)
  9. Strip "javascript:" URI scheme anywhere in text
    │
    ▼
Phase 2 — Allowlist + escape
  Tokenize remaining string against _ALLOWED_TAGS_RE.
  Allowed tags: <p>, <br>, <br/>, <br />,
                <strong>, <em>, <b>, <i>,
                <ul>, <ol>, <li> (opening + closing, any case).
  Text between matches → django.utils.html.escape() fully.
  Tag matches → passed through verbatim (no attribute allowlist —
                attributes are implicitly stripped because the regex
                only matches bare tag names with no attributes).
    │
    ▼
Fall-back guard
  If the final result is empty, return escape(strip_tags(input))
  so the caller always gets *something* safe rather than blank.
    │
    ▼
Output SafeString
```

### 3.2 — Allowlist Tag Set (Exact Regex)

```python
_ALLOWED_TAGS_RE = re.compile(
    r"</?(?:p|br\s*/?|strong|em|b|i|ul|ol|li)\s*/?>",
    re.IGNORECASE,
)
```

**Attributes are never preserved** — the regex only matches bare tag names
with optional whitespace and optional self-closing slash for `<br>`. Any
`<p class="…">`, `<a href="…">`, `<img src="…">`, `<div onload="…">`, etc.
is fully escaped to literal text.

### 3.3 — Sanitization Coverage

| Content Source                | Caller                                   | Sanitized? |
|-------------------------------|------------------------------------------|:----------:|
| Snapshot payload strings      | `minutes_payload()` via `_walk(node)`    |     ✔      |
| Agenda item discussion        | `minutes_payload()` section walk         |     ✔      |
| Agenda item decision          | `minutes_payload()` section walk         |     ✔      |
| Section summaries             | `minutes_payload()` section walk         |     ✔      |
| Action item descriptions      | Action item templates + Word/Excel rows  |     ✔*     |
| Submission text (7 sections)  | `minutes_payload()` → `departments` key  |     ✔      |
| Audit log `reason` field      | Authorized Audit Report templates        |     ✔*     |

\* = These fields originate from clean `CharField` / `TextField` values with
their own form-level sanitization; the report pipeline still runs
`sanitize_html` defensively so any past or future injection that bypassed
form clean() is caught at export time.

---

## §4 — Print CSS Coverage Specification

All printable HTML reports extend `templates/reports/base_printable.html`,
which embeds a self-contained `<style>` block (no external CSS — required
for PDF rendering pipelines that don't fetch linked resources). The table
below documents the Phase 7 required print features and maps each to its
CSS rule + line number in `base_printable.html`.

### 4.1 — Feature Coverage Table

| #  | Required Print Feature                                    | CSS Rule / Selector                                                                  | Line  | Status |
|----|------------------------------------------------------------|--------------------------------------------------------------------------------------|:-----:|:------:|
|  1 | **@page A4 landscape** with margins                        | `@page { size: A4 landscape; margin: 1.5cm 1.2cm 1.8cm 1.2cm; }`                    |  8–10 |   ✔    |
|  2 | **Page N of M** via CSS counters                           | `@bottom-right { content: "Page " counter(page) " of " counter(pages); … }` + `html, body { counter-reset: pages; }` | 11–16 + 24 | ✔ |
|  3 | **Repeat `<thead>` on every page**                         | `thead { display: table-header-group; }` + `tfoot { display: table-footer-group; }`  |  64–65|   ✔    |
|  4 | **Avoid page break inside `.action-row`**                  | `tbody tr.action-row { page-break-inside: avoid; }`                                  |   80  |   ✔    |
|  5 | **Right-align money & numeric columns**                    | `.money, .num { text-align: right; white-space: nowrap; font-variant-numeric: tabular-nums; }` | 86–90 | ✔ |
|  6 | **Negative values: red color + parens format**             | `.negative { color: #9b2c2c; }` (HTML) + Excel writer `number_format='…(#,##0.00)…'` + font red | 91 | ✔ |
|  7 | **Confidentiality notice in footer margin-box**            | `@bottom-left { content: "CONFIDENTIAL"; font-size: 8pt; color: #888; }`             | 17–22 |   ✔    |
|  8 | **Page header with company + reference**                   | `.doc-header` block: `.company` (bold name) + `.meta` spans (Ref / Meeting / Cut-off / Status / Version) | 92–116 | ✔ |
|  9 | **Headings avoid page break after**                        | `h1, h2, h3, h4 { page-break-after: avoid; }`                                         |  34–38|   ✔    |
| 10 | **Zebra striping for readability**                          | `tbody tr:nth-child(even) td { background-color: #f5f7fb; }`                          |   79  |   ✔    |
| 11 | **`@media print` hide no-print elements**                  | `@media print { .no-print { display: none !important; } }`                            | 194–196|   ✔    |
| 12 | **Confidential notice block (in-page)**                    | `.confidential-notice` class — pink background + border, 9pt text                    | 124–131|   ✔    |
| 13 | **Approval signature block**                               | `.approval-block .sig-col` with flex row + top-border separator lines                | 132–146|   ✔    |
| 14 | **Footer branding + generated timestamp**                  | `.doc-footer` flex row: company · site on left, `{% now %}` on right                 | 117–123 + 237–240 | ✔ |

### 4.2 — @page Margin Box Layout

The CSS Paged Media specification defines 16 margin boxes around each page
rectangle. Phase 7 uses two of them:

```
┌─────────────────────────────────────────────────────────────────┐
│ @top-left        @top-center        @top-right                   │  (unused in Phase 7)
│                                                                 │
│                      PRINTABLE AREA                             │
│              (starts 1.5cm from top edge)                       │
│                                                                 │
│                                                                 │
│ @bottom-left              @bottom-center     @bottom-right      │
│ [CONFIDENTIAL]            (unused)         [Page 7 of 12]       │
└─────────────────────────────────────────────────────────────────┘
     1.2cm left margin                     1.2cm right margin
                    1.8cm bottom margin (above footer boxes)
```

Margin boxes are rendered by **paged-media capable** user agents:
Chrome/Edge print dialog, WeasyPrint, PrinceXML, wkhtmltopdf, LibreOffice
print. Screen (non-print) rendering ignores them entirely, which is why the
in-page `.doc-footer` + `.page-counter` elements also exist as a fallback.

### 4.3 — Money & Negative Formatting Contract

The combined CSS + template + Excel writer convention for financial cells:

| Context       | Positive Example         | Negative Example                                     |
|---------------|--------------------------|------------------------------------------------------|
| HTML/CSS      | `₱1,234.56` (right-aligned) | `(₱1,234.56)` with `.negative` class → `#9b2c2c` red  |
| Excel (XLSX)  | `₱ 1,234.56` tabular-num  | `₱ (1,234.56)` — red font + accounting format         |
| Word (DOCX)   | `₱1,234.56` right-aligned | `-₱1,234.56` with colored text or `(₱1,234.56)`       |

Money columns in every report template use `<td class="money">`, and the
Excel writer receives a `money_cols = frozenset({col_indices, …})` per sheet
so formatting is applied at write-time, not post-hoc.
