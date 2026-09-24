# Phase 2 — Accounts, Organization, and Role-Based Access Implementation Plan

## Repository Research

### Phase 1 already provides
- `AUTH_USER_MODEL = accounts.User` (extends `AbstractUser`) with `display_name`, `initials`, `phone`, `signature_text`, `theme`, custom `UserManager` — migration `0001_initial` already applied.
- Organization models: `Department`, `Position`, `ManagementTeam`, `ManagementTeamMembership`, `DepartmentMembership` — all in `apps/accounts/models.py`. All inherit from `TimeStampedModel` (UUID PK) or `BaseNamedModel` (is_active flag, name, timestamps).
- `DepartmentMembership` has `is_primary`, `is_contributor` but **no `is_active` flag** (needed for requirement #7). `ManagementTeamMembership` similarly lacks `is_active`.
- Admin is configured in `apps/accounts/admin.py` with inlines.
- Split settings, templates, UI scaffold, 15 passing tests.

### Gaps against Phase 2 requirements
1. **User profile**: Model fields mostly exist, but no profile view/edit page, no avatar, no bio/middle initials/emergency fields.
2. **Active/inactive org assignments**: `DepartmentMembership.is_active` and `ManagementTeamMembership.is_active` missing.
3. **Groups/Permissions**: No code yet for the 6 pre-defined role groups (System Administrator through Viewer) and no Django permissions on our custom models.
4. **Permission tooling**: No reusable mixins/decorators for role checks or per-department authorization. No template permission helpers.
5. **User-management pages (non-admin UI)**: No user CRUD views outside `admin/`.
6. **Department assignment interface**: No view/page to manage department assignments + positions + contributor flag.
7. **Profile page**: Missing.
8. **Password-change flow**: Only Django defaults — no project templates, no success page wiring.
9. **Audit hooks**: `apps/audit/models.py` is empty. No signals for user, group, permission changes.
10. **Seeded groups**: No fixture/management command.
11. **Tests**: No permission-matrix, object-level authorization, department-access, inactive-user, or admin-access tests.
12. **Docs**: `docs/permissions.md` + docs/workflows + docs/architecture need to be created per MASTER_PROMPT (at least permissions, since phase explicitly calls out Update documentation).

## Files and Modules

### Accounts Models & Admin (edit existing)
- `apps/accounts/models.py` — add `DepartmentMembership.is_active`, `ManagementTeamMembership.is_active`; user helper methods (`get_primary_department()`, `get_assigned_departments(active_only=True)`, `has_role(*group_names)`, `is_inactive_sentinel()`); add organizational models clean `is_active` querysets.
- `apps/accounts/admin.py` — expose `is_active` on membership inlines; add groups filter/display to User; add membership inlines to User admin.
- `apps/accounts/forms.py` (NEW) — UserCreateForm, UserUpdateForm, DepartmentMembershipForm, ProfileUpdateForm, PasswordChangeForm subclass with validation that inactive users cannot receive new assignments.
- `apps/accounts/signals.py` (NEW) — audit-triggering signals for user save/delete, group save, M2M changes.
- `apps/accounts/management/commands/seed_roles.py` (NEW) — management command to idempotently create the 6 role Groups, assign reasonable Django permissions per matrix, plus a `User.has_role(...)`-compatible group naming convention.
- `apps/accounts/urls.py` (NEW) — routes for user list, user create/edit, profile, department assignments, password change.
- `apps/accounts/views.py` (NEW) — auth-required, permission-gated views: UserListView, UserCreateView, UserUpdateView, UserDeactivateView, ProfileView, ProfileEditView, DepartmentAssignmentListView, DepartmentAssignmentUpdateView, password_change views wiring.

### Audit app (NEW functionality)
- `apps/audit/models.py` — `AuditLog` with record_type, record_id, action (CREATE/UPDATE/DELETE/APPROVE/PUBLISH/LOGIN), user (FK nullable), IP, previous/new values (JSONField), reason, related_meeting (FK nullable), correlation_id, created_at.
- `apps/audit/admin.py` — read-only style admin for AuditLog (no mass delete, no inline edits, search + filters).
- `apps/audit/services.py` (NEW) — `log_audit_event(...)` service function with `transaction.on_commit` safety.
- `apps/audit/migrations/0001_initial.py` — generated.

### Core permissions + template helpers
- `apps/core/permissions.py` (NEW) — `RoleRequiredMixin`, `group_required` decorator, `DepartmentContributorRequiredMixin`, `is_system_admin`, `is_management_admin`, `is_meeting_chair`, `is_minutes_secretary`, `is_department_contributor`, `is_viewer` helpers.
- `apps/core/templatetags/__init__.py` (NEW) + `apps/core/templatetags/permissions.py` (NEW) — `{% has_role %}` tag, `in_assigned_departments` filter, `can_manage_users` simple tag.

### Templates (NEW accounts + auth)
- `templates/accounts/profile.html` — self profile viewer.
- `templates/accounts/profile_edit.html` — self profile editor.
- `templates/accounts/user_list.html` — paginated, searchable for admin+management admin + chair.
- `templates/accounts/user_form.html` — create/edit user with groups picker + basic info.
- `templates/accounts/department_assignments.html` — per-user dept assignments UI.
- `templates/registration/password_change_form.html`, `password_change_done.html`.
- `templates/components/user_badge.html` — reusable avatar+name component.
- Update `templates/includes/navbar.html` — add "Profile" menu link and "Change Password" link; add user-list link when user has permission.

### Tests (NEW)
- `tests/test_permission_matrix.py` — role-group check helpers + mixin behavior.
- `tests/test_object_authorization.py` — per-department contributor limits, inactive-user block, template-hidden-still-secure pattern.
- `tests/test_accounts_views.py` — user CRUD + profile pages + department assignment views + password change.
- `tests/test_audit_signals.py` — user/group change writes AuditLog.
- `tests/test_seed_roles_command.py` — idempotent `seed_roles`.

### Configuration & docs
- `config/urls.py` — include `apps.accounts.urls`, include password change URLs.
- `config/settings/base.py` — add `APP_DIRS` is true already; add `'django.contrib.auth.context_processors.auth'` is already there; just add `PASSWORD_RESET_TIMEOUT_DAYS` (or use Django default), `LOGIN_URL` already set.
- `docs/permissions.md` (NEW) — role matrix, department-scoped access rules, audit events list.
- `docs/workflows.md` (NEW, minimal) — user creation, department assignment, password change.

## Implementation Steps (dependency order)

1. **Accounts model additions** — add `is_active` to both memberships, add user helper methods. Generate `0002_*.py` migration.
2. **AuditLog model + service + signals** — `apps/audit/models.py`, `services.py`, wire accounts signals to call audit service. Generate `audit/0001_initial.py`.
3. **Seed-role groups management command** + `has_role` user method. Run once idempotently; never drop existing group assignments.
4. **Core permissions module + template tags** — mixins, decorators, helpers; register in `INSTALLED_APPS` templatetags discovery.
5. **Accounts forms** — UserCreateForm, UserUpdateForm, ProfileUpdateForm, DepartmentMembershipFormSet with inactive-user assignment guard.
6. **Accounts views + urls** — profile (view+edit), user CRUD (role-gated), department assignments (role-gated), password change wiring.
7. **Admin polish** — inlines in User admin for memberships; AuditLog read-only admin.
8. **Templates** — all 8 accounts/registration templates, plus navbar/sidebar updates.
9. **Documentation** — `docs/permissions.md`, `docs/workflows.md`.
10. **Tests** — 5 test modules (permission matrix, object-level auth, accounts views, audit signals, seed command).
11. **Verification** — `python manage.py check`, `makemigrations` (if any), `migrate`, `seed_roles`, `pytest`, `ruff check && ruff format`.

## Dependencies and Considerations

- **UUID PKs + foreign keys to User/Department** — all FKs from AuditLog to User/Department must support UUID. `User.pk` is UUID. `related_name` must not clash.
- **AUTH_USER_MODEL is already custom** — safe. Never change it; just add helpers.
- **Membership `is_active` default = True** — backward compatible. Set `db_index=True` because queries filter by it constantly.
- **Inactive user guard** — enforce in **forms + view mixin**, not only in template. MASTER_PROMPT rule: "Do not rely only on template hiding for security."
- **Department Contributor scoping** — helper `User.get_contributor_departments()` returns Departments where `DepartmentMembership.is_contributor=True and is_active=True and user.is_active=True`. Views use `.filter(department__in=user.get_contributor_departments())` pattern.
- **Idempotent seed_roles** — use `Group.objects.get_or_create(name=...)`; never DELETE existing groups so manual admin edits survive re-run.
- **Audit events via `transaction.on_commit`** — avoid logging rollback. Do not fail request if audit write fails (log to logger + swallow error).
- **Signals for Group/User/DepartmentMembership/ManagementTeamMembership** — `post_save`, `post_delete`, `m2m_changed` for `User.groups` + `User.user_permissions`.
- **6 Role Groups to permissions map** (conservative sensible defaults; expand later):
  - *System Administrator* — superuser-equivalent via `is_staff + is_superuser` + all custom model permissions.
  - *Management Administrator* — add/change/delete/view Meeting, Agenda, Attendance, ActionItem; add/change/view User + DepartmentMembership; view SalesUpdates; export; publish.
  - *Meeting Chairperson* — view Meeting + ActionItem; approve minutes; close meeting.
  - *Minutes Secretary* — create/update draft Meeting/Agenda/Attendance/ActionItem; cannot approve/publish.
  - *Department Contributor* — view assigned department update pages; CRUD own department update records; NO cross-department edits.
  - *Viewer* — view published minutes + dashboards; no create/update/delete.
- **Password change**: Use `django.contrib.auth.views.PasswordChangeView` + `PasswordChangeDoneView`; wrap with `@login_required`. Force logout other sessions? Keep simple (no invalidation) for Phase 2.
- **Django permissions naming**: `accounts.add_user`, `accounts.change_user`, `accounts.view_departmentmembership` etc. — auto-generated. We grant these in `seed_roles`.

## Validation

- `python manage.py check` — must pass.
- `python manage.py makemigrations` — if changes remain; run migrate.
- `python manage.py seed_roles` — success + re-run idempotent.
- `pytest` — all tests passing (should be 15 old + 15+ new ≥ 30 tests).
- `ruff check apps config tests manage.py && ruff format --check apps config tests manage.py`.
- **Manual smoke test**:
  - Create two users: one "Management Administrator" + one "Department Contributor" assigned only to Department "Sales".
  - Login as Contributor → dashboard works, user list access returns 403.
  - Attempt direct URL `/users/1/edit/` as Contributor → 403.
  - Password change via `/accounts/password/change/` works and redirects to `/accounts/password/change/done/`.
  - Deactivate Contributor (set `is_active=False`) → login fails with correct message.

## Risks

| Risk | Mitigation |
|---|---|
| Migration of `DepartmentMembership.is_active` on existing rows (none yet in Phase 1) | `default=True` so 0 rows = safe; add DB index. |
| `seed_roles` re-run breaks manually-assigned permissions | Use `get_or_create` + only **add** missing perms, never revoke. Document this behavior. |
| Role mixins accidentally block superusers | All mixins short-circuit: `if request.user.is_superuser: return True`. |
| Audit log table grows quickly | Add index on `(created_at, action, user_id)`; future Phase can add retention. |
| Membership `unique_together = [[user, dept]]` conflicts with `is_active` toggling | Keep it. To "re-add" user to same dept, flip `is_active=True` rather than create new row. The forms enforce this. |
| Contributors can hack URLs to edit other departments | Every object-modifying view checks `department in user.get_contributor_departments()`. Forms filtered by same queryset. Add regression test. |
| Template hiding alone gives false security | Add test asserting 403 returned even when direct URL hit without UI. |
