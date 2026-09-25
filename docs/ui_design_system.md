# UI Design System

Canonical design system for the Management Meeting Minutes Intranet. Defines
design tokens, reusable components, responsive layout rules, accessibility
standards, and interaction patterns. All new UI work MUST conform to this
document; if something is missing, extend this spec first, then build.

---

## 1. Design Tokens

### 1.1 Color Palette

Semantic color names are preferred over raw hex values. Use Bootstrap 5 CSS
variables (`var(--bs-*)`) in custom CSS so dark-mode / theme overrides stay
consistent.

| Token            | Purpose                                              | Base value (light) |
|------------------|------------------------------------------------------|--------------------|
| `--primary-500`  | Primary brand, CTAs, active nav, links, focus ring   | `#0d6efd`          |
| `--primary-100`  | Subtle primary bg, icon wraps on KPI cards           | `#cfe2ff`          |
| `--success-500`  | Completed / Approved / Published statuses            | `#198754`          |
| `--warning-500`  | Draft / Overdue / Archived                           | `#ffc107`          |
| `--danger-500`   | Errors, overdue-highlight, destructive actions       | `#dc3545`          |
| `--info-500`     | In Progress / For Review statuses                    | `#0dcaf0`          |
| `--secondary-500`| Neutral / muted actions, disabled state              | `#6c757d`          |
| `--dark-900`     | Body text, headings                                  | `#212529`          |
| `--light-100`    | Page bg (`bg-light`), card hover off-state           | `#f8f9fa`          |
| `--surface`      | Card surface (`bg-white`)                            | `#ffffff`          |
| `--border-subtle`| Card / table borders                                 | `#dee2e6`          |

### 1.2 Typography

- **Base font stack**: `system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif` (Bootstrap default).
- **Base size**: 16px (`1rem`). Headings scale from `h1` (2.5rem / fw-bold) to `h6` (1rem / fw-semibold).
- **KPI numbers**: Use `.h2` + `.fw-bold` on dashboard stat cards so they read as numeric headlines regardless of surrounding text.
- **Mono / ref codes**: Wrap meeting references (`MRG-2026-0003`) and action-item refs in `.font-monospace.small`.
- **Line-height**: Body `1.5`, tight headings `1.2` via Bootstrap defaults.

### 1.3 Spacing Scale

Use Bootstrap spacing utilities (`p-*`, `m-*`, `g-*`) exclusively — do not
write ad-hoc `padding`/`margin` CSS unless the scale literally cannot
express it.

| Key    | Value | Typical use                                |
|--------|-------|--------------------------------------------|
| `*=1`  | 4px   | Icon-to-label inline gaps, badge margins   |
| `*=2`  | 8px   | Small card internal padding, form rows     |
| `*=3`  | 16px  | Standard card-body default, page gutter    |
| `*=4`  | 24px  | Section vertical spacing (`my-4`, `py-4`)  |
| `*=5`  | 48px  | Large page-heading block spacing           |

Grid gutters: use `.g-4` on dashboard KPI rows, `.g-3` on form `.row`s.

### 1.4 Radii

- Default cards / buttons: `.rounded-3` (8-12px) via Bootstrap utility.
- KPI icon wraps: `.rounded-3` (same as card radius, consistent feel).
- Badges / pills: `rounded-pill` (fully rounded ends).
- Focus rings: inherit button / input radius.

### 1.5 Shadows

- **Resting card**: `.shadow-sm` (consistent for `.card-stats` and list containers).
- **Hover (card-hover)**: raise shadow + translate 1px (defined in `app.css` `.card-hover`).
- **Floating elements** (toasts, modals, sticky submit bar): Bootstrap defaults ≥ shadow-sm with z-index ≥ 1050.

### 1.6 Z-Index Layers

