# Permissions & Role Matrix

## Overview

Authorization in the intranet follows **Role-Based Access Control (RBAC)** using
Django's built-in `Group` and `Permission` system, augmented with object-level
scoping (department-level contributor checks) and a set of reusable view mixins
and template helpers.

The security model is intentionally *multi-layered*: permission checks run at
the view layer, the form layer, and again in the template layer for visibility.
Hiding a button/link in the UI is **never** the sole enforcement mechanism.

## Role Groups (6 Standard Roles)

Groups are created idempotently by the `seed_roles` management command (see
below). A user may be a member of **multiple groups** — permissions are the
*union* of all group memberships plus any per-user `user_permissions` rows and
the Django `is_superuser` flag (which short-circuits every check).

| Role Name                | Intended User                          | Core Capabilities                                                                                             |
|--------------------------|----------------------------------------|---------------------------------------------------------------------------------------------------------------|
| **System Administrator** | IT / central team                      | Full CRUD on User, Department, Position, ManagementTeam, *Membership rows, plus view on AuditLog.              |
| **Management Administrator** | HR / Office manager             | Create/edit users, edit assignments, view audit. Cannot edit Department/Position masters directly (System only).|
| **Meeting Chairperson**  | Person running each management meeting | View users & org chart + edit department assignments (so chairs can adjust contributor lists).                 |
| **Minutes Secretary**    | Person taking minutes                  | View users & org chart. Read-only baseline for meeting workflow (meeting-level perms added in Phase 3+).        |
| **Department Contributor**| Staff submitting updates             | View users & org chart. Scoped **only to their assigned departments** for any Phase 3+ object-level actions.  |
| **Viewer**               | Read-only observer                     | View users & org chart. No write access anywhere.                                                             |

## Permission Helper Predicates

Defined in `apps/core/permissions.py`. All predicates short-circuit on
`is_superuser=True` and require the user to be both *authenticated* and
*active* (`is_active=True`). Inactive users return `False` from every
predicate even if they have DB rows in the `Group` join table.

- `is_system_admin(user)` — member of **System Administrator**.
- `is_management_admin(user)` — member of **Management Administrator**.
- `is_meeting_chair(user)` — member of **Meeting Chairperson**.
- `is_minutes_secretary(user)` — member of **Minutes Secretary**.
- `is_department_contributor(user)` — member of **Department Contributor**.
- `is_viewer(user)` — member of **Viewer**.
- `can_manage_users(user)` — **System Administrator** OR **Management Administrator**.
- `can_manage_department_assignments(user)` — `can_manage_users` OR **Meeting Chairperson**.
- `user_in_department_contributors(user, department)` — active contributor membership for that specific department.

## `User` Model Helpers

Defined in `apps.accounts.models.User`:

```python
user.has_role(*group_names: str) -> bool         # union check; cached per-request, cleared on save()
user.get_assigned_departments(active_only=True)  # all Department rows the user is a member of
user.get_primary_department()                    # first DepartmentMembership with is_primary=True AND is_active
user.get_contributor_departments()               # departments where the user is an active contributor
user.can_manage_users()                          # shortcut for system or management admin
```

## View Mixins & Decorator

Use these instead of writing inline `if user.has_role(...)` checks in views.

### Class Based Views (CBV)

```python
from apps.core.permissions import (
    RoleRequiredMixin,
    ManagementRoleRequiredMixin,
    UserManagementRequiredMixin,
    DepartmentAssignmentManagementRequiredMixin,
    DepartmentContributorRequiredMixin,
)
```

- `RoleRequiredMixin(required_roles=[...])` — requires user has at least one listed role.
- `ManagementRoleRequiredMixin` — preconfigured for `System Admin | Management Admin | Meeting Chair`.
- `UserManagementRequiredMixin` — preconfigured for `System Admin | Management Admin` (user CRUD).
- `DepartmentAssignmentManagementRequiredMixin` — preconfigured for `System Admin | Management Admin | Meeting Chair`.
- `DepartmentContributorRequiredMixin` — **object-level**: the URL must pass `department_pk` or the view must override `get_department()`. Returns `403` if the user is not a contributor for that specific department.

