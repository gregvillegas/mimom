# Phase 6: Minutes Preparation, Review, Approval, and Publishing — Implementation Plan

## Repository Research

### Current Baseline (Phases 1-5 complete)
- **Cumulative pytest**: 302 passed / 0 FAIL (1 warning only: Deprecated EMAIL_BACKEND)
- **Quality gates all green**: ruff check/format (104 files) clean; `django check` 0 issues; `makemigrations --check` No changes detected.
- **Audit actions expanded**: 16 total (CREATE/UPDATE/DELETE/APPROVE/PUBLISH/LOGIN/LOGOUT/ASSIGN/ROLE/TRANSITION/ARCHIVE/COMPLETE/REOPEN/CARRY_FORWARD/LOCK/EXPORT). max_length=16 accommodates everything.
- **Permission roles**: 6 groups (SysAdmin / MgmtAdmin / Chair / Secretary / DeptContributor / Viewer) seeded via `seed_roles`. Sales predicates templatetag pattern in use.
- **Meetings domain already ships 10 statuses**: DRAFT → OPEN_UPDATES → AGENDA_FINALIZED → IN_PROGRESS → FOR_REVIEW → RETURNED → APPROVED → PUBLISHED → CLOSED → ARCHIVED. Valid transitions graph, `REQUIRE_ADMIN_TRANSITIONS={RETURNED, ARCHIVED}`, `REQUIRE_REASON_TRANSITIONS={(FOR_REVIEW/APPROVED/PUBLISHED) → RETURNED}`. `transition_meeting(service)` uses `@atomic select_for_update` + creates MeetingStatusHistory rows + fires log_audit_event with PUBLISH→ACTION_PUBLISH, APPROVED→ACTION_APPROVE, ARCHIVED→ACTION_ARCHIVE, else→TRANSITION.
- **NON_EDITABLE_STATUSES = {APPROVED, PUBLISHED, CLOSED, ARCHIVED}**: propagates to sales GroupPerformanceSnapshot via lazy import. `Meeting.is_editable` property already uses it.
- **AgendaItem already carries discussion + decision + owner + dept fields** (Phase 3 scaffold). `MeetingStatusHistory` = version history of transitions; but Phase 6 needs a **deeper immutable snapshot** (not just status changes).
- **Missing domain objects today**:
  - No per-department tracker for submission state of agenda sections — the prep dashboard (col 1-10: dept / contributor / required section / state / last update / submitted by / timestamp / missing info / management remarks) has no home.
  - No `ApprovedMeetingSnapshot` JSON-denormalized frozen copy of all of meeting metadata + attendance + agenda sections + discussions + decisions + action_items + sales-performance + approval metadata + version.
  - No `ActionItemLink` bridge (AgendaItem → ActionItem) to back "create action item during minutes editing" without FK-cycling (ActionItem has FK source_agenda_item already — that column is `null=True` currently; a link model records the minute-edge creation timestamp for snapshotting).
  - No `MinutesSectionSpec` (what sections are REQUIRED for this meeting type — powers the "missing information" dashboard cell and pre-submit validation summary).
- **Missing routes**: Today meetings have 13 routes (CRUD + transition + attendance + carry forward + agenda items CRUD/order + attachments). Missing: prep_dashboard, dept_submission state, structured minutes editor (agenda item discussion/decision inline edit with action item sub-form), meeting preview, validation summary, submit_for_review, return_for_correction (with comments), resubmit, approve, publish, close, authorized reopen, version history list, snapshot detail view.
- **Missing forms**: MinutesEditorForm (meeting notes), DiscussionDecisionInlineForm (agenda_item discussion + decision + item_status), ReturnForCorrectionForm (reason comment + optional mark-section), ActionItemCreateFromMinutesForm (prefills source_meeting + source_agenda_item).

### Phase 6 explicit constraints (from PHASE6.md lines 49-55)
1. **`transaction.atomic`** for approval and publication.
2. **Prevent double publication.** → unique_together on snapshot(meeting, version) OR DB-level `published_at` transition guard using select_for_update + `skip_locked=False`.
3. **Audit every workflow event.** → 17 workflow triggers; existing ACTION_* covers 11 transitions; need: SUBMIT, RETURN, RESUBMIT, SNAPSHOT = 4 new actions (total audit 20; AuditLog.action max_length=16 OK all ≤ 16 chars — SNAPSHOT=8, SUBMIT=6, RETURN=6, RESUBMIT=8).
4. **Test approval and snapshot immutability.** → dedicated test module `tests/test_meeting_snapshots_immutable.py` with `@pytest.mark.django_db(transaction=True)` since audit hooks use on_commit.
5. **Line 54 stop.** — Do not touch notifications/warehouse/marketing/product_updates/accounting.