| Layer               | z-index | Notes                                          |
|---------------------|---------|------------------------------------------------|
| Sticky table header | 10      | `.sticky-thead` inside scroll wrap             |
| Sticky submit bar   | 1020    | Above page content, below offcanvas/nav        |
| Navbar / sidebar    | 1030    | Bootstrap default                              |
| Fixed toast anchor  | 1090    | `base.html` toast container                    |
| Modals / dropdowns  | 1055+   | Bootstrap defaults; confirmation dialog =1055  |

### 1.7 Durations / Motion

- Toast autohide: success 4500ms, info 4500ms, warning 5500ms, error 6000ms.
- Card hover: `transition: all 150ms ease` (no distracting motion).
- Avoid auto-playing animation; any progress-bar / count-up must be
  purely decorative (screen readers see the text value, not the animation).

---

## 2. Components Library

### 2.1 Cards (`.card`)

All elevation surfaces use Bootstrap `.card` + one of the variants below.
Never stack `border` + custom shadows manually.

- **KPI cards (dashboard row)**: `.card.card-hover.card-stats.border-0.shadow-sm.h-100`.
  The `card-hover` class lifts the card on pointer hover (translate + shadow).
  Wrap each card in responsive column: `col-sm-12 col-md-6 col-lg-3` so the
  4-column grid collapses gracefully (see §3).
- **List/filter container card**: `.card.mb-4.shadow-sm` (no hover) with
  `.card-header` + `.card-body`. The meeting / action item filter panels
  use this with class `filter-form-card`.
- **Quick-shortcut cards**: link-wrapped bordered panels, `rounded-3` with
  a leading icon — no separate hover class needed (links get `:focus-visible`).

### 2.2 Badges (`.badge`) — Pill Variant Map

Use `rounded-pill` + semantic `-subtle` background variants for KPI headers
and status chips. Prefer the mapping in §2.4 for status badges specifically.

| Variant CSS class combo                | Semantics                        |
|----------------------------------------|----------------------------------|
| `.badge.rounded-pill.bg-primary-subtle.text-primary`   | Scheduled / Open / Active |
| `.badge.rounded-pill.bg-success-subtle.text-success`   | Approved / Published / Done |
| `.badge.rounded-pill.bg-warning-subtle.text-warning`   | Draft / Returned / Archived |
| `.badge.rounded-pill.bg-info-subtle.text-info`         | In Progress / For Review / Mine |
| `.badge.rounded-pill.bg-danger-subtle.text-danger`     | Overdue / High priority gap     |
| `.badge.rounded-pill.bg-secondary-subtle.text-secondary`| Neutral / NA / Counters       |

### 2.3 Progress Bars

- Wrap in a `role="progressbar"` container with `aria-label`, `aria-valuenow`,
  `aria-valuemin`, `aria-valuemax`. Never use the progress bar alone without
  a visible numeric label (or `.visually-hidden` equivalent) next to it.
- Inner bar: `<div class="progress" style="height: 6px;">` for KPI cards,
  `height: 10px` for table-cell progress (action-item list).
- Bar-color rules: `bg-success` at 100%, `bg-primary` 50–99%, `bg-secondary` <50%.

### 2.4 Status Badges — Model Mapping

Meeting / action-item status chips are partials (`templates/components/status_badge.html`
and the per-app `_partials/status_badges.html`). Map statuses via these
variants (Bootstrap `.bg-*` classes):

**Meeting status → badge class:**

| Status constant            | Badge class     | Label           |
|----------------------------|-----------------|-----------------|
| `STATUS_DRAFT`             | `bg-secondary`  | Draft           |
| `STATUS_OPEN_UPDATES`      | `bg-light.text-dark.border` | Open for updates |
| `STATUS_AGENDA_FINALIZED`  | `bg-info`       | Agenda Finalized|
| `STATUS_IN_PROGRESS`       | `bg-primary`    | In Progress     |
| `STATUS_FOR_REVIEW`        | `bg-warning.text-dark` | For Review |
| `STATUS_APPROVED`          | `bg-success`    | Approved        |
| `STATUS_PUBLISHED`         | `bg-success`    | Published       |
| `STATUS_RETURNED_FOR_CORRECTION` | `bg-danger` | Returned   |
| `STATUS_ARCHIVED`          | `bg-warning.subtle` | Archived |
| `STATUS_CLOSED`            | `bg-secondary`  | Closed          |