### Function Based Views (FBV)

```python
from apps.core.permissions import group_required

@group_required("System Administrator", "Management Administrator")
def my_view(request):
    ...
```

Redirects anonymous users to `LOGIN_URL`; raises `PermissionDenied` (403) for
authenticated users without any of the named roles.

## Template Tags

Library name: `permissions`. Tags use `takes_context=True` and prefer
`context['user']` with fall-back to `context['request'].user` so they work in
navbar/offcanvas/sidebar render contexts that may not have the auth
context-processor user exposed.

```django
{% load permissions %}

{% has_role user "Management Administrator" as is_mgmt_admin %}
{% can_manage_users_tag as can_manage_users %}
{% can_manage_department_assignments_tag as can_assign %}
{% is_system_admin as is_sysadmin %}
{% is_management_admin as is_mgmt %}
{% is_meeting_chair as is_chair %}
{% is_minutes_secretary as is_sec %}
{% is_department_contributor as is_contrib %}
{% is_viewer as is_viewer %}

{% if can_manage_users %}<a href="{% url 'accounts:user_list' %}">Users</a>{% endif %}
{% if some_department in_assigned_departments user %}...{% endif %}
{% if some_department in_contributor_departments user %}...{% endif %}
```

**Important:** use these tags only for *UI visibility*. All restricted routes
must also be gated by a view mixin/decorator.

## Department Contributor Scoping

A "Department Contributor" only gains object-level access to resources
belonging to departments where their `DepartmentMembership` row has
`is_active=True AND is_contributor=True`. The role group name alone does NOT
grant system-wide contributor authority. Implementations of per-department
object views must use `DepartmentContributorRequiredMixin` or the
`user_in_department_contributors` predicate.

## Inactive User Lockout

- `is_active=False` on the `User` model returns `False` from every role check
  and returns an empty `get_contributor_departments()` queryset.
- The Django authentication backend already rejects login for inactive users.
- The `DepartmentMembershipForm.clean()` validator rejects submissions that
  would activate an assignment row when the assignment **owner** (the target
  user, not the admin submitting the form) is `is_active=False`. Re-activate
  the user first, then activate assignments.

## Audit Event Catalog

Every authorization-relevant write is recorded in `apps.audit.models.AuditLog`.
Standard action strings:

| Action   | When                                                                 |
|----------|----------------------------------------------------------------------|
| CREATE   | User / membership / other entity is created                          |
| UPDATE   | Entity fields change (diff stored in `changes` JSON)                 |
| DELETE   | Entity is removed                                                    |
| APPROVE  | Approval gating (Phase 3+)                                           |
| PUBLISH  | Publication gating (Phase 3+)                                        |
| LOGIN    | Successful user login (includes `ip_address`)                        |
| LOGOUT   | User logout                                                          |
| ASSIGN   | Department / management team membership rows edited inline formset   |
| ROLE     | `Group` memberships added or removed from a user                     |

### The `log_audit_event` Service

```python
from apps.audit.services import log_audit_event

log_audit_event(
    record_type="accounts.user",
    record=user_instance,
    action="UPDATE",
    user=request.user,        # actor
    target_user=user_instance,
    ip_address=request.META.get("REMOTE_ADDR"),
    previous_values=old_dict,
    new_values=new_dict,
    reason="is_active toggle by admin",
    immediate=False,          # defers write to transaction.on_commit (default)
)
```

Use `immediate=True` for events fired during signal handlers that run when
the ORM object may no longer exist (post_delete) or when the transaction is
closing (user_logged_in / user_logged_out).

## `seed_roles` Management Command

```bash
python manage.py seed_roles            # safe/idempotent; additive only
python manage.py seed_roles --reset-perms   # clears existing per-group perms first
```

- Creates 6 `Group` rows (see table above) if they do not exist.
- Adds the baseline `accounts.*` and `audit.*` permissions to each group.
- **Never removes** existing group-memberships; additive-only perms unless
  `--reset-perms` is explicitly passed.

Run this once in every environment (dev, staging, prod) after migrations, and
again after adding new models that should be covered by the baseline
permission matrix.

