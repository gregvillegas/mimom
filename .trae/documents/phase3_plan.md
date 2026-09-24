# Phase 3 Implementation Plan — Meeting & Agenda Management

## Repository Research

**Current state (after Phase 2 completion):**
- Django 6.1.1 monolith with Python 3.14, `AUTH_USER_MODEL = "accounts.User"`. Base classes in `apps/core/models.py`:
  - `TimeStampedModel` (abstract): UUID `id` PK, `created_at`, `updated_at` with ordering `[-created_at]`.
  - `BaseNamedModel` (abstract, inherits TimeStampedModel): `name`, `is_active`, ordering `[name]`.
- Skeleton app structure for meetings (`apps/meetings/`) exists but models/views/admin are empty files. URLs already registered in `config/urls.py` line 48: `path("meetings/", include("apps.meetings.urls"))` with `app_name = "meetings"` in urls.py. Template folder `templates/meetings/` noted in project_structure.txt but does not exist on disk yet.
- Phase 2 RBAC has 6 groups: System Admin, Management Admin, Meeting Chairperson, Minutes Secretary, Department Contributor, Viewer — wired via `User.has_role()`, `apps/core/permissions.py` mixins/decorators, and `apps/core/templatetags/permissions.py`.
- `DEFAULT_AUTO_FIELD = BigAutoField`, but non-auth domain models inherit `TimeStampedModel` which uses **UUID** PKs — so Meeting/AgendaItem/Attendance etc. will be UUID. Users remain BigInt PK.
- `ATOMIC_REQUESTS = True` globally in base.py; additional explicit `transaction.atomic()` needed for multi-step transitions.
- Audit service at `apps/audit/services.py`: `log_audit_event(record_type, record_id, action, ..., immediate=False, user=, target_user=, ...)` — 9 action constants exist (CREATE/UPDATE/DELETE/ASSIGN/ROLE/LOGIN/LOGOUT/REGISTER) and we will add TRANSITION/PUBLISH/ARCHIVE constants to `apps.audit.models.AuditLog` action list or reuse UPDATE with reason field (prefer UPDATE + reason, to avoid altering existing 9-action contract; extend if a clean new constant is necessary only).
- `media/meeting_attachments/` directory exists conceptually (project_structure.txt); need to ensure MEDIA_ROOT `meeting_attachments` dir exists in code (via `upload_to=` callable, django auto-creates it on upload).
- Sidebar/navbar/offcanvas have Meetings section with placeholder links — need to wire real URLs.
- `apps/action_items/models.py` is empty — Action Items are Phase 4+; no Meeting→ActionItem FK yet; avoid circular FK across phases.

**PHASE3.md 16 numbered + 5 business rule deliverables:**
1. CRUD (list/detail/create/update, permitted delete or archive)
2. Human-readable unique reference generator
3. Attendance (invitation vs actual)
4. Agenda category management
5. Agenda item create/edit with discussion/decision/status/owner/dept/confidentiality fields
6. Agenda ordering
7. Item fields from line 37 (discussion, decision, status, owner, department, confidentiality)
8. Supporting attachments (agenda item + meeting level)
9. Workflow transitions across 10 statuses
10. Transition validation (enforce legal edges; reopening requires role + reason)
11. MeetingStatusHistory model populated on every transition
12. Draft locking + publishing controls
13. Calendar + list views
14. Mobile-friendly pages
15. Management dashboard shell (home dashboard cards for upcoming meetings / statuses)
- Business rules: Approved/Published not directly editable; reopening needs authorization + reason; references unique; agenda carry-forward; attendance invitation vs actual distinct; confidential items permission-controlled.

## Files and Modules

