# Phase 8 Plan — Responsive UI/UX Refinement

## 1. Scope & Goals

**Baseline (after org-seed R0–R6 complete):**
- 438/438 pytest passing (`tests/` cumulative), `ruff --select=E,F,W,UP` clean.
- PHASE7 end → Phase8-prep org wiring (sidebar, depts/positions/teams, seed, permissions) done.

**Deliverables (per [PHASE8.md](instructions/PHASE8.md)):**
Per spec L1–52 — build **consistent Bootstrap 5 design system**; keep business logic unchanged; end-to-end responsive mobile + accessibility compliance; add standard components for nav, cards, badges, progress, alerts, toasts, breadcrumbs, empty/loading, confirmation; responsive forms/tables; sticky headers + sticky submit on long forms; mobile card alternatives; search/filter/pagination panels; validation summaries.

---

## 2. Business-Logic Change Rule (Preservation

**Strict invariant (PHASE8.md L51):** "Do not change working business logic unless required to fix a UI issue." → zero code in the following modules unless wrapped inside `{% block %}`, CSS class attribute, `aria-*`, data-*, or template `<script type="application/json">` + JS behavior only:
- ❌ CBV querysets / form save logic / audit calls / permissions predicates → NO edits
- ✅ Only: Templates (HTML), static CSS/JS files and tags, base.html `<head>` CSS; possibly add new template-tags returning CSS-class builder helpers returning `|yesno:","` strings only.

---

## 3. Work Packages

### WP1 — Design System Library & Tokens (CSS)

Create unified token layer on top of Bootstrap utilities. Keep Bootstrap 5.3 default values. `static/css/app.css` existing, add `static/css/design-tokens.css` new OR append to `app.css`:
1. CSS custom properties (`:root`) for: brand colors (info/warn/success/danger primary secondary neutral 50,100,200,500,700,900), font family sans/mono, spacing 2/4/8/12/16/24/32, radii pill/card/btn, elevation shadows 0→5, durations ms 150/250/500, z-index values (nav 1020, toast 1090, modal 1050, offcanvas 1050), breakpoints sm/md/lg/xl/xxl.
2. Component utility: `.card-hover` `.card-stats` `.badge-pill` `.chip` `.empty-state` `.loading-skeleton` `.sticky-top-table` `.sticky-submit-bar` `.sr-visible-focus` `.scrollable-table-wrap` `.card-table-mobile`.
3. Ensure WebAIM AAA on focus ring; semantic; contrast ratios check at least 4.5:1 body; 3:1 large text.

### WP2 — Responsive Navigation (sidebar + offcanvas + collapsible)
1. `templates/base.html**: desktop `lg`+ keeps sidebar fixed left; `<lg` collapses sidebar completely and shows only offcanvas hamburger.
2. `sidebar.html`: collapse/expand toggle icon button top; nested sub-menus (ACTIONS/REPORTS/ORGANIZATION/ADMIN) `aria-expanded` with chevron; smooth slide; currently selected link background, state `active` styling; `data-bs-toggle="collapse"` on groups;
3. offcanvas mobile nav accordion expands from top `aria-controls mobile burger menu; `data-offcanvas-search-flyout` to close offcanvas after anchor click.
4. Add `IntersectionObserver`-style scrollspy on sidebar; breadcrumbs show current parent section.

### WP3 — Dashboard home (`dashboard/home.html`)
1. Existing 4×kpi-row + reports row → mobile: 1-col up to `sm; md 2-col; lg 4-col. Card shadow 0.3s box-shadow-hover; active numbers use `data-count`;
2. KPI labels on small display numbers; big primary progress ring border
3. Add charts wrap flex order; quick shortcuts grid rows 1-col; status badges.

### WP4 — Standard Components
1. **Badges** all status types: Meeting statuses badges pill color variants; accessible `<span class="badge"> role=status> + text sr `sr-only aria-live.
2. **Progress indicators**  ** meetings progress bar** Progress** progress-striped**.
3. Alerts —** ** alerts accessible dismissible, close button aria; `.toast-container` position top-right (fixed top-right; toasts fire `data-delay  **  confirmation dialogs 2) bootbox modal confirm dialog confirmation component (templates/includes/confirmation_modal.html`
4. **Breadcrumbs** — standardized at top every non-modal; last page page-title wrapper; component `{% include %}` reusable component.
5. **Empty states** — for each list page custom illustrations, zero results; no items; create first; illustrations glyph icons; link.
6. **Loading states / skeleton** — table rows shimmer; forms show spinner while fetching data.

### WP5 — Forms / Responsive Forms long sticky submit bar
1. Every Model forms: `form-control`, `form-select,` `input-group` `d-flex` layout; `col-md-6` row cols; mobile full width labels.
2. Focus rings focus state.
3. Sticky `.sticky-submit-bar` bottom (mobile/desktop fixed bottom save Cancel buttons; `form-actions`.
4. Accessible validation error summaries Django form `{{form.non_field_errors}}` alert-danger at the top; each field `form-control is-invalid feedback div.invalid-feedback,

### WP6 — Responsive tables + alternatives
1. `.table-wrap` overflow mobile horizontal scroll container sticky first cols; `.sticky-th-desktop top table header; desktop `<thead>` sticky position top 0 within card header.
2. Mobile card alterative `.mobile-cards` CSS classes `@media (max-width: 768px)`; tables → render rows cards; each `<td data-label>` header name pseudo content:`:before`.
3. Pagination `.page-item `.disabled aria-label pagination buttons sizes md lg.

### WP7 — Search filter panels
1. Standard filter form every list view search `.search card,
2. Search/filter reset button; clear filter; preserved query params back.

### WP8 — Mobile rules checklist spec (PHASE8.md L30-L39
Feature parity; important actions visible; tables scroll or cards; touch controls sized; hover interactions; suitable types; dashboard cards column 2 max per row on mobile.

### WP9 — Accessibility (WCAG AA+)
Keyboard; focus; labels; headings H1–H6 (no skip); table `<caption>` or aria-labelledby; meaningful button ("Cancel" "Delete" etc., not icon-only; status icons sr color communicate + text; 4.5:1 contrast.

### WP10 — Tests + Docs + Quality gates
Tests module: `tests/test_ui_components.py` (5 tests rendering list_pages; buttons readable accessible, accessible aria attrs; responsive rendering (contains `aria-label=`; `toast-container`, `focus-visible`; pages visited (not hover-only;
Docs update: docs/ui_design_system.md; L20 design system tokens components library.
Quality chain order: ruff, check, makemigrations check dry pytest (all; 3.
---

## 4. Deliverable 6. Acceptance criteria checklist
✅ [ ] 438+ passing; test pytest
✅ [ ] ruff `ruff E/F/W/UP green;
✅ [ ] pages list, meetings/sales_updates/accounts/reports/ users/department list/ + create /detail. responsive; sidebar lg and mobile.
✅ [ ] No desktop-only required. Accessibility checklist all pass color.