**Action item status → badge class:**

| Status constant        | Badge class     |
|------------------------|-----------------|
| `STATUS_OPEN`          | `bg-secondary`  |
| `STATUS_IN_PROGRESS`   | `bg-primary`    |
| `STATUS_BLOCKED`       | `bg-warning`    |
| `STATUS_UNDER_REVIEW`  | `bg-info`       |
| `STATUS_COMPLETED`     | `bg-success`    |
| `STATUS_CANCELLED`     | `bg-dark`       |
| `STATUS_REOPENED`      | `bg-primary`    |

### 2.5 Breadcrumbs

Use `templates/components/breadcrumbs.html`. It renders a `<nav aria-label="Breadcrumb">`
with `<ol>` and the last item `aria-current="page"`. Never hand-roll a
breadcrumb list.

### 2.6 Empty States

`templates/components/empty_state.html`. Standard pattern:

- Container class `empty-state` with `role="region"` + `aria-live="polite"`.
- Icon: `.bi bi-{icon}.fs-1.text-muted.opacity-50`.
- Title: `.h5.text-body-secondary.fw-medium`.
- Message: `.small.text-muted.mb-4.max-w-480px`.
- CTA button: `.btn.btn-primary.btn-sm` with leading `bi-plus-lg` icon when
  the user can create the missing item.

**When to use:** any list view with zero rows (meeting list, action-item list,
upcoming-meetings sidebar card, overdue table, reports dashboard).

### 2.7 Skeleton Loading

`templates/components/skeleton_rows.html` — 5 placeholder rows with animated
`.placeholder` strips. Render only for async-partial load states; the default
server-rendered pages should show real empty state, not skeletons.

### 2.8 Toasts

- Global mount: `<div class="toast-container position-fixed top-0 end-0 p-3">`
  at z-index 1090 in `base.html`.
- JS API: `window.IntranetUI.showToast(message, variant, delay)`.
- Mapping from Django messages → toasts (in `templates/includes/messages.html`):
  `success` → variant `success` (4500ms), `warning` → `warning` (5500ms),
  `error` → `danger` (6000ms), `info/debug` → `info` / `secondary` (4500ms).
- Every toast has `role="alert"`, `aria-live="assertive"`, `aria-atomic="true"`,
  and a `Close` button with `aria-label="Close"`.

### 2.9 Confirmation Dialogs

- Single shared modal `#confirmDialogModal` in
  `templates/includes/confirmation_modal.html` with
  `aria-labelledby="confirmDialogModalLabel"` + `aria-hidden="true"`.
- JS API: `window.IntranetUI.confirmDialog({title, message, confirmText, cancelText, onConfirm})`.
- Buttons: Cancel (`.btn-secondary`, dismisses) + Confirm (`.btn-danger` —
  destructive default; override to `.btn-primary` for non-destructive flows).
- Fallback for forms/links: `data-confirm` attribute (uses native `window.confirm`
  where the modal is not wired up — see `app.js`).

### 2.10 Alerts Containers (Validation Summaries)

Two entry points, both rendering `role="alert"` with an icon + heading:

1. **Non-field form errors**: `templates/includes/alerts_container.html`
   invoked with `{% include 'includes/alerts_container.html' with errors=form.non_field_errors %}`.
   Renders `.alert.alert-danger` id `#validation-summary`.
2. **Per-field errors**: same partial auto-renders individual `role="alert"`
   boxes for each `field.errors` keyed by label.

Both boxes MUST include `aria-labelledby` pointing to the inner `.alert-heading`
so assistive tech announces the headline.

---

## 3. Responsive Layout

Bootstrap 5 breakpoints. Design mobile-first; each breakpoint adds columns /
reveals chrome.