### New/Replaced Core Files
- `apps/meetings/models.py` — 8 models (MeetingType, Meeting, MeetingStatusHistory, MeetingAttendance, AgendaCategory, AgendaItem, AgendaItemAttachment, MeetingAttachment) + 10 status constants + helper `Meeting.transitions_to`, `can_edit`, `reference_generator`
- `apps/meetings/forms.py` — MeetingForm (gated by status), AttendanceFormSet, AgendaCategoryForm, AgendaItemForm (confidentiality visibility), AgendaItemOrderFormSet, Attachment forms, TransitionForm (reason field)
- `apps/meetings/services.py` — Workflow service: `transition_meeting(meeting, target_status, by_user, reason="")` with validation, status history write, audit log, and rollback on any failure; `generate_meeting_reference(meeting)` for unique refs; `carry_forward_agenda_items(source_meeting, target_meeting, item_ids)`
- `apps/meetings/views.py` — CBVs: MeetingListView (with calendar alternate view?), MeetingDetailView, MeetingCreateView (MeetingChair/MinSec/MgmtAdmin/SystemAdmin), MeetingUpdateView (Draft/OpenUpdates/AgendaFinalized/InProgress only), MeetingArchiveView (soft-delete); AttendanceView; AgendaCategoryListView/Create/Update; AgendaItemCreate/Update/Delete; AttachmentUpload; TransitionView; CarryForwardView
- `apps/meetings/admin.py` — Read-only history stack; inlines for Attendance, AgendaItems, Attachments; searchable
- `apps/meetings/urls.py` — 15-20 named routes (app_name=meetings), UUID `<uuid:pk>` converters for all meeting/agenda/attendance pk params since they inherit TimeStampedModel
- `apps/meetings/signals.py` (optional) — For meeting reference autofill on pre_save, audit log hooks
- `apps/meetings/apps.py` — Register signals in `ready()` if signals used
- `apps/meetings/migrations/0001_initial.py` — Generated via `makemigrations meetings`

### Templates (Mobile-first Bootstrap 5.3)
- `templates/meetings/meeting_list.html` — Tab switcher: List view (with filters) and Calendar view (month grid rendered via template loop over date_start)
- `templates/meetings/meeting_detail.html` — Summary card, status badge, transition buttons, attendance tab, agenda tab, attachments tab, confidential items hidden from unauthorized users
- `templates/meetings/meeting_form.html` — Create/Update form with validation notice when Published/Approved locked
- `templates/meetings/meeting_attendance.html` — Checkmark grid invited vs attended; invite new attendees search picker
- `templates/meetings/agenda_categories.html` — CRUD table
- `templates/meetings/agenda_item_form.html` — Includes drag-reorder (HTML5 drag order + hidden inputs)
- `templates/meetings/meeting_calendar_partial.html` — Includable calendar grid
- `templates/meetings/_partials/status_badges.html` — Reusable status badge include with color mapping
- `templates/meetings/_partials/transition_modal.html` — Reusable modal with reason textarea

### Navigation Updates
- `templates/includes/sidebar.html` meetings section: replace `#` links with real URLs (Meetings list → `meetings:meeting_list`, Agenda categories → `meetings:agenda_category_list`, Attendance is reached via meeting detail)
- `templates/includes/offcanvas.html` — mirror sidebar meetings section
- `templates/dashboard/home.html` — Add management dashboard shell: 4-6 summary cards (Upcoming meetings count, Drafts, For Review, Approved this month, Archived, Open Action Items (placeholder 0)) + table of next 5 meetings, using view helpers in `apps/core/views.py::home` or new `apps/meetings/views.py::dashboard_context` included via inclusion tag

### Permission Core Extensions
- `apps/core/permissions.py`: Add `is_meeting_chair`, `is_minutes_secretary` predicates (they already exist per Phase 2 summary; verify they still exist). Add `can_view_confidential_items(user, meeting=None)` — SysAdmin, MgmtAdmin, MeetingChair, MinSec, OR if a user is the owner/dept head of the confidential item. Add helper `can_create_meeting`, `can_edit_meeting`, `can_archive_meeting`, `can_transition_meeting(user, meeting, target_status=None)`.
- `apps/core/templatetags/permissions.py`: expose same as template tags/filters for detail page buttons.

### Tests
- `tests/test_meeting_models.py` — Reference uniqueness, transitions valid/invalid edges, can_edit locks, confidential access scoping, carry forward copies item but not attachments if user lacks rights
- `tests/test_meeting_transitions.py` — Direct service test of every 10-choose-2 edge; valid transitions pass; invalid raise ValidationError; reopen-for-correction requires Management/System Admin + reason; Approved/Published can only go → Archived or Returned-For-Correction by admin; MeetingStatusHistory written per transition
- `tests/test_meetings_permissions.py` — 403 check: Viewer cannot create; Contributor can list but not edit; Chair can transition own-created or assigned; MinSec can add agenda; Confidential items return 403 for unprivileged direct URLs; Approved meetings reject POST to edit views
- `tests/test_meetings_views.py` — Happy path smoke: create meeting, transition to Open, add attendee, add 2 agenda items, reorder items, upload attachment, transition through to Published, verify edit view returns PermissionDenied
- `tests/test_attendance_invited_vs_attended.py` — Invited flag can be True without attended; attended-only records also valid; counts correct