## Files and Modules

### Existing to modify
- `apps/meetings/models.py` (+4 new models, new status constants, + Meeting FK to ApprovedSnapshot nullable, dept submission state constants, REQUIRED_SECTION_TYPES tuples)
- `apps/meetings/migrations/0008_phase6_models.py` (0001 through 0007 may have been created by prior phases — check; actually current dir shows only 0001_initial — we'll name 0002_phase6_* to be sequential). Correction: migrations/ only has 0001 so next is `0002_phase6_models`.
- `apps/audit/models.py` + migration `apps/audit/migrations/0005_alter_auditlog_action.py` → ACTION_CHOICES expanded 16 → 20 constants + choices.
- `apps/audit/migrations/0005_*.py` migration for choices expansion.
- `apps/core/permissions.py`: 8 new predicates (can_submit_minutes, can_return_minutes, can_resubmit_minutes, can_approve_meeting, can_publish_meeting, can_close_meeting, can_reopen_meeting, can_create_snapshot). REOPEN_AUTHORIZED_ROLES tuple already exists (line 137 services.py). New MinutesAuthorized return roles.
- `apps/core/templatetags/permissions.py`: 8 new simple_tags mirror pattern.
- `apps/meetings/services.py`: new service layer — agenda_completeness(meeting)→ list[{dept, spec, state, missing}], dept_submission_set(meeting, dept, user, *, state, remarks), submit_for_review(meeting, user), return_for_correction(meeting, user, *, reason, marked_sections=None), resubmit_for_review(meeting, user), approve_meeting(meeting, user, *, reason=""), publish_meeting(meeting, user, *, reason="") → creates ApprovedSnapshot, close_meeting(meeting, user, *, reason=""), reopen_meeting(meeting, user, *, target_status=FOR_REVIEW, reason_required_nonempty), create_approved_snapshot(meeting, *, by_user, version=None, trigger=None) select_for_update to prevent double publish. Version increment from latest snapshot of meeting. Read-API: snapshot_meeting_versions(meeting) list, get_snapshot_payload(snapshot) returns dict.
- `apps/meetings/signals.py`: post_save ApprovedSnapshot → log ACTION_SNAPSHOT audit (on_commit).
- `apps/meetings/forms.py` + 4 forms: MinutesEditorForm, DiscussionDecisionInlineForm, ReturnForCorrectionForm, ActionItemCreateFromMinutesForm, inline helpers `build_discussion_formset(meeting)`.
- `apps/meetings/views.py` + 15 CBVs (see S6) — use `SalesEditRequiredMixin` pattern → `MinutesEditRequiredMixin / MinutesReviewRequiredMixin / MinutesApproverRequiredMixin` mixins in `apps.core.permissions`.
- `apps/meetings/urls.py` + 17 routes (UUID converters for meeting/snapshot PKs; `app_name = "meetings"` already preserved).
- `apps/meetings/admin.py`: 4 new @register; DepartmentSubmissionInline, ActionItemLinkInline.
- `templates/dashboard/home.html`: 5th 4-card KPI row (Meetings Pending Review / Returned for Correction / Approved This Month / Ready To Publish) + Current Meetings Prep dashboard link card.
- `apps/core/views.py`: home() try/except lazy import `meetings_prep_dashboard_data(user)` fallback sentinels.
- `templates/includes/sidebar.html` + offcanvas.html: 2 Phase-6 nav links (Minutes Prep Dashboard, Version History index).
- Docs: 3 writes (permissions.md Minutes roles matrix, workflows.md §13/§14, NEW meeting_snapshot_model.md).

### New files
- `tests/test_meeting_submissions.py` — 12 tests: dept submission lifecycle, agenda completeness, missing-info
- `tests/test_meeting_snapshots_immutable.py` — 15 tests: create snapshot, version auto-incr, payload preserves all fields, edit underlying AgendaItem does NOT mutate snapshot JSON, double publish raises ValidationError, publish rollback leaves snapshot absent.
- `tests/test_meeting_minutes_transitions.py` — 14 tests: submit → review → return with comments → resubmit → approve → publish → close → reopen with reason; each status history row + audit log present.
- `tests/test_meeting_minutes_permissions.py` — 10 tests: role matrix 8 predicates × 6 roles.
- `tests/test_meeting_minutes_pages.py` — 12 tests: 15 views status 200/302.
- `tests/test_meeting_actionitems_from_minutes.py` — 8 tests: create action item from editor, source_agenda_item FK set, link model row exists, snapshot payload records action item count.
- `templates/meetings/prep_dashboard.html` + 12 other templates per S8.
- `docs/meeting_snapshot_model.md`.

## Implementation Steps (dependency-ordered)

### Step 1 — Audit action expansion + new constants/role tuples
1. Add 4 new actions to apps.audit.models.AuditLog: ACTION_SUBMIT, ACTION_RETURN, ACTION_RESUBMIT, ACTION_SNAPSHOT. Expand ACTION_CHOICES 16→20 (max_length=16 all fit).
2. Add 8 permission predicates + 3 mixins in permissions.py; 8 template tags in core.templatetags.permissions.
3. makemigrations audit → 0005 migration. Migrate.

### Step 2 — 4 new meetings models + Meeting snapshot FK
1. Models in apps.meetings.models (all TimeStampedModel, UUID PKs, URL converters later <uuid:*>):
   - **DeptSubmissionState constants**: NOT_STARTED, IN_PROGRESS, SUBMITTED, RETURNED, ACCEPTED.
   - **RequiredSectionType**: OPENING_REMARKS, DEPT_UPDATES, ACTION_ITEMS_REVIEW, SALES_PERFORMANCE, OLD_BUSINESS, NEW_BUSINESS, OTHER.
   - **MinutesSectionSpec**: FK MeetingType, section_type, order, name, required Bool, description. unique_together(meeting_type, section_type).
   - **DepartmentSubmission**: FK Meeting, FK Department (null if cross), FK User (contributor), submission_state, last_updated_at, last_submitted_at, submitted_by (FK User), missing_info Text, management_remarks Text, notes Text. unique_together(meeting, department).
   - **ActionItemLink**: FK AgendaItem, FK ActionItem, created_by FK User, created_at Date auto. unique_together(agenda_item, action_item).
   - **ApprovedMeetingSnapshot**: FK Meeting NOT NULL, version PositiveSmallInt, trigger (SUBMIT/APPROVE/PUBLISH/MANUAL), snapshot JSONField (non-editable DB layer), approved_at DateTime, approved_by FK User, published_at DateTime null, published_by FK User null, notes Text. unique_together(meeting, version). DB select_for_update on create path prevents double publish/version clash.
   - **Meeting.approved_snapshot** FK one-to-one nullable to ApprovedMeetingSnapshot (related_name="active_for_meeting").
2. makemigrations meetings → 0002_phase6_models.py. Migrate. django check clean.

### Step 3 — Meetings service layer
1. agenda_completeness(meeting) per dept × spec → missing list.
2. dept_submission_upsert(meeting, dept, user, state, *, missing_info="", remarks="", notes="") — in atomic.
3. submit_for_review / return_for_correction / resubmit → wrap transition_meeting + DeartmentSubmission state SET; return reason required via REQUIRE_REASON.
4. approve_meeting → @atomic + select_for_update, log ACTION_APPROVE already exists in transition_meeting, create_snapshot with trigger=APPROVE.
5. publish_meeting → @atomic + select_for_update + snapshot_with_trigger=PUBLISH unique_together guard prevents double publish, sets Meeting.published_at already in transition_meeting + additionally link meeting.approved_snapshot to the created snapshot row.
6. close_meeting / reopen_meeting (authorized roles only) → transition_meeting wrapper. reopen requires non-empty reason.
7. create_approved_snapshot(meeting, *, by_user, version, trigger):
   - serialise 8 sections: meeting_meta (reference, title, dates, chair, type…), attendance (list {user_name, invited, attended, rsvp, role}), agenda_items (title, cat, order, owner_name, dept, discussion, decision, status, time_allocated, action_item_links_count + titles), discussions (redundant view), decisions (redundant), action_items (title, desc, owner, due, priority, status), sales_data (if meeting linked GroupPerformanceSnapshot: revenue_actual/target/pct, profit/margin/deficit), approval_meta (approved_at/by, trigger, version), version.
   - returns ApprovedMeetingSnapshot instance. Uses `json.dumps` no indent; Decimal → str; DateTime → isoformat; UUID → str.

### Step 4 — Signals + audit events wire
1. `meetings/signals.py`: post_save ApprovedMeetingSnapshot (created=True) fires ACTION_SNAPSHOT log. existing transition_meeting fires TRANSITION/PUBLISH/APPROVE/ARCHIVE; submit/return/resubmit services themselves additionally call log_audit_event with respective SUBMIT/RETURN/RESUBMIT action constants.

### Step 5 — Forms
1. MinutesEditorForm: Meeting notes + editable-title (readonly when non-editable status).
2. DiscussionDecisionInlineForm (per agenda_item: discussion, decision, item_status, order, owner, confidential).
3. build_discussion_formset → extra=0, each form prefixed by agenda pk.
4. ReturnForCorrectionForm: required Textarea reason, optional check list of section_spec_ids to highlight.
5. ActionItemCreateFromMinutesForm → pre-populated source_meeting + source_agenda_item.

### Step 6 — New views + routes (15 CBVs, UUID route converters)
Routes added in `apps/meetings/urls.py` under existing app_name="meetings":
1. `prep/dashboard/` → PrepDashboard ListView (dept × section grid table with status badges; missing-info highlights; link to edit per-dept submissions).
2. `<uuid:pk>/dept-submissions/` → DeptSubmissionStatus DetailView.
3. `<uuid:pk>/dept-submissions/<uuid:dept_id>/edit/` → DeptSubmissionUpsertView FormView.
4. `<uuid:pk>/minutes-editor/` → MinutesEditorView Form + inline disc/decision formsets + action item create button modal.
5. `<uuid:pk>/agenda/<uuid:ai_pk>/action-item/new/` → ActionItemFromMinutesCreateView.
6. `<uuid:pk>/minutes-preview/` → MeetingPreviewView (printable preview without snapshot; mirrors future approved snapshot).
7. `<uuid:pk>/validation/` → MeetingValidationSummaryView — rows per section: PASS / MISSING / WARNING with link back to editor.
8. `<uuid:pk>/submit-review/` → SubmitForReviewView POST-only transition + redirect.
9. `<uuid:pk>/return-correction/` → ReturnForCorrectionFormView.
10. `<uuid:pk>/resubmit-review/` → ResubmitForReviewView.
11. `<uuid:pk>/approve/` → ApproveMeetingView (POST-only; @atomic).
12. `<uuid:pk>/publish/` → PublishMeetingView (POST-only; @atomic + double-publish guard).
13. `<uuid:pk>/close/` → CloseMeetingView (POST-only).
14. `<uuid:pk>/reopen/` → ReopenMeetingView (Form: reason required).
15. `<uuid:pk>/versions/` → MeetingVersionHistory ListView (MeetingStatusHistory + ApprovedMeetingSnapshot rows mixed timeline).
16. `<uuid:meeting_pk>/snapshots/<uuid:snap_pk>/` → ApprovedSnapshotDetailView (read-only display of JSON fields; template uses the snapshot payload, NOT live records — this is the test assertion point for immutability).
17. `snapshots/<uuid:pk>/printable/` → SnapshotPrintableView (standalone A4 landscape printable mirror of Phase 5 pattern).

### Step 7 — Admin registrations
1. 4 @register(MinutesSectionSpec/DepartmentSubmission/ActionItemLink/ApprovedMeetingSnapshot).
2. DepartmentSubmissionInline(TabularInline on MeetingAdmin); ActionItemLinkInline on AgendaItemAdmin; ApprovedMeetingSnapshot read-only fields except notes.

### Step 8 — Templates (13 new; plus rewires)
New templates in templates/meetings/:
1. prep_dashboard.html — BS5 card + .table-responsive; rows are departments × RequiredSectionSpec; sticky first column; 10 cols per PHASE6.md line 27-36.
2. dept_submission_status.html — one department detail + remarks + last update badge.
3. dept_submission_form.html.
4. minutes_editor.html — 2 columns: LHS agenda items with DiscussionDecisionInlineFormset per item; RHS sticky notes panel + save button + action-item modal launcher.
5. discussion_decision_inline.html — form snippet.
6. minutes_preview.html — standalone preview (extends base, not printable yet).
7. validation_summary.html — grouped by section_type; PASS green / MISSING red / WARNING amber badges; per-row anchor links to minutes-editor fragment.
8. submit_for_review_confirm.html.
9. return_for_correction_form.html — big reason textarea + checklist.
10. version_history.html — timeline (merged: status arrows + snapshot boxes with "VIEW" link).
11. snapshot_detail.html — frozen render using ONLY snapshot.payload dict; NEVER queries live agenda/attendance tables (the key immutability display).
12. snapshot_printable.html — standalone; @page landscape; omits nav.
13. actionitem_create_from_minutes.html — modal form.

Rewires:
- templates/includes/sidebar.html: Minutes Prep Dashboard → `meetings:prep_dashboard`.
- templates/includes/offcanvas.html: mirror.
- home dashboard 5th row 4 cards; Current Minutes Prep card (links to meetings:prep_dashboard, shows count meetings needing review).

### Step 9 — Navigation & dashboard rewires + lazy import
apps/core/views.py home(): meetings_prep_dashboard_data(user) try/except ImportError fallback dict sentinels (mirror phase5 pattern); templates/dashboard/home.html 5th 4-card row.

### Step 10 — 6 Phase 6 test modules; cumulative target ≥ 361 pass
Target cumulative: 302 (current) + 71 new = 373 (≥ 361 goal; 9 headroom):
1. test_meeting_submissions (12 tests: 4 states + 2 completeness cases + missing-info accuracy + 6 role-gated writes).
2. test_meeting_snapshots_immutable (15 tests: 3 versions × 5 payload segments × edit-after-snapshot assert JSON unchanged × double publish raises).
3. test_meeting_minutes_transitions (14 tests: 9 transitions × 2× audit check × 2× history record check × reopen reason req × double publish guard).
4. test_meeting_minutes_permissions (10 tests: 8 predicate roles).
5. test_meeting_minutes_pages (12 views tests: 15 URLs × permission gating → ~59 checks but 12 test funcs).
6. test_meeting_actionitems_from_minutes (8: creation + FK set + snapshot payload includes action items).
→ 71 new tests; cumulative 373 ≥ 361.

All audit-reading tests use transaction=True.

### Step 11 — Docs + final quality chain
Docs writes (3):
1. permissions.md — Minutes Role Matrix (8 capabilities × 6 roles; 4 audit actions SUBMIT/RETURN/RESUBMIT/SNAPSHOT table; 3 new mixins; new template tags).
2. workflows.md — §13 Minutes Preparation Workflow (prep dashboard → editor → validation → submit → return → resubmit → approve → publish → close → reopen; 11-state diagram). §14 Approved Snapshot Immutability (JSON payload 8 segments; version counter; double publish guard; frozen payload vs live edits example).
3. NEW docs/meeting_snapshot_model.md (JSON schema 8 sections; versioning algorithm; idempotency; audit trigger; editable vs frozen table; permissions matrix on snapshots).

Final quality chain (repeat from phase5 pattern):
`ruff check/format` + `manage.py check` + `makemigrations --check` + `pytest tests/ -q` → 0 FAIL 373 pass target.

## Dependencies and Considerations
1. **Audit actions max_length=16**: all new 4 fit (SNAPSHOT=8, SUBMIT=6, RETURN=6, RESUBMIT=8).
2. **Circular imports**: service layer reads GroupPerformanceSnapshot; lazy import of sales_updates models inside helper functions never module-top.
3. **Atomic guards**: approve/publish both do `select_for_update` on Meeting + ApprovedMeetingSnapshot unique_together DB constraint guarantee "exactly one snapshot per meeting/version".
4. **UUID routes**: all meeting_pk, snap_pk, dept_pk route parameters use `<uuid:*>`.
5. **Frozen snapshot rendering test assertion**: SnapshotDetailView response HTML contains strings present at snapshot creation time even after user edits underlying agenda rows afterward.
6. **JSON field + Decimal serialization**: convert Decimal → str with _q precision via `json.dumps(default=str)`; on display, cast back to Decimal inside snapshot view layer before currency formatting (5 filters re-used from sales_formatting via minutes_snapshot_filters — or re-use existing sales_formatting load).
7. **EmailBackend DeprecationWarning**: tolerated (pytest warning category already); no migration required until Django 7.

## Validation
- `pytest tests/test_meeting_*.py --tb=short` — 0 FAIL target.
- Full cumulative: `pytest tests/ -q` ≥ 373 pass, 0 FAIL.
- `ruff check apps config tests manage.py`; `ruff format --check ...`; `manage.py check`; `makemigrations --check --dry-run No changes detected`.

## Risks
1. **Approved snapshot JSON too large**: Use `JSONField(compressible=True)` (default on Postgres JSONB; no-op on SQLite tests).
2. **Race double publish**: Two-tier guard — `ApprovedMeetingSnapshot.unique_together=(meeting, version)` DB hard + `select_for_update` app-level.
3. **ApprovedSnapshotDetail accidentally reading live tables**: Code review + immutability test edits agenda item AFTER snapshot + re-renders snapshot detail → asserts still shows old text.
4. **Circular import services/meetings ↔ sales_updates**: Always lazy import.
5. **Home dashboard sales 3rd row / minutes 5th row lazy sentinels**: dict sentinels not None when queryset missing or ImportError; templates use `{% if sales_summary %}` checks matching Phase 4/5 patterns.