| Name | Min-width | Typical effect |
|------|-----------|----------------|
| `sm` | 576px     | Cards no longer full-bleed, padding widens. |
| `md` | 768px     | 2-column form grids, dashboard cards go 2-across. |
| `lg` | 992px     | Sidebar appears (see §3.1), dashboard cards 4-across. |
| `xl` | 1200px    | Wider max gutters on container-fluid. |
| `xxl`| 1400px    | Max container-fluid inner width via `xxl:` utilities. |

### 3.1 Sidebar — Fixed on `lg+`, Collapse Offcanvas on Mobile

- Desktop (`≥ lg`): `templates/includes/sidebar.html` renders with classes
  `d-none d-lg-flex`, fixed 280px width, scrollable, with a
  `.sidebar-collapse-btn` carrying `data-intranet-sidebar-collapse` +
  `aria-expanded="true"` for collapsible behavior.
- Mobile (`< lg`): sidebar is hidden; the same links are exposed via
  `templates/includes/offcanvas.html` (Bootstrap offcanvas drawer triggered
  from the top navbar). The offcanvas must have `aria-label` and a close button.

### 3.2 Dashboard Cards — 2 / 4 Columns

Every KPI card wrapper in `templates/dashboard/home.html` uses the exact
responsive class: `col-sm-12 col-md-6 col-lg-3`. This yields:

- `< md`: 1 column (full width).
- `md ≤ · < lg`: 2 columns.
- `≥ lg`: 4 columns.

Wrap the row in `<div class="row g-4 mb-4">` to apply consistent 24px gutters.

### 3.3 Forms — `md`-2 Grid

Meeting / user / action-item forms use the pattern:

```html
<div class="row g-3 form-grid">
  <div class="col-12 col-md-6">…field…</div>
  <div class="col-12">…full-width field (title, description)…</div>
</div>
```

Net effect: two columns only from `md` upward, single column on mobile. No
`col-md-4` / `col-md-8` splits wider than two columns unless the form has
a natural 3-way partition (date start/end/location).

### 3.4 Tables — Scroll + Card-Mobile Fallback

Every data table (meeting list, action-item list, sales sub-totals, report
tables):

1. Wrap in `<div class="scrollable-table-wrap" tabindex="0">` so keyboard
   users can scroll horizontally on narrow viewports.
2. Every `<th>` has `scope="col"` (or `scope="row"` for row headers).
3. Every `<td>` carries a `data-label="Header Text"` attribute matching the
   column header. CSS (`app.css`) uses this at `@media (max-width: 768px)`
   to convert each `<tr>` into a stacked card, rendering `data-label` as a
   pseudo-element label beside the cell value.
4. Table captions: `<caption class="visually-hidden">Table: Meetings</caption>`
   (required — screen-reader heading for the data table).
5. Desktop sticky header: `<thead class="sticky-thead table-light">` — stays
   pinned at top inside the scrollable wrap (z-index 10).

---

## 4. Accessibility — WCAG AA Target

Target: **WCAG 2.1 AA**. All new features must pass these checks before
merge.

### 4.1 Color Contrast

- Text-on-background: minimum 4.5:1 for body, 3:1 for large/ bold text ≥ 18pt.
  The Bootstrap `*-subtle` text variants are approved for secondary labels
  only — never use them for body copy.
- Status-only color cues (e.g. green "Published" badge) MUST also carry a
  text label; never rely on color alone to communicate state.
- Focus ring (see §4.2) is a distinct contrast change, not just a color shift.

### 4.2 Keyboard & Focus

- Every interactive element (button, link, input, `tabindex="0"` scroll
  container) MUST be reachable by Tab in a logical DOM order.
- Custom focus style: `outline: 2px solid var(--bs-primary, #0d6efd); outline-offset: 2px;`
  (2px primary-500 ring). Applied via `:focus-visible`, never `:focus` alone
  (avoids painting rings on mouse click).
- Skip-to-content link: `<a class="visually-hidden-focusable" href="#mainContent">Skip to main content</a>`
  (Bootstrap utility; becomes visible on first Tab).

### 4.3 ARIA Labels, Roles, and Live Regions