### Documentation Updates
- `docs/permissions.md` — Add meeting roles column, confidential item rules, transition matrix
- `docs/workflows.md` — Add 2 canonical workflows: (A) Meeting lifecycle Draft→...→Published→Archived end-to-end, (B) Returned-For-Correction reopening flow
- Optionally create `docs/meeting_status_transitions.md` — 10x10 adjacency matrix of valid edges and required roles

## Implementation Steps

Dependency ordering. After every 3 steps, sanity check via `manage.py check` and `makemigrations --check`:

1. **Models & Migration** — Write all 8 models + 10 status constants in `apps/meetings/models.py` (all inheriting TimeStampedModel or BaseNamedModel). `MeetingType(BaseNamedModel)`, `Meeting(TimeStampedModel)` with FKs: type, created_by, last_modified_by; `title`, `reference` (unique), `description`, `start_at/end_at`(DateTimeField, tz-aware), `location`, `department` (nullable FK to Department for scope), `chair` (nullable FK to User assigned chair), `status` (CharField choices: 10 statuses), `is_locked` Boolean for draft-lock, `notes`. `MeetingStatusHistory(TimeStampedModel)` with FK meeting, `from_status`, `to_status`, `transitioned_by` FK User, `reason` TextField, timestamp. `MeetingAttendance(TimeStampedModel)` with FK meeting + FK user, unique_together; `is_invited` bool; `is_attended` bool; `rsvp_status` CharField (Yes/No/Maybe/Pending); `arrived_at`/`departed_at` nullable datetime; `notes`. `AgendaCategory(BaseNamedModel)` with ordering `order = PositiveIntegerField(default=0)` + `scope_department` nullable FK. `AgendaItem(TimeStampedModel)` FK meeting + FK category nullable; `order` PositiveIntegerField; `title`; `discussion` TextField; `decision` TextField; `item_status` (To Be Discussed / Carried Forward / In Progress / Decided / Withdrawn); `owner` FK User nullable; `department` FK Department nullable; `is_confidential` Boolean default False; `parent_item` FK self nullable for sub-items; `carried_forward_from` FK self nullable to source item; `unique_together(meeting, order)`. `AgendaItemAttachment(TimeStampedModel)` FK item + `file` (FileField upload_to meeting_attachments/agenda/YYYY/); `filename`, `uploaded_by` FK User; `is_confidential` bool. `MeetingAttachment(TimeStampedModel)` FK meeting + `file` similar fields. Run `manage.py makemigrations meetings` → generate `0001_initial.py`. Add pre-save signal or model `save()` hook to auto-call `generate_meeting_reference(meeting)` if reference is blank; unique constraint on Meeting.reference with db_index=True.

2. **Permission Helpers** — Verify/add predicates in `apps/core/permissions.py`: `can_create_meeting(user) → has_role(System/MgmtAdmin, Chair, MinSec)`. `can_edit_meeting(user, meeting) → can_create_meeting(user) AND meeting.status in {Draft, OpenUpdates, AgendaFinalized, InProgress, ForReview, ReturnedForCorrection}`; also sys-admins may bypass (per superuser short-circuit in has_role). `can_archive_meeting(user, meeting) → SysAdmin/MgmtAdmin only`. `can_transition_meeting(user, meeting, target) → chair or minsec or admin, plus legal edge`. `can_view_confidential_items(user, meeting=None) → user.has_role(System/MgmtAdmin, Chair, MinSec) OR (owner of item) OR (department head of item.department)`. Update template tags mirror.