---

## Meetings Domain Role Matrix (Phase 3+)

The following table defines which roles can perform actions on Meetings,
Attendance rows, and Agenda Items. All actions additionally require the user
to be **both authenticated (`is_authenticated=True`) and active
(`is_active=True`)**. The meeting `created_by` (owner) always has author-level
privileges equivalent to "Meeting Chairperson" for their own meetings even if
they are not in that group (see `MEETING_AUTHOR_ROLES`).

| Action                                   | Sys Admin | Mgmt Admin | Meeting Chair | Minutes Sec | Dept Contributor | Viewer | Meeting Owner (created_by) |
|------------------------------------------|-----------|------------|---------------|-------------|------------------|--------|----------------------------|
| View published meeting list              | ✅         | ✅          | ✅             | ✅           | ✅                | ✅      | ✅                          |
| View draft / confidential meetings       | ✅         | ✅          | ✅ own dept    | ✅ own dept  | ✅ own dept       | ❌      | ✅ (own)                    |
| **Create** new meeting                   | ✅         | ✅          | ✅             | ❌           | ❌                | ❌      | —                          |
| Edit meeting (title, date, type)         | ✅         | ✅          | ✅ owner only  | ✅ owner     | ❌                | ❌      | ✅ (only if editable status) |
| Delete meeting (draft only)              | ✅         | ✅          | ✅ owner only  | ❌           | ❌                | ❌      | ✅ (draft only)             |
| Archive / Un-archive meeting             | ✅         | ✅          | ❌            | ❌           | ❌                | ❌      | ❌                          |
| Edit Attendance rows                     | ✅         | ✅          | ✅ owner only  | ✅ owner     | ❌                | ❌      | ✅                          |
| Edit Agenda Categories / Items / Order   | ✅         | ✅          | ✅ owner only  | ✅ owner     | ❌                | ❌      | ✅                          |
| Upload / delete Attachments (meeting)    | ✅         | ✅          | ✅ owner only  | ✅ owner     | ❌                | ❌      | ✅                          |
| Upload / delete Attachments (agenda)     | ✅         | ✅          | ✅ owner only  | ✅ owner     | ❌                | ❌      | ✅                          |
| Carry-forward agenda from past meeting   | ✅         | ✅          | ✅ owner only  | ✅ owner     | ❌                | ❌      | ✅                          |
| Status transition → APPROVED             | ✅         | ✅          | ❌            | ❌           | ❌                | ❌      | ❌                          |
| Status transition → PUBLISHED            | ✅         | ✅          | ❌            | ❌           | ❌                | ❌      | ❌                          |
| Return-for-correction (→ RETURNED)       | ✅         | ✅          | ❌            | ❌           | ❌                | ❌      | ❌                          |
| All other transitions (DRAFT↔OPEN→FINAL…)| ✅         | ✅          | ✅ owner only  | ✅ owner     | ❌                | ❌      | ✅ (with editable rules)    |
| View Confidential agenda items (detail)  | ✅         | ✅          | ✅ owner only  | ✅ owner     | ❌ (rendered `[Confidential]`) | ❌ | ✅ plus their dept head |
| Request transition reason field          | —         | —          | —             | —           | —                | —      | —                          |

### Non-Editable Status Lock (4-Layer Defense)

A meeting whose `status` is in `NON_EDITABLE_STATUSES = {APPROVED, PUBLISHED,
CLOSED, ARCHIVED}` is locked against direct field edits. Enforcement happens
in four independently-true places so template-only bypass is impossible:

1. **Model property** — `Meeting.is_editable` returns `False`; service-layer
   helpers in forms/views read this first.
2. **Form layer** — `MeetingForm.__init__()` sets every widget
   `disabled=True` and help text to a locked notice; `MeetingForm.clean()`
   additionally raises `ValidationError` if any data changed.
3. **View dispatch** — `can_edit_meeting(user, meeting)` returns `False` so
   `MeetingAuthorRequiredMixin.dispatch()` returns `403 PermissionDenied`
   before any handler runs.