Mandatory patterns:

| Element / region                     | Required ARIA                               |
|--------------------------------------|---------------------------------------------|
| Main page shell                      | `<main>` element (HTML5 implicit landmark). |
| Sidebar / offcanvas navigation       | `aria-label="Main navigation"` or equivalent on `<nav>`. |
| Search / filter card                 | `aria-label="Filter Results"` on wrapping `<div class="card filter-form-card">`. |
| Table                                | `<caption class="visually-hidden">…</caption>`, `<th scope="col">`. |
| Progress bar container               | `role="progressbar"` + `aria-label` + value/min/max. |
| Empty state region                   | `role="region"` + `aria-live="polite"`.     |
| Validation summary / alert box       | `role="alert"` + `aria-labelledby` → inner heading id. |
| Pagination `<nav>`                   | `aria-label="Action item pagination"` / per-list-name (never generic "Pagination"). |
| Toast                                | `role="alert"` + `aria-live="assertive"` + `aria-atomic="true"`. |
| Status badge that carries only icon  | `aria-label` describing the state.          |
| Modal `<div class="modal fade">`     | `aria-labelledby` → title id + `aria-hidden="true"` when closed. |
| Toast close / modal close buttons    | `aria-label="Close"` on the X icon button.  |
| Sidebar collapse toggle              | `aria-expanded` (true/false as it toggles). |

### 4.4 Button Labels

- Every `<button>` and `<a role="button">` MUST have a human-readable label:
  either visible text, or an icon button with `aria-label` and visually
  hidden text (use `.visually-hidden` span as a belt-and-braces fallback).
- No `<button>` or link with only `href="#"` and no content.

### 4.5 Semantic Headings

- Exactly ONE `<h1>` per page. Dashboard uses `<h1 class="h3 fw-bold">` for
  the greeting; list pages use `<h1 class="h3 mb-1">` for the page title.
- Heading levels do not skip: `h1 → h2 → h3…`. KPI card numbers use `<h3>`
  inside cards whose section already sits under the page `<h1>`.
- Card sub-headings (Quick Shortcuts, Upcoming Meetings): `<h2 class="h6 fw-semibold mb-0">`
  inside `.card-header` — visually small but semantically a section header.

### 4.6 Table Captions

Required on every data `<table>`, even if visually hidden (use
`class="visually-hidden"` on the `<caption>`). Pattern:

```html
<caption class="visually-hidden">Table: {{ page_title|default:"Meetings" }}</caption>
```

---

## 5. Search + Filter Panels

All list pages (meetings, action items, users, sales groups, reporting
periods) share this contract:

1. **Container card** with `class="filter-form-card"` and
   `aria-label="Filter Results"`.
2. **Search input** with `<label class="visually-hidden" for="id_q">Search</label>`
   and `type="search"`, prefilled with `request.GET.q`.
3. **Status / dept / date filters**: each wrapped with its own
   `visually-hidden` label (form controls MUST have labels even when the
   placeholder suggests meaning).
4. **Filter button** (primary-outline) submits the GET form.
5. **Reset button** (secondary-outline) with href pointing to the bare list
   URL for this view, dropping ALL query params. The href must not carry
   `?q=` or `?page=` — it must be a clean reset. Examples:
   - Meeting list reset → `{% url 'meetings:meeting_list' %}?view={{ view_mode }}`
   - Action item list reset → `{% url 'action_items:actionitem_list' %}` (or
     `my`, `department`, `overdue` variants depending on the current tab).
6. **Preserve query through pagination**: every pagination `Previous` /
   `Next` link re-appends the current `request.GET` keys except `page`.
   Do not drop `?q=` on page change.

### 5.1 Pagination ARIA

Pagination controls live inside a `<nav>` with a descriptive `aria-label`
that names the list being paged (e.g. `aria-label="Action item pagination"`,
`aria-label="Meetings pagination"`). Size class `.pagination-lg` on the
inner `<ul>` gives a larger touch target for mobile.

---

## 6. Forms