3. **Workflow Services** — Write `apps/meetings/services.py`. Transition DAG constant `VALID_TRANSITIONS: dict[str, set[str]]` defining every legal move; reopen rules: ReturnedForCorrection only reachable by Sys/MgmtAdmin with reason length > 0; Approved/Published cannot be edited directly but can be transitioned → Archived or → ReturnedForCorrection (requires admin + reason). `transition_meeting()` wrapped in `transaction.atomic()`, raises `ValidationError` if move illegal; writes `MeetingStatusHistory` row; writes audit log via `apps.audit.services.log_audit_event(action=TRANSITION or reuse UPDATE with reason field populated; add new ACTION_TRANSITION constant to audit.models.AuditLog if code is cleaner — decide: extend audit action set (preferred, for searchability)). Add `generate_meeting_reference(meeting)` format like `{MeetingType.code or 'MTG'}-{YYYY}-{NNNN}` with DB row-level lock or get_or_create uniqueness guard; if empty code fallback use meeting type's slugified name. `carry_forward_agenda_items(source, target, item_ids)` copies item fields but clears decision, resets item_status to Carried Forward, writes `carried_forward_from` pointer, copies owner/dept/category/order (append to end of target). Skips copying `is_confidential=True` items if caller cannot view source confidential items.

4. **Forms** — Create `apps/meetings/forms.py`. MeetingForm: includes all basic fields; widget for start/end uses Bootstrap date+time picker; excludes `status` from direct edit (transitions go via service only). MeetingUpdateForm: extends MeetingForm but conditionally excludes fields when `instance.status` is Approved/Published (raise SuspiciousOperation or form-level ValidationError if attempt to save changes on locked status). AttendanceFormSet: inlineformset_factory over MeetingAttendance with `user`, `is_invited`, `is_attended`, `rsvp_status`. AgendaCategoryForm with ordering and scope fields. AgendaItemForm: confidential item, hide from contributors without access; carry-forward as disabled read-only indicator. TransitionForm: `target_status` ChoiceField filtered by legal edges + `reason` CharField required when move crosses Returned/Approved borders. AgendaOrderForm: hidden order per item for reorder POST endpoint. AttachmentUploadForm: ModelForm restricted to confidential flag based on uploader's permission.

5. **Views & URLs** — Populate `apps/meetings/views.py` and `apps/meetings/urls.py`. All views use `LoginRequiredMixin`; write gating using role mixins from core permissions. Meeting list: supports `?view=calendar` query parameter → template renders 31-day grid using start_at; `?q=` filter title/reference; `?status=` filter status; `?department=` filter dept. Detail view: passes `user_can_edit`, `user_can_view_confidential` into context, redacts confidential discussion/decision fields in rendered HTML when unauthorized AND still redacts in raw response body via `get_object() -> raise 404` if directly accessing by URL that shouldn't (better: render with text replaced by "[Confidential]"). Attendance view: POST handles marking invite/attended. AgendaCategory: simple CRUD. AgendaItem create/edit: route to meeting/<uuid:meeting_pk>/agenda/new/ so it's always meeting-scoped. Reorder: POST `item_order` list → bulk update AgendaItem.order. Upload attachments: POST file; meeting-level or item-level endpoints. Transition view: POST target_status + reason → invokes `transition_meeting()` service; success redirects to detail. Archive view: only Sys/Mgmt Admin; sets status Archived. Carry-forward view: UI picker lets user select source meeting IDs, calls service. URL names: `meeting_list`, `meeting_detail`, `meeting_create`, `meeting_update`, `meeting_archive`, `meeting_attendance`, `meeting_transition`, `meeting_carry_forward`, `agenda_category_list`, `agenda_category_create`, `agenda_category_update`, `agenda_item_create`, `agenda_item_update`, `agenda_item_delete`, `agenda_item_order`, `meeting_attachment_upload`, `agenda_item_attachment_upload`, `meeting_attachment_delete`, `agenda_item_attachment_delete`. Use `<uuid:pk>` / `<uuid:meeting_pk>` / `<uuid:item_pk>` / `<uuid:category_pk>` / `<uuid:attachment_pk>` URL path converters (all these models inherit TimeStampedModel with UUID PKs).

6. **Signal Registration (optional, small)** — If reference generator was done as pre-save signal rather than model save hook, create `apps/meetings/signals.py` and wire `ready()` in apps.py. Also optionally post_save MeetingStatusHistory → audit log, though the service already writes that directly; avoid double-writing. Audit creation/update/delete on Meeting/AgendaCategory/AgendaItem/MeetingAttendance using same pattern as apps/accounts/signals if desired (minimum: use the audit service directly in views/services). Prefer keeping it simple: write audit events explicitly inside views + service, do not create new signal file for phase 3 unless testing shows double writes from accounts signal patterns.

7. **Admin** — Populate `apps/meetings/admin.py`. MeetingAdmin with list_display (reference, title, status, start_at, chair, department), list_filter(status, department, type), search_fields(reference, title, location). Inlines: MeetingStatusHistoryInline (readonly, no add/change/delete — matches audit philosophy from phase 2), MeetingAttendanceInline, AgendaItemInline (tabular with sortable order), MeetingAttachmentInline. MeetingStatusHistoryAdmin as standalone read-only list. AgendaCategoryAdmin simple ordering sort. Models registered with appropriate read-only inlines.

8. **Templates + Mobile-Friendly Design** — Create all template files listed above, extending `templates/base.html`. Bootstrap 5.3 responsive; detail page uses offcanvas on mobile for tab navigation (attendance/agenda/attachments). Status badge partial renders color mapping per status: Draft=muted, OpenUpdates=info, AgendaFinalized=primary, InProgress=warning, ForReview=secondary, ReturnedForCorrection=danger, Approved=success, Published=success-outline, Closed=dark, Archived=muted-outline. Calendar view month grid as divs, sticky header on scroll. Meeting form fields break into multiple fieldsets; 2-col on desktop, single-col on mobile.

9. **Navigation + Dashboard Shell** — Update sidebar.html lines 13-30 to wire real URLs. Update offcanvas.html meetings section same. Modify `apps/core/views.py` home view to call a new helper `apps.meetings.views.dashboard_summary_counts()` returning dict of counts grouped by status + next_meetings queryset; render dashboard cards in `templates/dashboard/home.html` (meeting status cards + upcoming 5 meetings table; 0 placeholder for action items; sales updates placeholder 0). No new URLs needed — home page already at `/`.

10. **Tests** — Create 5 test modules listed in Tests section. Use `pytest.mark.django_db(transaction=True)` where tests exercise audit/transaction.on_commit paths; standard marker elsewhere. Coverage goals: 100% of 10×10 transition DAG legal edges pass; ≥5 invalid edge cases each raise ValidationError. Permission matrix: at least 15 different role-vs-view tests. Confidential item redaction test asserts that rendered detail view content contains "[Confidential]" for an unprivileged contributor user.

11. **Documentation** — Update `docs/permissions.md` with meeting role matrix (new columns: CreateMeeting, EditMeeting, Transition, ViewConfidential, Archive). Update `docs/workflows.md` with two new workflows: (A) Meeting lifecycle, (B) Returned-for-correction. Write transition adjacency matrix either inline in docs or as `docs/meeting_status_transitions.md` (one new doc file if inline would clutter too much — inline preferred, add new file only if > 20 lines needed for matrix table).

12. **Final Verification** — Run in order: (a) `manage.py check` clean. (b) `manage.py migrate` meetings 0001 applied. (c) `manage.py makemigrations --check` no changes. (d) `pytest tests/` all passing (existing 61 Phase 1/2 + new Phase 3 ≥25, combined ≥86). (e) `ruff check apps config tests manage.py` clean. (f) `ruff format --check apps config tests manage.py` clean. (g) Quick manual smoke: login as admin, create meeting, transition twice, add agenda item, mark attendance, publish, confirm edit button disabled.

## Dependencies and Considerations

- **FK to accounts.User, Department**: Use string references `"accounts.User"` and `"accounts.Department"` in meetings model to avoid circular imports. `on_delete=SET_NULL` on nullable FKs (chair, owner, department), `on_delete=CASCADE` on mandatory (meeting FK → attachments, attendees, items). `MeetingStatusHistory.from_status/to_status` use CharField values directly (no FK to "status model" — simpler).
- **Upload paths**: For attachments, use `upload_to=user_directory_path` style callable that nests under `MEDIA_ROOT/meeting_attachments/{meeting_id}/{type}/{YYYYMM}/`. Django auto-creates parent dir when saving; no extra mkdirs needed.
- **Bootstrap 5.3 CSS/CDN**: Assumed Bootstrap 5.3 CSS + icons CDN is already in base.html from Phase 1 (verify before using any classes). If missing, add CDN link+script+icons in `<head>` of base.html.
- **Calendar rendering**: Simple 42-cell month grid computed in a view helper `build_calendar(month_start, meetings)` that returns list of 42 dicts. Not using fullcalendar.js for phase 3 (no JS bundler set up per base settings; keep plain HTML server-render per project structure).
- **Django 6.1 removed-args caution**: Avoid `select_related()` with no arguments (emits deprecation warning; found in phase 2). Explicitly list related fields when used: `select_related("type", "chair", "department", "created_by")`.
- **Audit action set expansion**: Currently audit models.py has 9 action constants. Adding ACTION_TRANSITION, ACTION_PUBLISH, ACTION_ARCHIVE new constants in `apps.audit.models.AuditLog` will require no new DB migration (CharField with choices just expands validation choices in Django, not DB schema — but better to check: if choices is used, makemigrations DOES NOT create migration for CharField choices. Confirmed: Django docs say choices are pure-Python. Safe to add new constants. Then update seed_roles docs if anything referenced 9-actions count; no seed command uses them so it's fine).
- **Audit record_id type**: Record_id in AuditLog is `CharField(max_length=255)`. Meeting PK is UUID; cast via `str(pk)` works. Good.
- **Mobile-friendly CSS**: Use Bootstrap 5 classes `.d-sm-block`, `.col-12 col-md-6`, responsive tables `.table-responsive` for attendance grids, sticky nav on mobile already in base.html presumably.
- **Meeting unique reference generation**: Not DB-sequence (not DB-portable). Implementation: inside `transaction.atomic()`, lock row or count-filter + unique constraint together: pattern `TYPE-YYYY-NNNN`; count existing rows `WHERE reference LIKE 'TYPE-YYYY-%'` to get next NNNN, save, rely on unique constraint IntegrityError retry up to 3 times.
- **Inactive users cannot be assigned active attendance rows**: Reuse pattern from forms.py phase 2 — pass for_user into attendance subforms so clean() raises if user is inactive and is_attended/is_invited active flag would be set.

## Validation

1. `manage.py check`
2. `manage.py makemigrations meetings` (runs during step 1), then `manage.py migrate` meetings app
3. `makemigrations --check` after all model changes final
4. `pytest tests/ --tb=short` — all pass, ≥86 total
5. `ruff check apps config tests manage.py`
6. `ruff format --check apps config tests manage.py`
7. Manual smoke on dev server (optional, if runserver started): login sysadmin → create meeting → transition through states → publish → edit returns 403; login viewer → list works, detail redacts confidential, edit buttons hidden; login contributor → cannot create/transition.

## Risks

- **Circular imports between meetings↔accounts↔audit**: Mitigated by string-FK references `"accounts.User"` in model definitions and importing services inside view functions only when needed (models never import services; services never import views).
- **Phase 2 `ATOMIC_REQUESTS=True` + explicit `transaction.atomic()` inside `transition_meeting`**: Django nested transactions use savepoints; works, but if an outer rollback happens history write vanishes too — that is desired. Tests use `transaction=True` marker if they need on_commit audit writes to fire.
- **UUID vs int PK confusion in URLs (regression risk from phase 2 fix)**: All meeting/agenda/attendance PKs are UUID (inherit TimeStampedModel) so `<uuid:pk>` converters ARE correct in meetings urls; phase 2 had the opposite (BigInt on auth). Write step 5 explicitly uses correct converter per model base class. Reviewer can double-check: grep meeting_pk in urls.py — all should be `uuid:` type.
- **Confidential data leaks via JSON/changeset in audit log previous_values**: If a MeetingAgenda item is confidential, its audit event's previous_values/new_values/changes JSON still contains discussion text in audit log. Mitigation: confidential audit events — if the actor cannot view confidential items, do not write detailed JSON, write scrubbed JSON `"[Confidential redacted]"` placeholder only, or ensure audit log view is admin-only anyway (it is; read-only admin in phase 2). Combined acceptable.
- **Carry forward copies item order: may violate unique_together(meeting, order) if target meeting already has agenda items at same order**: Mitigation in service: append to end of target meeting order using `max(order) + 1` for all copied items; test step 10 asserts no IntegrityError raised.
- **Test performance (61 existing + new 30~)**: Uses SQLite in-memory; acceptable. Avoid `transaction=True` where not strictly needed.
- **Sidebar/offcanvas URL name typos**: Always `reverse(...)` once; if typo, django NoReverseMatch caught in `manage.py check` if URL patterns loaded in tests — add a smoke test that renders dashboard/sidebar with a logged-in user to catch any.
