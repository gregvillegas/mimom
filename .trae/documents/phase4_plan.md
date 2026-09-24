# Phase 4: Action Items Implementation Plan

## Repository Research

### Current Architecture (confirmed from codebase)

**Base patterns (inherited from Phase 3, must follow exactly):**
- **Django 6.1 + Python 3.14, split settings in config/settings/{base,development,production}.py.**
- **PK Scheme:** `DEFAULT_AUTO_FIELD = BigAutoField` globally; all action_items domain models must inherit `TimeStampedModel` (abstract) from [apps/core/models.py](../apps/core/models.py) → UUID primary key + `created_at/updated_at`. Therefore all action_items URL routes use `<uuid:pk>` converters.
- **AUTH_USER_MODEL = "accounts.User"** with BigInt PK. Do NOT store user PKs as UUIDs; use `ForeignKey("accounts.User", ...)` directly.
- **Audit service signature:** `log_audit_event(*, record_type: str, record: ModelInstance, action: str, user=, target_user=, ip_address=, previous_values=, new_values=, reason="", correlation_id=, immediate=False)` — takes a **model instance** (`record=`) NOT `record_id=`. No `changes=` kwarg; diff is computed internally. See [apps/audit/services.py](../apps/audit/services.py).
- **Audit actions expanded** from Phase 2 with `ACTION_TRANSITION` + `ACTION_ARCHIVE`. Phase 4 adds `ACTION_COMPLETE`, `ACTION_REOPEN`, `ACTION_CARRY_FORWARD`. These must be added to `AuditLog.ACTION_CHOICES` with new migration.
- **RBAC:** 6 role groups (System Admin, Management Admin, Meeting Chair, Minutes Secretary, Department Contributor, Viewer). User-level cache `user.has_role(*names)`. See [apps/core/permissions.py](../apps/core/permissions.py) for existing predicates `MEETING_AUTHOR_ROLES` / `can_edit_meeting` / mixins to follow the same pattern for actions.
- **Service layer pattern:** transaction.atomic() + select_for_update() + rollback/retry on IntegrityError. Model `Meeting`'s `transition_meeting()` in [apps/meetings/services.py](../apps/meetings/services.py) is the canonical pattern for status DAG + history + audit.
- **Signal pattern:** [apps/meetings/signals.py](../apps/meetings/signals.py) pre_save auto-fills reference — same approach will auto-fill any required auto-generated action reference (like `ACT-2026-0123`).
- **Formset pattern:** `build_attendance_formset()` monkey-patches `_construct_form` to inject `for_user` kwarg. Reuse for ActionItemAssignee inline formset.
- **Navigation:** Sidebar [templates/includes/sidebar.html](../templates/includes/sidebar.html) has an Actions section with `href="#"` placeholders (All Items, Overdue, My Assignments). Wire those to action_items named URLs. Dashboard [templates/dashboard/home.html](../templates/dashboard/home.html) currently has 4 meeting-count cards — add Action Items KPI row below.
- **Config / URL:** `action_items` already in `INSTALLED_APPS` and `config/urls.py` includes `"actions/"` → `apps.action_items.urls`.
- **Status DAG philosophy (reuse from meetings):** action item statuses are module-level constants + choices tuple, not as class attributes. Transition service returns `ActionItemStatusHistory` objects, writes AuditLog, returns exception for invalid transitions.
- **Carry-forward philosophy (reuse):** meetings `carry_forward_agenda_items()` links records via FK, skips confidential by default, runs in atomic block, writes audit events. Reuse same 6-part contract for action items.

### Constraints from Phase4.md (lines 1-56)