4. **Template layer** — "Edit meeting" button and in-place form fields are
   wrapped in `{% if can_edit_meeting %}…{% endif %}` guards so users don't
   click dead links.

The ONLY way to advance a meeting past NON_EDITABLE_STATUSES is through the
status-transition flow (DAG-validated by `transition_meeting` service; writes
a `MeetingStatusHistory` row plus an `AuditLog.ACTION_TRANSITION` event).

### Meetings Permission Predicates (apps.core.permissions)

```python
from apps.core.permissions import (
    MEETING_AUTHOR_ROLES,           # System/Mgmt Admin, Meeting Chair, Minutes Sec
    CONFIDENTIAL_VIEWER_ROLES,      # System/Mgmt Admin, Meeting Chair, Minutes Sec
    REOPEN_AUTHORIZED_ROLES,        # System/Mgmt Admin — ARCHIVE + RETURNED gates

    can_create_meeting(user),
    can_edit_meeting(user, meeting),
    can_transition_meeting(user, meeting),
    can_archive_meeting(user, meeting),
    can_view_confidential_items(user, meeting),

    MeetingAuthorRequiredMixin,     # CBV mixin — dispatch-level author/edit gate
    ArchiveAuthorizedMixin,         # CBV mixin — only System/Mgmt Admin
)
```

### Meetings Template Tags

New tags in the `permissions` library (Phase 3). All accept an optional
meeting object parameter:

```django
{% load permissions %}

{% can_create_meeting_tag as can_create %}
{% can_edit_meeting_tag meeting as can_edit %}
{% can_transition_meeting_tag meeting as can_transition %}
{% can_archive_meeting_tag meeting as can_archive %}
{% can_view_confidential_items_tag meeting as can_see_secret %}

{% if can_edit %}<button>Edit meeting</button>{% endif %}
{% if not can_see_secret %}<em>[Confidential]</em>{% else %}{{ item.decision }}{% endif %}
```

### Meetings Audit Events (extensions)

Added to `apps.audit.models.AuditLog.action` choices in migration
`audit.0002_alter_auditlog_action`:

| Action      | When                                                              |
|-------------|-------------------------------------------------------------------|
| TRANSITION  | `transition_meeting()` moves status; `reason` stored + diff.      |
| ARCHIVE     | Meeting transitions to `ARCHIVED` (also captured as TRANSITION). |

Combined with the existing CREATE / UPDATE / DELETE / APPROVE / PUBLISH /
ASSIGN / ROLE / LOGIN / LOGOUT entries, every meeting-domain write produces
an `AuditLog` row that survives entity deletion (user FK is `SET_NULL` on
delete so audit logs outlive actors).

## Action Items Domain Role Matrix (Phase 4+)

The following table defines which roles can perform actions on Action Items.
All actions require the user to be **both authenticated and active**.
Related users (owner, created_by, any assignee, or source-meeting chair) are
granted view/edit privileges beyond their role group via
`_action_item_user_is_related()` in `apps.core.permissions`.

| Action                                   | Sys Admin | Mgmt Admin | Meeting Chair | Minutes Sec | Dept Contributor | Viewer | Related User (owner/assignee) |
|------------------------------------------|-----------|------------|---------------|-------------|------------------|--------|-------------------------------|
| View visible action list (dept-scoped)   | ✅ all    | ✅ all      | ✅ own dept   | ✅ own dept | ✅ own dept     | ✅ own dept | ✅ own records              |
| **Create** action item                   | ✅         | ✅          | ✅             | ✅           | ✅                | ❌      | —                             |
| Edit fields (title/due/priority/body)    | ✅         | ✅          | ✅             | ✅           | ✅ owner only     | ❌      | ✅ owner only (if editable)  |
| Change assignees (primary/supporting)    | ✅         | ✅          | ✅             | ✅           | ✅ owner only     | ❌      | ✅ owner only (if editable)  |
| Delete action item                       | ✅         | ✅          | ❌            | ❌           | ❌                | ❌      | ❌                            |
| Add comment / Update post                | ✅         | ✅          | ✅             | ✅           | ✅                | ❌      | ✅ related users             |
| Upload / delete attachment               | ✅         | ✅          | ✅ owner       | ✅ owner     | ✅ owner only     | ❌      | ✅ owner (if editable)       |
| **Status transition** (non-terminal)     | ✅         | ✅          | ✅ owner       | ✅ owner     | ✅ owner only     | ❌      | ✅ owner (DAG + reason gated)|
| **Mark COMPLETE** (transition → COMPLETED) | ✅       | ✅          | ✅             | ✅           | ❌                | ❌      | ❌ requires role             |
| **RE-OPEN** (COMPLETED/CANCELLED→REOPENED)| ✅ only   | ✅ only     | ❌            | ❌           | ❌                | ❌      | ❌ requires admin role       |
| Bulk carry-forward in list view          | ✅         | ✅          | ✅             | ✅           | ❌                | ❌      | —                             |
| View Overdue / My Assignments tabs       | ✅         | ✅          | ✅             | ✅           | ✅                | ❌      | ✅                           |