### 6.1 Sticky Submit Bar

Every form with more than one fieldset (meeting create/edit, action-item
create/edit, user create/edit, dept submission) MUST include the sticky
submit pattern:

```html
<div class="sticky-submit-bar btn-primary-submit mt-3">
  <a class="btn btn-outline-secondary" href="…">Cancel</a>
  <button type="submit" class="btn btn-primary">Create / Save…</button>
</div>
```

CSS behavior (defined in `app.css`):
- Desktop: `position: sticky; bottom: 1rem;` — pinned above the page footer
  while the form scrolls.
- Mobile: falls back to `position: fixed; bottom: 0; left: 0; right: 0;`
  so the action row never scrolls off-screen on long forms. Z-index 1020.
- Never place `type="submit"` anywhere else unless it is a distinct
  sub-action (e.g. "Save order" on agenda reorder).

### 6.2 Validation Summaries (role=alert)

1. The first element inside the `<form>` (after `{% csrf_token %}`) renders
   `{% include 'includes/alerts_container.html' with errors=form.non_field_errors %}`
   — this is the top-level non-field error summary with `role="alert"` and
   `id="validation-summary"`.
2. The `<form>` tag carries `aria-describedby="validation-summary"` when
   non-field errors exist (conditional: `{% if form.non_field_errors %}…{% endif %}`).
3. Field-level invalid state: add `.is-invalid` class to the `<input>` /
   `<select>` / `<textarea>` and pair it with `.invalid-feedback` div
   immediately below. Use `forloop` of `field.errors` — not a single string.

### 6.3 Mobile Input Types

Use the native `type=…` attributes so mobile keyboards switch correctly:

| Semantic field            | HTML type      |
|---------------------------|----------------|
| Email                     | `type="email"` |
| Username / no spaces     | `type="text"`  |
| Search box                | `type="search"`|
| Phone                     | `type="tel"`   |
| URL (rare)                | `type="url"`   |
| Number (money/qty)       | `type="number"` with `step` / `min` / `max` as required |
| Date picker               | `type="date"`  |
| DateTime-local (meeting start/end) | `type="datetime-local"` or the Django split widget (`_0` date + `_1` time) |

---

## 7. Tables (repeat of §3.4 with extra rules)

Reinforcing from §3.4 with additional behavior rules:

### 7.1 Sticky `<thead>` on Desktop

`<thead class="sticky-thead table-light">`. CSS:

```css
.sticky-thead { position: sticky; top: 0; z-index: 10; }
```

Applied only inside `.scrollable-table-wrap` so it pins relative to the
scroll container, not the viewport.

### 7.2 Scrollable Wrap + `tabindex`

```html
<div class="scrollable-table-wrap" tabindex="0">
  <table class="table table-hover table-sm mb-0 align-middle">…</table>
</div>
```

The `tabindex="0"` puts the scroll region into the tab order so keyboard
users can arrow-key scroll horizontally on narrow screens. Give the wrap a
visible `:focus-visible` ring matching §4.2.

### 7.3 `@media (max-width: 768px)` Card-Fallback Rows

At viewports under 768px, each `<tr>` is re-layouted as a card. The CSS
rule in `app.css`:

```css
@media (max-width: 768px) {
  .scrollable-table-wrap table thead { display: none; }
  .scrollable-table-wrap table tbody tr {
    display: block; border: 1px solid #dee2e6; border-radius: .5rem;
    margin-bottom: .75rem; background: #fff; padding: .75rem 1rem;
  }
  .scrollable-table-wrap table tbody td {
    display: flex; justify-content: space-between; gap: 1rem;
    padding: .375rem 0; border: 0; text-align: right;
  }
  .scrollable-table-wrap table tbody td::before {
    content: attr(data-label); font-weight: 600; color: #6c757d;
    margin-right: auto; text-align: left;
  }
}
```

This is why every `<td>` MUST have a matching `data-label="Column Name"`
equal to the header text. Without it the mobile card rows have unlabeled
values, which is an AA failure.