**6 Models required:**
1. ActionItem — main record with title, description, FK to source AgendaItem / Meeting, FK owner (User), department, priority (LOW/MED/HIGH/URGENT), status, progress_pct (0..100), due_date, blockers, next_steps, completed_at, reopened_count.
2. ActionItemAssignee — linking table (many-to-many via explicit model) User → ActionItem with `is_primary` / `is_supporting` flag so we have distinct Primary Assignee vs Supporting Users (Phase4.md items 4,19).
3. ActionItemUpdate — status/progress update notes with author + timestamp + optional file link (Phase4.md item 9).
4. ActionItemAttachment — file upload to `action_item_attachments/<uuid>/YYYYMM/<filename>` (Phase4.md item 11).
5. ActionItemStatusHistory — immutable log of status changes (from, to, reason, by_user, transitioned_at) (Phase4.md item 12/27).
6. ActionItemCarryForwardLink — FK new_action → old_action + carried_by (User) + carried_at + reason (Phase4.md item 36–44) to enforce idempotency.

**Deliverables 1–36 mapping to features:**
- #1–2 → ActionItemCreateView from Meeting Detail (with pre-filled data from AgendaItem) + standalone.
- #3–4 → Assignee formset with primary/supporting toggle.
- #5–9 → Fields on model + forms + service transitions.
- #10–13 → Blocker/next_steps fields + complete/reopen DAG with mandatory reason.
- #14 → Overdue computed property `is_overdue = due_date < now AND status != COMPLETED/CANCELLED` plus overdue_age_days.
- #15 → ListView filterset (status, priority, department, assignee, due_range, search text).
- #16–18 → 3 dedicated pages: My Actions / Department Actions / Overdue Actions.
- #19 → Dashboard KPI cards (total open, assigned to me, overdue, this-week-due) + next-8 overdue table, and in dashboard helper.
- #20 → CarryForwardForm + preview modal + execution service.

**Carry-forward hard contract (Phase4.md items 37–44):**
(1) new FK-carried_forward_from (ActionItem self-ref) + ActionItemCarryForwardLink;
(2) history preserved = carry-forward link + each ActionItemUpdate gets copied as a read-only "Carried from original" entry;
(3) default skip COMPLETED + CANCELLED (UI shows checkboxes allowing user to override "carry completed too");
(4) idempotent via carrying_action UNIQUE(source, target_meeting_or_none, item) so re-running same carry-forward 5× creates only 1 record;
(5) wrapped in transaction.atomic(); IntegrityError → rollback + return empty list;
(6) AuditLog(ACTION_CARRY_FORWARD, reason="Carried from…") per item.

**Required tests (Phase4.md items 46–54):**
- Overdue logic: due_date last week + open → overdue=True; completed last week → no; due future → no.
- Completion: requires primary assignee OR admin; progress=100; blocks empty (optional enforcement in service).
- Reopening: closed → IN_PROGRESS requires non-empty reason; writes audit REOPEN + history row.
- Object-level perms: user can only edit items they own, are primary/supporting assignee on, or are admin/meeting author on the originating meeting; Viewer read-only.
- Carry-forward: verify FK link, verify COMPLETED skipped by default, verify idempotency (2× post → 1 record), verify atomic rollback.
- Duplicate: same user + same title + open status doesn't prevent but carry-forward de-dupes by link.
- Progress validation: progress_pct 0..100 in form clean + model clean(); completed forces 100; reopen allows any 0..99.

### Existing scaffolding (what's in the repo already — empty)
- `apps/action_items/`: [__init__.py](../apps/action_items/__init__.py) empty; [apps.py](../apps/action_items/apps.py) exists (BigAutoField default); models/views/urls/admin empty; migrations/__init__.py empty.
- `templates/action_items/`: directory listed in project_structure.txt but empty.

## Files and Modules