### Action Items Non-Editable Status Lock (4-Layer Defense)

`NON_EDITABLE_STATUSES = TERMINAL_STATUSES = {COMPLETED, CANCELLED}`. An
action item whose status enters either terminal state becomes fully locked.
Enforcement mirrors the Meetings 4-layer contract:

1. **Model property** — `ActionItem.is_editable` returns `False`.
2. **Form layer** — `ActionItemUpdateForm.__init__()` disables all widgets and
   injects a lock notice; `clean()` also rejects any mutated data.
3. **View dispatch** — `ActionItemAuthorRequiredMixin.test_func()` calls
   `can_edit_actionitem()` which returns `False` for terminal items before
   any POST/GET handler runs, returning `403 PermissionDenied`.
4. **Template layer** — detail template `actionitem_detail.html` wraps the
   Edit, Save-assignees, and Transition buttons in
   `{% if can_edit_actionitem %}` guards and renders a `Locked` status badge.

The ONLY permitted escape from the terminal lock is **RE-OPEN via admin
transition**: a user holding System Administrator OR Management Administrator
role (with a non-empty `reason`) can post to `action_reopen` route, which
calls `transition_actionitem(item, STATUS_REOPENED, …)` internally. This
writes an `ActionItemStatusHistory` row plus an `AuditLog.ACTION_REOPEN`
event with the mandatory reason captured.

### Action Items Permission Predicates (apps.core.permissions)

```python
from apps.core.permissions import (
    ACTION_AUTHOR_ROLES,       # (SysAdm, MgmtAdm, Chair, Sec, DeptContrib)
    ACTION_VIEWER_ROLES,       # (*ACTION_AUTHOR_ROLES, ROLE_VIEWER)
    ACTION_REOPEN_ROLES,       # (SysAdm, MgmtAdm)
    ACTION_COMPLETE_ROLES,     # (SysAdm, MgmtAdm, Chair, Sec)

    can_create_actionitem(user),
    can_view_actionitem(user, action_item),
    can_edit_actionitem(user, action_item),        # False for terminal status
    can_complete_actionitem(user, action_item),
    can_reopen_actionitem(user, action_item=None), # role-only (role gate)

    ActionItemAuthorRequiredMixin,  # CBV mixin: dispatch + owner/role edit gate
    ActionItemCompleteMixin,        # CBV mixin: dispatch + complete role gate
)
```

### Action Items Template Tags

New tags in the `permissions` library (Phase 4). Follow the same
`_user_from_context` pattern as meeting tags (no `user` arg in templates):

```django
{% load permissions %}

{% can_create_actionitem_tag as can_create %}
{% can_view_actionitem_tag action_item as can_view %}
{% can_edit_actionitem_tag action_item as can_edit %}
{% can_complete_actionitem_tag action_item as can_complete %}
{% can_reopen_actionitem_tag as can_reopen %}
```

### New Audit Actions (Phase 4 — audit.0003)

`apps.audit.models.ACTION_CHOICES` expanded from 11 → 14 entries:

| Action         | When                                                                 |
|----------------|----------------------------------------------------------------------|
| COMPLETE       | `transition_actionitem()` moves status to `COMPLETED`.              |
| REOPEN         | `transition_actionitem()` moves `COMPLETED`/`CANCELLED` → `REOPENED`. |
| CARRY_FORWARD  | `carry_forward_action_items()` creates a new linked action item.     |

## Sales Role Matrix (Phase 5 — audit.0004 / sales_updates.0001)

### Sales Role Groups

Four role tuples govern the Sales data module (defined in
`apps/core/permissions.py`). Capabilities are *unions* of roles, so a System
Administrator inherits every lower capability:

```
SALES_VIEWER_ROLES  = (SYS_ADMIN, MGMT_ADMIN, CHAIR, SECRETARY, DEPT_CONTRIBUTOR, VIEWER)
SALES_AUTHOR_ROLES  = (SYS_ADMIN, MGMT_ADMIN, CHAIR, SECRETARY, DEPT_CONTRIBUTOR)
SALES_EXPORT_ROLES  = (SYS_ADMIN, MGMT_ADMIN, CHAIR)
SALES_LOCK_ROLES    = (SYS_ADMIN, MGMT_ADMIN, CHAIR)
```

### Sales Capability × Role Matrix

| Capability                           | SysAdmin | MgmtAdmin | Chair | Secretary | DeptContr | Viewer |
|--------------------------------------|:--------:|:---------:|:-----:|:---------:|:---------:|:------:|
| View reporting periods               |    ✔     |     ✔     |   ✔   |     ✔     |     ✔     |   ✔    |
| View sales groups / team data        |    ✔     |     ✔     |   ✔   |     ✔     |     ✔     |   ✔    |
| View dashboard / snapshots / detail  |    ✔     |     ✔     |   ✔   |     ✔     |     ✔     |   ✔    |
| Create / edit reporting period       |    ✔     |     ✔     |   ✔   |     ✔     |     ✔     |   ✘    |
| Create / edit teams & groups         |    ✔     |     ✔     |   ✔   |     ✔     |     ✔     |   ✘    |
| Upsert Targets / Deliveries / Actuals|    ✔     |     ✔     |   ✔   |     ✔     |     ✔     |   ✘    |
| Save weekly commitments / snapshot   |    ✔     |     ✔     |   ✔   |     ✔     |     ✔     |   ✘    |
| Create snapshot (linked to meeting)  |    ✔     |     ✔     |   ✔   |     ✔     |     ✔     |   ✘    |
| **Export period to Excel XLSX**      |    ✔     |     ✔     |   ✔   |     ✘     |     ✘     |   ✘    |
| **Lock / edit-locked snapshot**      |    ✔     |     ✔     |   ✔   |     ✘     |     ✘     |   ✘    |
| Close / re-open reporting period     |    ✔     |     ✔     |   ✔   |     ✘     |     ✘     |   ✘    |

### Sales Predicates & Mixin

```python
# apps/core/permissions.py
can_view_sales_data(user)        # SALES_VIEWER_ROLES
can_edit_sales_period(user, period)  # SALES_AUTHOR_ROLES + period.status != CLOSED
can_export_sales_period(user, period) # SALES_EXPORT_ROLES
can_lock_sales_snapshot(user, snapshot) # SALES_LOCK_ROLES

class SalesEditRequiredMixin:     # LoginRequiredMixin + can_edit_sales_period check
    def dispatch(...): ...
```

### Sales Template Tags (Phase 5)

Simple tags registered in `apps.core.templatetags.permissions`:

```django
{% load permissions %}

{% can_view_sales_tag as can_view_sales %}
{% can_edit_sales_period_tag period as can_edit_period %}
{% can_export_sales_period_tag period as can_export_period %}
{% can_lock_sales_snapshot_tag snapshot as can_lock_snap %}
```

### New Audit Actions (Phase 5 — audit.0004)

`ACTION_CHOICES` expanded 14 → 16 entries:

| Action         | When                                                                      |
|----------------|---------------------------------------------------------------------------|
| LOCK           | `GroupPerformanceSnapshot.save()` fires when `is_snapshot_locked()` → T   |
| EXPORT         | `ExcelPeriodExport.get()` streaming response returns period XLSX to user  |