| File | Expected Change |
|---|---|
| `apps/action_items/models.py` | 6 models + 7 action status constants + 4 priority constants + 2 upload_to path functions. |
| `apps/audit/models.py` | Add `ACTION_COMPLETE`, `ACTION_REOPEN`, `ACTION_CARRY_FORWARD` to `ACTION_CHOICES` (3 new entries, 12 total). |
| `apps/audit/migrations/0003_*` | Auto-generated migration expanding `AuditLog.action` CharField choices. |
| `apps/core/permissions.py` | Append `ACTION_AUTHOR_ROLES`, `ACTION_VIEWER_ROLES`, `ACTION_REOPEN_ROLES` tuples; 5 predicates `can_create_actionitem`, `can_edit_actionitem`, `can_complete_actionitem`, `can_reopen_actionitem`, `can_view_actionitem`; 2 mixins `ActionItemAuthorRequiredMixin`, `ActionItemCompleteMixin`. |
| `apps/core/templatetags/permissions.py` | 5 new template tags for action-item permissions (mirror meetings pattern). |
| `apps/action_items/services.py` | New file: `generate_action_reference()` retry-loop, `transition_actionitem()` DAG validator+atomic+history+audit, `carry_forward_action_items()` service (implements 6-part carry contract), `dashboard_action_counts(user)`, overdue query helpers. |
| `apps/action_items/signals.py` + `apps.py` | `pre_save` hook auto-filling `ActionItem.reference` using `generate_action_reference()`; apps.ready() imports signals. |
| `apps/action_items/forms.py` | New file: 9 form classes (ActionItemCreate/Update/Transition/CarryForward/Complete/Reopen + ActionItemUpdateForm + ActionItemAttachmentForm) + `build_assignees_formset()` factory with `_construct_form` monkey-patch. |
| `apps/action_items/views.py` | ~20 views: list/filter, detail, create (standalone + from-agenda-item), update, delete, complete, reopen, update-add, attachment-upload/delete, carry-forward, 3 dedicated views (My/Dept/Overdue), carry-forward-exec POST. |
| `apps/action_items/urls.py` | ~20 named routes using `<uuid:pk>` URL converters under "actions/" prefix + namespaced `action_items:`. |
| `apps/action_items/admin.py` | Register all 6 models with read-only inlines for StatusHistory + Updates + Attachments + Assignees. |
| `templates/action_items/*.html` | ~9 templates: list (with filter sidebar), detail (4 tabs — Overview / Updates / Attachments / History), form create/update, standalone complete modal, carry-forward preview, action_list_my.html, action_list_dept.html, action_list_overdue.html, partials/status_badges.html. |
| `templates/includes/sidebar.html` | Replace the 3 Actions-section `href="#"` with real URLs (action_items:actionitem_list / action_items:actionitem_overdue / action_items:actionitem_my). |
| `templates/includes/offcanvas.html` | Same sidebar Actions section mirrored. |
| `templates/dashboard/home.html` | Add second 4-card KPI row: "Open Actions", "Assigned to Me", "Overdue", "Due This Week" + "Next 8 Overdue" table (if any). |
| `apps/core/views.py` | Dashboard `home()` view: import `dashboard_action_counts` lazily (with try/except fallback), pass counts + top overdue list into home template. Add standalone `dashboard_action_counts()` helper (meetings style). |
| `tests/test_actionitem_models.py` | 10 tests: field defaults, reference unique, overdue logic, progress validation, status DAG edges, ActionItemAssignee primary/supporting, attachments upload_path, carried_forward link FK non-null, UNIQUE CarryForwardLink constraint. |
| `tests/test_actionitem_transitions.py` | 9 tests: DAG coverage, complete auto-set progress=100, reopen mandatory reason, reopen admin-only, reopen increments count, invalid transitions error, status history rows audit, 2 concurrent transitions serialize. |
| `tests/test_actionitems_permissions.py` | 8 tests: predicates, Viewer can't edit, Department Contributor can edit their own + assigned items, 403 response on delete, confidential redaction carried forward, admin override, 3 object-level scenarios. |
| `tests/test_actionitems_views.py` | 12 tests: create standalone, create from agenda-item (prefill), list filters (status/priority/search), assignee formset, upload+delete attachment, complete view, reopen view with+without reason, carry-forward preview+exec, my/dept/overdue pages return 200, dashboard counts appear. |
| `tests/test_actionitem_carry_forward.py` | 6 tests: default skips completed/cancelled, carry-with-override includes completed, carry idempotent 2× post → 1, carry preserves FK link back to source, carry copies history entries, carry rolls back when FK references missing. |
| `docs/permissions.md` | Append "Action Items Role Matrix" with roles × actions table, non-editable statuses, object rules. |
| `docs/workflows.md` | Append "§9 Action Item Lifecycle" and "§10 Carry-Forward" sections. |
| `docs/actionitem_status_transitions.md` | New file: 7×7 adjacency matrix for statuses, reason/admin requirements, flow diagram. |

## Implementation Steps (dependency-ordered)

1. **Scaffold models + constants** in `apps/action_items/models.py` (6 models + STATUS + PRIORITY constants + module-level CHOICES tuples, NOT class attrs). Statuses (Phase4.md #7,#12,#13,#27): `OPEN`, `IN_PROGRESS`, `BLOCKED`, `COMPLETED`, `CANCELLED`, `REOPENED` (transient) → actually 7 canonical: `OPEN, IN_PROGRESS, BLOCKED, COMPLETED, CANCELLED, UNDER_REVIEW, REOPENED`. Non-editable terminal statuses = {COMPLETED, CANCELLED} (lock all fields except by admin for UNDO). Add NON_EDITABLE_STATUSES set.
2. **Expand AuditLog.action:** edit [apps/audit/models.py](../apps/audit/models.py) action choices to add ACTION_COMPLETE, ACTION_REOPEN, ACTION_CARRY_FORWARD. Run `makemigrations audit` to generate `0003_alter_auditlog_action.py`. Apply `migrate` locally so tests work.
3. **Permissions layer:** Extend [apps/core/permissions.py](../apps/core/permissions.py) with role tuples, 5 predicates, 2 mixins. Extend [apps/core/templatetags/permissions.py](../apps/core/templatetags/permissions.py) with 5 new tags + a "is_primary_assignee" predicate.
4. **Services + signals:** Write [apps/action_items/services.py](../apps/action_items/services.py) with `generate_action_reference()` (3-attempt retry, prefix like `{code}-{year}-`, code default `ACT` unless carrying meeting-type-based `MRG-2026-AI-012` — keep simple for now: `ACT-{year}-NNNN`). Write `transition_actionitem(item, target, by_user, reason="", skip_role_check=False)` with the same fresh-fetch + select_for_update pattern as meetings. Write `carry_forward_action_items(source_items, target_meeting=None, include_completed=False, include_cancelled=False, by_user=None)`. Write 3 overdue / dashboard helpers. Write signals.py + apps.py ready() wire.
5. **Forms:** Write [apps/action_items/forms.py](../apps/action_items/forms.py) — 9 forms, assignee inline formset, progress clean(), reopen clean() requiring reason. DateTimeLocalInput widget mirror meetings for due date.
6. **Views + URLs:** Write views.py (~20 CBVs) + urls.py (~20 named `<uuid:*>` routes). All `redirect(...) + "#anchor"` patterns must use the `reverse()+"#anchor"` form (the bug from Phase 3 — don't repeat!). All list views use `LoginRequiredMixin`, object views use `ActionItemAuthorRequiredMixin`.
7. **Admin:** Register all 6 models.
8. **Templates:** 9 templates + 1 partials (status badges). Tab navigation on detail. Copy meetings Bootstrap-5.3 mobile-first layout so pattern is consistent.
9. **Navigation + Dashboard:** Sidebar Actions links (3), offcanvas mirror, dashboard 4 new KPI cards + overdue table, core/views home() integration (lazy import fallback so startup not fragile if action_items import fails single).
10. **Tests (6 modules):** Write all 6 test modules; target 80+ tests; run until all pass.
11. **Verification:** `manage.py check`, `makemigrations --check`, `pytest tests/` (phase3+4 cumulative ≥240 passing expected), `ruff check` + `ruff format`. Fix issues.
12. **Docs:** Permissions append (role matrix + object rules), Workflows append §9-§10, Create actionitem status transition matrix doc.

## Dependencies and Considerations

- **UUID PKs:** ActionItem is UUID. Assignees FK User (BigInt) is fine.
- **Carry-forward idempotency:** `ActionItemCarryForwardLink` must have explicit `Meta.unique_together = [("source_item", "target_meeting", "target_scope_key")]` where `target_scope_key` is a CharField hashable key defaulting to `"default"` so carry-forward with different "include_completed=False" vs True yields different records (reasonable).
- **Meeting → AgendaItem → ActionItem chain:** When creating ActionItem from AgendaItem, populate `source_agenda_item`, `source_meeting`, title=agenda.title, description=f"From {meeting.reference} — {agenda.discussion}", primary_assignee=agenda.owner (if set), due_date=meeting.start_at + 14 days default, department=agenda.department or meeting.department. All editable in the form after.
- **Progress auto-advance:** service `transition_actionitem(item, COMPLETED)` sets progress_pct=100 if not already. transition to IN_PROGRESS from OPEN sets min progress=10 if user set 0. Form clean enforces 0 ≤ progress_pct ≤ 100.
- **Overdue calculation:** Using `@property def is_overdue(self): return (self.due_date is not None) and (self.status not in {COMPLETED, CANCELLED}) and (self.due_date < timezone.now().date())`. With `overdue_age_days` = max(0, (today - due_date).days) if overdue else 0.
- **Dual edit locking:** ActionItem in {COMPLETED, CANCELLED} is non-editable — apply same 4-layer defense pattern as meetings NON_EDITABLE_STATUSES (property → form → view dispatch 403 → template hide buttons). Only admin can re-open (service re-opens first, then edits are allowed again on the IN_PROGRESS state).
- **AuditLog.record_type convention:** meetings used `"meetings.meeting"`, `"meetings.agendaitem"`, etc. Actions use: `"action_items.actionitem"`, `"action_items.assignee"`, `"action_items.update"`, `"action_items.attachment"`.
- **Test transaction markers:** Any test that asserts on AuditLog written via `transaction.on_commit` needs `@pytest.mark.django_db(transaction=True)` because in non-transactional DjangoTestCase on_commit never fires.
- **Django default `ATOMIC_REQUESTS = True` globally — remember carry-forward + transitions already atomic; nested atomic() is fine but make sure outer view-level decorator doesn't swallow integrity errors (we re-raise them).**

## Validation

After step 11 (cumulative):

| Check | Expected |
|---|---|
| `pytest tests/ --tb=short` | 240+ tests passing; 0 failures (Phase3=161 + Phase4 target 80+ = ≥241). |
| `python manage.py check` | 0 issues. |
| `python manage.py makemigrations --check` | No changes detected. |
| `ruff check apps config tests manage.py` | All checks passed (0 errors). |
| `ruff format --check apps config tests manage.py` | 100% files already formatted. |
| Manual smoke (optional) | Superuser: create ActionItem, complete it, reopen with reason, carry forward from monthly meeting 1 → monthly meeting 2 (skips completed by default), Viewer sees 403 on delete, 403 on transition past noneditable status. |

## Risks

1. **AuditLog.action CharField length** — if current field is `CharField(max_length=20)`; adding 3 more choices → OK. If too short, migration will fail. Mitigation: check current `apps/audit/models.py` first before running makemigrations.
2. **TimeStampedModel ordering = ["-created_at"]** — if ActionItem list views need custom priority+due ordering they must override `queryset.order_by(...)` explicitly; class Meta on model will override abstract default if defined. Good.
3. **Duplicate carry-forward records** — if unique_together scopes too narrowly (e.g. missing target scope key), user running 2 different carry-forwards to different targets collides. Mitigation: include explicit target_scope_key/meeting FK in unique constraint.
4. **Progress_pct integer or decimal?** Use `PositiveSmallIntegerField(validators=[MaxValueValidator(100)])` so Django enforces 0..100 DB-level (SQLite smallint allows 0..32767; MaxValueValidator is app-level, double check).
5. **Assignee de-dupe** — ActionItemAssignee `unique_together = [("action_item", "user")]` — users can't be both primary and supporting; add formset clean that prevents duplicate user across rows, catches IntegrityError in service.
6. **Lazy import failures on dashboard** — wrap action imports in try/except like meetings pattern, returning default dicts if fails. If any helper breaks startup, home still renders with 0 counts.
