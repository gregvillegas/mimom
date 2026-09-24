# Operational Workflows

This document records the canonical user flows shipped with Phase 2. Steps
marked *[Phase 3+]* are placeholders; they describe how future phases connect
to the accounts foundation built here.

## 1. Onboarding a New User

Actors allowed: **System Administrator**, **Management Administrator**.

1. Open **Admin → New User** (or `Accounts → Users → New User`).
2. Fill in:
   - Username (required, unique, used as login id).
   - Email (required, unique, used for notifications).
   - First name, Last name (optional, auto-fills `display_name`).
   - Phone, Initials, Signature text (profile fields).
   - **Groups (roles):** select one or more of the 6 standard role groups
     (union-of-permissions semantics). If the new hire only needs to submit
     department updates, assign **Department Contributor** and nothing else.
   - `is_staff`: tick **only** if this user needs direct Django admin access
     (system-level configuration). Most users should NOT be staff.
   - `is_active`: leave ticked (default) for a normal onboarding; leave
     unticked if the person is onboarding but start date is in the future.
   - Password: set a strong temporary password. Communicate it out-of-band.
3. Save → system writes an `AuditLog` row with `action=CREATE`.
4. Immediately click **Assign Departments** on the saved user (or navigate to
   `Accounts → Users → the user → Department Assignments`).
5. For each department:
   - Pick the Department row.
   - Optionally pick a Position.
   - Mark **one** row `Is primary` (optional but recommended).
   - If the user should be able to submit department-level updates, tick
     **Is contributor**.
   - Leave `Is active` ticked.
6. Save the formset → system writes `AuditLog` row(s) with `action=ASSIGN`.

Hand-off to the new user:

1. Share the intranet URL, username, and the temporary password via a secure
   channel.
2. Instruct them to follow *Workflow 3 (Change Password)* on first login to
   rotate the temp password.

### Role to Assignment Mapping Cheatsheet

| Scenario                                       | Assign these groups                          | Department rows needed                                     |
|------------------------------------------------|----------------------------------------------|------------------------------------------------------------|
| Office admin (HR, creates users, edits roles)  | Management Administrator                     | 1 (their own department, primary=true, no contributor flag)|
| IT user that also maintains master data        | System Administrator                         | 1+ (as appropriate)                                        |
| Meeting chair (Sales director)                 | Meeting Chairperson                          | 1 (Sales, primary=true, is_contributor=true optional)      |
| Minutes secretary                              | Minutes Secretary                            | 0+ (they just read/type; no dept scoping required)         |
| Sales rep that submits sales updates           | Department Contributor                       | 1 (Sales, is_contributor=true)                             |
| Finance manager that needs to read meeting docs| Viewer                                       | 0+ (read only)                                             |

## 2. Re-assigning a Department or Changing Role

Actors allowed: **System Administrator**, **Management Administrator** (full
edit), **Meeting Chairperson** (edit department assignments only, not user
core fields/roles).

Steps (role change):
1. Navigate to `Accounts → Users → Edit`.
2. Modify the Groups selection (add or remove; the UI shows ticked groups).
3. Save → signal handler writes an `AuditLog` row with `action=ROLE` and the
   diff of group names added / removed.

Steps (department reassignment):
1. Navigate to `Accounts → Users → Department Assignments` (for the target user).
2. *Deactivate* the old row by unticking `Is active` on the old department.
   Do NOT delete the row — historical audit relies on the row existing with
   `is_active=False`.
3. Add a new row for the new department, ticking `Is primary` if needed and
   `Is contributor` if the user needs dept-scoped submit access.
4. Save → writes `action=ASSIGN` with per-row previous/new flags.

**Important anti-patterns** (don't do these):
- ❌ Do not try to infer a user's department from their Position title. The
  Position model is a label/level library; only `DepartmentMembership` rows
  grant department scope.
- ❌ Do not remove a user's last active role group *before* re-assigning. If
  you accidentally remove Management Administrator from your own account you
  will lock yourself out — keep a known System Administrator or superuser
  account available at all times.

## 3. Changing Your Own Password

Any authenticated active user.

1. Top-right user menu → **Change Password** (`/accounts/password/change/`).
2. Type the current password once, then the new password twice (Django's
  `AUTH_PASSWORD_VALIDATORS` run here — length, common-password, numeric-only
  checks are enforced by project settings).
3. Submit → the view calls `update_session_auth_hash()` so you stay signed
   in after the rotation (no force-logout).
4. Redirect to **Password Change Done** confirmation page. Audit event
   `action=UPDATE` on the user record with `previous_values.password`
   redacted (only a `*` sentinel is stored).

### Password Reset for Forgotten Passwords

*[Phase 4]* — the password-reset-email flow (`PasswordResetView` and
associated templates) will be added in the communications phase. Until then,
any System Administrator or Management Administrator can:
1. Edit the user (Accounts → Users → the user → Edit).
2. Click the "set a password" link on the edit form.
3. Set a temporary password and communicate it out-of-band.
4. Ask the user to rotate it on first login (Workflow 3).

## 4. Updating Your Profile

Any authenticated active user.

1. Top-right user menu → **My Profile**.
2. Click the **Edit Profile** button on the profile card.
3. Update Display name, Initials, Phone, Signature text, Theme (Auto/Light/Dark),
   and Bio (rich text via standard `<textarea>`; Phase 3+ adds WYSIWYG).
4. Save → writes `action=UPDATE` audit event (diff stored).

Viewing **another user's** profile (allowed for Management/System admins):
1. Accounts → Users → click their name → Profile view renders.
2. Edit button is rendered only if the viewer has `can_manage_users`.
3. Department Assignments / Manage Roles links are shown under the same gate.

## 5. Activating / Deactivating a User Account

Actors allowed: **System Administrator**, **Management Administrator**.

**Deactivating** (user is on leave, terminated, or long-term disabled):
1. Accounts → Users → Edit.
2. Untick `Active` and Save.
3. Immediate effects:
   - Next login attempt by the user is rejected by Django auth with the
     standard "inactive account" error.
   - The user's active session is NOT force-killed server-side, but they
     will fail every role check on the next request.
   - `User.has_role(...)` → always `False` regardless of group rows.
   - `User.get_contributor_departments()` → empty queryset.
   - Attempting to tick `Is active` on any of their department assignments
     raises a form validation error until the user is re-activated.
4. Audit writes `action=UPDATE` with `previous_values.is_active=True`,
   `new_values.is_active=False`.

**Re-activating** (returning user):
1. Accounts → Users → Edit → tick `Active`, Save.
2. (Optional) visit **Department Assignments** and re-tick `Is active` on the
   appropriate rows. Deactivated user's old rows are preserved but typically
   have `is_active=False` — you choose which to restore.
3. If their password was rotated while inactive, tell them to use the
   temporary one (see Workflow 3).

**Do NOT use `User.delete()` / the admin Delete action** unless you are
certain the row will never be referenced again. The `User` model is a
foreign-key target for `AuditLog`, Action Items, Meetings attendees, etc. —
deleting produces orphaned audit trails. Deactivate instead.

## 6. Direct URL Access Control Tests (Security Smoke Check)

To verify view-level gating (beyond template hiding), run these scenarios
from an incognito window. The paths are under `/accounts/` by default.

| As this user…          | Try accessing                                     | Expected status |
|------------------------|---------------------------------------------------|-----------------|
| Department Contributor | GET `/accounts/users/`                            | 403 Forbidden   |
| Department Contributor | GET `/accounts/users/<uuid>/edit/`                | 403 Forbidden   |
| Department Contributor | GET `/accounts/users/<uuid>/assignments/`         | 403 Forbidden   |
| Department Contributor | GET `/accounts/profile/` (their own)              | 200 OK          |
| Department Contributor | GET `/accounts/profile/<their-uuid>/`             | 200 OK          |
| Viewer                 | GET `/accounts/users/`                            | 403 Forbidden   |
| Viewer                 | GET `/accounts/password/change/`                  | 200 OK (can change their own pw) |
| Management Admin       | GET `/accounts/users/`                            | 200 OK          |
| Management Admin       | GET `/accounts/users/<any-uuid>/edit/`            | 200 OK          |
| *Logged out*           | GET `/accounts/users/`                            | 302 → LOGIN_URL (not 403) |

If any row returns the *opposite* of what's expected, check that the view
class inherits from the required mixin. The accounts views file
(`apps/accounts/views.py`) documents the gate for each view at the top of its
class docstring.

---

## 7. Standard Meeting Lifecycle (Phase 3)

Actors: **Meeting Chairperson**, **Minutes Secretary** or author (creator)
prepare everything; **System Administrator** or **Management Administrator**
perform APPROVE / PUBLISH / RETURNED gating.

Diagram of statuses and allowed edges. Details, admin gates, and reason
requirements are in `docs/meeting_status_transitions.md`.

```
DRAFT ─┬─► OPEN_UPDATES ─┬─► AGENDA_FINALIZED ─┬─► IN_PROGRESS ─┬─► FOR_REVIEW ─┬─► APPROVED ──► PUBLISHED ──► CLOSED
  │    │    ▲     │        │     ▲               │    ▲          │    ▲    │      │    ▲   │         ▲   │
  │    └────┘     └────◄───┴─────┘               └────┘          └────┘    │      └────┘   └──┐      │   │
  │                                                                         │                    │      │   │
  └────────────────────┬─────────────────────────── RETURNED_FOR_CORRECTION ◄───────────────────┘      │   │
                       │                                                                                │   │
                       └────────────────────────────────────────────────────────► ARCHIVED ◄───────────┘   │
                                                                                  ▲                        │
                                                                                  └────────────────────────┘
```

Step-by-step happy path for a monthly departmental review:

1. **Create (DRAFT)** — Meeting Chair or Minutes Secretary opens
   *Meetings → New Meeting*, selects Type (auto-generates the reference prefix
   like `MRG-2026-0003`), title, start/end time, location, department,
   chair. Saves → status = **DRAFT**, audit `action=CREATE`.
2. **Open Updates** — After saving, owner clicks "Open for updates" from the
   meeting detail page → status becomes **OPEN_UPDATES**. Department
   contributors (scoped) can now add agenda items *in their departments* via
   the carry-forward dialog or directly.
3. **Finalize Agenda** — Owner finalises the agenda by clicking "Lock
   agenda" → status = **AGENDA_FINALIZED**. New items can no longer be
   added until re-opened.
4. **In Progress** — On the day, owner clicks "Meeting in progress" →
   status = **IN_PROGRESS**. Minutes secretary fills decision fields on each
   agenda item live.
5. **For Review** — Owner submits to management → **FOR_REVIEW**. Now only
   System / Management admins can advance it further; chairs see it
   read-only.
6. **Approve / Return** — Admin opens the modal:
   - If minutes are fine → **APPROVED** (no reason required; audit
     `action=APPROVE` + `ACTION_TRANSITION` recorded).
   - If minutes need correction → **RETURNED_FOR_CORRECTION** and admin
     **must** write a Reason (enforced in both the transition form clean()
     and the service). The meeting re-opens at the status *prior to*
     FOR_REVIEW (the author may then re-edit decisions and submit again).
7. **Publish** — Admin clicks "Publish minutes" → **PUBLISHED**. All staff
   (Viewers +) see the meeting on the list/calendar; URLs to attachments and
   decisions are now world-readable to logged-in users.
8. **Close** — After any follow-up action items are cut and linked, admin
   clicks "Close meeting" → **CLOSED**.
9. **Archive** — Long-term storage (years-old meetings) → admin moves any
   status to **ARCHIVED**. Archiving is reversible only by System/Mgmt Admin
   using `ArchiveAuthorizedMixin`.

At **every** edge the service `transition_meeting()` re-reads the DB row with
`select_for_update()` inside `transaction.atomic()`, validates the edge is in
`VALID_TRANSITIONS`, enforces admin-role gates for RETURNED/ARCHIVED, enforces
non-empty reason for RETURNED transitions, writes *two* records
(`MeetingStatusHistory` + `AuditLog(ACTION_TRANSITION)`), and propagates the
new status/timestamps back to the caller's Python object.

## 8. Attendance, Agenda Build, and Carry-Forward (Phase 3)

Actors: **Minutes Secretary** (usually) or **Meeting Chair**.

### 8a. Setting Up Attendance

From the meeting detail page click **Attendance** tab → `/meetings/<uuid>/attendance/`.

1. The page shows an empty inline formset. For each person:
   - Pick their `user` row (filter shows only active users).
   - Tick **Invited?** (yes/no — tracks RSVP list separately from who actually showed up).
   - Tick **Attended?** (set after the meeting; walk-ins = Attended=True, Invited=False).
   - Pick RSVP status: YES / NO / PENDING.
2. Click **Save attendance** → each row triggers `MeetingAttendanceForm.clean()`
   which rejects inactive users (checks `user.is_active`; can't accidentally
   mark a departed employee as "attended"). A single `AuditLog.ACTION_ASSIGN`
   event is written summarising the bulk change plus per-row events for rows
   that changed.

*Key invariant:* `Invited` and `Attended` are **independent flags**.
`is_invited=True, is_attended=False` means no-show.
`is_invited=False, is_attended=True` means a walk-in guest. Both contribute
to distinct counts on the detail page summary.

### 8b. Building the Agenda (Categories + Items + Order)

1. **Agenda Categories** — one-time setup under
   `/meetings/agenda-categories/`. Example categories: *Opening Remarks*,
   *Departmental Reports*, *Action Item Review*, *Any Other Business*.
   Categories have a global sort `order` field and can be department-scoped
   (leave scope blank for company-wide categories).
2. **Add Agenda Items** — on the meeting detail → **Agenda** tab →
   **+ Agenda Item**, fill in:
   - Category (optional; default: *Uncategorised*)
   - Title (required)
   - Discussion (free text, written pre- or during-meeting)
   - Decision (outcome, written IN_PROGRESS or after)
   - Item status: To be discussed / Carried forward (auto-set on carry-forward)
   - Owner / Department / Time allocated
   - **Confidential** checkbox — see §7 (Permissions doc, redacted to
     `[Confidential]` for unprivileged viewers).
3. **Drag to Reorder** — JS drag handles on the Agendum list reorder items,
   the "Save order" button POSTs to `/meetings/<uuid>/agenda/order/save/`.
   The backend runs a **two-phase bulk_update** (phase 1 → high offset,
   phase 2 → final 0..N) to avoid SQLite `UNIQUE(meeting_id, order)`
   conflicts during permutations.

### 8c. Carry-Forward Items from a Past Meeting

On the target meeting (current month's review), at the Agenda tab click
**Carry-forward items** button. A modal opens:

1. Pick **Source meeting** (dropdown shows past meetings of the same type,
   ordered by date desc).
2. Tick one or more agenda items from the source list.
3. Click **Carry forward** → backend service
   `carry_forward_agenda_items(source, target, item_ids, by_user=...)`:
   - Clones each item: title, discussion, category.
   - Sets `decision=""` (cleared for the new discussion),
     `item_status=CARRIED_FORWARD`, links
     `carried_forward_from=original_item`.
   - Appends new items at the **end** of the target's current agenda
     (`max(order)+1` per row, preserving the source's relative ordering).
   - **Confidential items** are silently skipped if the caller is not in
     `CONFIDENTIAL_VIEWER_ROLES`, so secret items can't leak via carry-forward
     abuse.
   - Each copied item writes `AuditLog(ACTION_CREATE,
     reason="Carried forward from MTG-2026-0002")` with the FK link.
4. After carry-forward, use drag-reorder (§8b step 3) to move the new items to
   the right place in the meeting.

When the Minutes Secretary then clicks **Finalize Agenda** → transitions to
AGENDA_FINALIZED and the normal lifecycle §7 takes over.

## §9 — Action Item Lifecycle (Phase 4+)

Action items span 7 statuses with a DAG enforced inside
`apps.action_items.services.VALID_TRANSITIONS`. Only the transitions shown in
[actionitem_status_transitions.md](actionitem_status_transitions.md) are
permitted; any other movement raises `ValidationError` in the service layer
*before* any DB write.

```
OPEN ──▶ IN_PROGRESS ──▶ UNDER_REVIEW ──▶ COMPLETED  (TERMINAL, LOCKED)
 │          │                 │
 │          ▼                 ▼
 │        BLOCKED         CANCELLED  (TERMINAL, LOCKED)
 │                           ▲
 ▼                           │
REOPENED ────────────────────┘
  │
  └──▶ re-enters IN_PROGRESS as the re-opened active state
```

Status constants live at **module level** in `apps.action_items.models`:
`STATUS_OPEN / STATUS_IN_PROGRESS / STATUS_BLOCKED / STATUS_UNDER_REVIEW /
STATUS_COMPLETED / STATUS_CANCELLED / STATUS_REOPENED`.

### 9a — Progress & Completion Rules

- `progress_pct` is always clamped by `ActionItem.clean()` to the **integer
  range 0..100** (both endpoints allowed). Any value outside raises
  `ValidationError`.
- Transitioning `OPEN → IN_PROGRESS` via `transition_actionitem()` bumps
  progress to a minimum of `10` automatically if it was still `0`, so an
  action is never "in progress" with zero reported work.
- Transitioning any non-terminal status **→ COMPLETED** via the Complete
  form (`ActionItemCompleteForm`) **and** the service layer:
  1. Requires `blockers == ""` (empty / unresolved blockers text → reject).
  2. Forces `progress_pct = 100` (service-level write; the Complete form
     shows progress as a read-only `100` widget).
  3. Writes an `ActionItemUpdate` snapshot with the completion summary text
     plus `[Completion]` prefix, followed by an `AuditLog(ACTION_COMPLETE)`
     record.

### 9b — 4-Layer Lock for Terminal Statuses

`TERMINAL_STATUSES = {COMPLETED, CANCELLED}` are fully locked by the same
four-layer defense described in `docs/permissions.md` (model property →
form disabled+clean → view dispatch 403 → template guards). No edit,
re-assign, or comment mutation is permitted once an item reaches a terminal
state — **only an admin can re-open it** (see §9c).

### 9c — Reopening Rules (COMPLETED / CANCELLED → REOPENED)

An action item in either terminal state can re-enter the workflow only if
**both** of the following conditions hold, enforced independently in the
transition service AND in `ActionItemReopenForm.clean()`:

1. **Role gate** — calling user has `ROLE_SYSTEM_ADMIN` or
   `ROLE_MANAGEMENT_ADMIN` (defined by `ACTION_REOPEN_ROLES`).
2. **Reason gate** — `reason` string is **non-empty after `.strip()`** — the
   transition raises `ValidationError("Re-opening requires a reason.")`
   otherwise.

A successful reopen writes:
- An `ActionItemStatusHistory` row preserving the prior terminal status.
- An `AuditLog(ACTION_REOPEN, reason=…)` record with the reason captured.
- Status flips to `REOPENED`, and the owner typically moves it to
  `IN_PROGRESS` to resume execution.

### 9d — Overdue Logic

The `ActionItem.is_overdue` property returns `True` when
`due_date < today()` **and** the item is not in a terminal status.
`overdue_age_days` returns the integer count of days past the due date
(0 when not overdue). The `overdue_action_items_queryset(user, dept, limit)`
service returns dept-scoped overdue items sorted by most-overdue first, used
by the dashboard "Next 8 Overdue" KPI card and the dedicated
`action_items:actionitem_overdue` list tab.

## §10 — Action Item Carry-Forward (Phase 4+)

Action items support bulk carry-forward via the 6-part hard contract defined
in `carry_forward_action_items()` (`apps.action_items.services`). The UI is
two-fold: (a) the checkbox-select + **Carry Forward** modal in
`actionitem_list.html` for arbitrary bulk moves, and (b) a per-item
"Carry to new meeting" card on the detail page.

### 10a — Six-Part Service Contract

Every invocation of `carry_forward_action_items(source_items, target_meeting,
target_scope_key, include_completed=False, include_cancelled=False, by_user,
reason="")` guarantees all of the following atomically:

1. **Explicit carry linkage** — for each newly created action item,
   `new.carried_forward_from = old` FK is set **and** a
   `ActionItemCarryForwardLink(source_item=old, target_item=new,
   target_meeting=, target_scope_key=)` row is inserted. Related history
   (`ActionItemUpdate` rows + `ActionItemStatusHistory` rows) is copied to
   the new item preserving provenance.
2. **Default terminal-skip** — items whose status is `COMPLETED` or
   `CANCELLED` are silently dropped UNLESS the caller explicitly flips
   `include_completed=True` / `include_cancelled=True` (rendered as
   checkboxes in the `ActionItemCarryForwardForm`).
3. **Idempotency** — enforced by the DB unique constraint
   `ActionItemCarryForwardLink.Meta.unique_together =
   [("source_item", "target_meeting", "target_scope_key")]`. Re-running the
   service with the same source set + target + scope key returns the
   *previously created* target items (no duplicates).
4. **Transaction atomicity** — the entire operation runs inside
   `transaction.atomic()`. Any `IntegrityError` triggers a full rollback
   and the service returns `[]` (empty list).
5. **Auditability** — per-item `AuditLog(ACTION_CARRY_FORWARD)` entries are
   written (via `transaction.on_commit` so they only persist on commit),
   with the optional user-provided `reason` string stored.
6. **Preservation of scoping** — the `target_scope_key` parameter
   distinguishes distinct logical carry operations over the same source &
   meeting (e.g., "week-15 carry of only open items" vs "week-15 full carry
   including completed items"). Callers (views) MUST compute distinct keys
   for distinct intents to avoid idempotency false-positives.

### 10b — UI Override Behavior

The list-view Carry Forward modal (`actionitem_list.html`, `#carryForwardModal`)
exposes two checkbox overrides rendered alongside the target-meeting select
and optional reason textarea:

- [ ] Include COMPLETED items
- [ ] Include CANCELLED items

These map 1:1 to `include_completed` / `include_cancelled` kwargs of the
service. After successful POST the user is redirected back to the list view
with `?status=` filter state preserved through the query string round-trip.

## 11 — Sales Workflow (Phase 5)

### 11a — Entities (9 models)

| Entity                            | FK / Unique keys                                                | Purpose                                                                                  |
|-----------------------------------|-----------------------------------------------------------------|------------------------------------------------------------------------------------------|
| `ReportingPeriod`                 | `(status, start_date)` candidate; `weeks_count ∈ {4, 5}`       | Business quarter or sprint: 3 statuses (DRAFT → OPEN → CLOSED), multi-currency.         |
| `SalesTeam`                       | unique `code`; leader → User                                   | Top-level sales organization (e.g., "Enterprise").                                     |
| `SalesGroup`                      | unique `code`; FK → `team`; manager → User                     | Sub-team that owns performance targets (e.g., "North Luzon").                           |
| `SalesGroupMembership`            | `unique_together (user, group)`; `left_on ≥ joined_on`         | Who belongs to a group during a range of dates; joined_on has sentinel default.         |
| `PerformanceTarget`               | `unique_together (group, period)`                               | Revenue / profit / orders / deliveries targets for one group × period.                  |
| `DeliveryPerformance`             | `unique_together (group, period)`; planned ≥ achieved ≥ on_time | Delivery counts for the group × period; clean() validates order.                        |
| `SalesOrderPerformance`           | `unique_together (group, period)`                               | Revenue / profit / orders achieved in the period.                                       |
| `WeeklyCommitment`                | `unique_together (group, period, week_number)`; week ∈ [1,wc]   | One row per week 1..`period.weeks_count` holding weekly revenue / profit / orders.      |
| `GroupPerformanceSnapshot`       | `unique_together (group, period, meeting)`; nullable `meeting` | Snapshot-of-record for a meeting; carries all justified values; lock propagated.        |

### 11b — Reporting Period Lifecycle

```
      /─────────────────────────────── reopen: SALES_AUTHOR_ROLES ──────────────────────────\
      |                                                                                      |
      ▼                                                                                      |
   [DRAFT] ──open──► [OPEN] ─────────────────────────────────close──► [CLOSED]              |
   (edit OK)      (weeklies editable; targets upsertable)         (all rows read-only)      |
      ▲                                                               ▲                     |
      \──new period default──────────────────────────────────────────/                     |
```

Transitions:

- **DRAFT → OPEN**: System auto-transition when period `start_date` reaches today OR any
  SALES_AUTHOR sets `status=OPEN` from the edit page. Edits are allowed until closed.
- **OPEN → CLOSED**: SALES_LOCK_ROLES (SysAdmin / MgmtAdmin / Chair) from period list
  "Close Period" action. Also automatically triggers when end_date passes. No further edits
  to targets, deliveries, actuals, or weekly commitments allowed.
- **CLOSED → OPEN**: SALES_LOCK_ROLES only.

All money columns use `DecimalField(16,2)`; rounding helper `_q()` with `ROUND_HALF_UP`
applied at every service-layer boundary. Float is prohibited from the calculation layer.

### 11c — Currencies (4)

Constant map: `CURRENCY_SYMBOLS = {"PHP":"₱","USD":"$","EUR":"€","JPY":"¥"}`

Templates format money as `₱1,234.56` (symbol adjacent, no space). Negative numbers
default to `minus` rendering; two alternate renderers available for variance cells:
`signed (±)` and `parens (financial)`, plus `negative_class → "text-danger"` coloring.

## 12 — Weekly Commitments & Snapshots (Phase 5)

### 12a — 4- or 5-Week Logic

- `ReportingPeriod.weeks_count ∈ {4, 5}` validated in `clean()`.
- `WeeklyCommitment.week_number` validated `1 ≤ week_number ≤ period.weeks_count`.
- Template table headers and `build_weekly_commitment_formset()` **compute**
  `extra = period.weeks_count - existing_count` at render time — never hardcoded to
  4 columns.

### 12b — Calculation Rules

Services live in `apps/sales_updates/services.py`. All are pure (no ORM mutations)
except `take_snapshot()`:

| Service                          | Output keys                                                                               |
|----------------------------------|-------------------------------------------------------------------------------------------|
| `percentage_achieved(actual, target)` | Returns `Decimal("0")` when target ≤ 0; else `actual/target * 100` quantized to 2 dp.     |
| `deficit(actual, target)`        | `actual - target`; negative = behind plan, positive = ahead.                              |
| `monthly_average(values, months_count)`  | `sum(values) / months_count`; `months_count > 0` guard.                            |
| `group_period_subtotals(group, period)`  | revenue/margin targets+actuals+pct+deficit; orders/deliveries counts; 16 keys.     |
| `team_period_totals(team, period)`       | Aggregation of all group subtotals under the team.                                |
| `overall_period_totals(period)`          | Sum of every group in the period across both axes.                                 |
| `weekly_commitment_totals(group, period)`| Sum of weekly rows (revenue/profit/orders) compared against actuals.               |

### 12c — `take_snapshot()` — Idempotency & Locking

```python
@atomic
def take_snapshot(group, period, *, meeting=None, by_user=None, force=False):
    ...
```

1. **Populate all 12 calculated fields** (`revenue_target`, `revenue_pct`,
   `profit_margin_actual`, `revenue_deficit`, `deliveries_on_time_pct`, ...)
   from the services layer at snapshot time. Only the snapshot is "justified" —
   everything else in the UI is `@property` / service computed on read.
2. **Idempotency via DB guard**: `unique_together = (group, period, meeting)`.
   If the 3-tuple already exists the save raises `IntegrityError`; the wrapper
   catches, rolls back, and returns the existing row.
3. **Snapshot meeting link**: snapshots may be created `meeting=None` (standalone
   editable draft) or linked to a specific Meeting instance.
4. **Lock propagation rule**: `is_snapshot_locked(snapshot)` lazily imports
   `NON_EDITABLE_STATUSES` from `apps.meetings.models` (never module-top — avoids
   circular import) and returns:
   ```
   snapshot.meeting_id is not None and snapshot.meeting.status in NON_EDITABLE_STATUSES
   ```
   Snapshots without a `meeting` link are **always editable** regardless of period
   or any other state.
5. **Audit trail**: `post_save` signal on `GroupPerformanceSnapshot` fires
   `ACTION_LOCK` via `log_audit_event(..., immediate=False)` (wrapped in
   `transaction.on_commit`) the first time `is_snapshot_locked()` transitions
   to True.

### 12d — Snapshot Printable & Excel Export

- **Printable**: `snapshot_printable.html` is a **standalone** fragment (does NOT
  extend the main base). Uses `@page { size: A4 landscape; margin: 1cm; }` print
  CSS. Nav bar, footer, and side panel are omitted entirely.
- **Excel**: `ExcelPeriodExport` view returns a `StreamingHttpResponse` with
  `Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`
  and an attachment filename. The workbook is built with `openpyxl`; sheets:
  1. `Period Summary` — targets vs actuals matrix with % achievement & deficit cols.
  2. `Meta` — generated-at (UTC), exported-by, period dates & currency.
  3. `Weekly Commitments` — one group per block, 4 or 5 week columns based on
     `period.weeks_count` (dynamic — never hardcoded).
- **Export audit**: ACTION_EXPORT is logged with `record=ReportingPeriod` inside
  the view body, guarded by `can_export_sales_period` permission. The response
  starts streaming only after the audit write has been enqueued to
  `transaction.on_commit`.

### 12e — UI Layout (6 Tabs on Group Period Detail)

Group Period Detail page renders these 6 tab-card sections; wide tables use the
`.sticky-col` pattern on the first column and `.table-responsive` wrapper for
mobile scrolling:

| Tab              | Contents                                                                                      |
|------------------|-----------------------------------------------------------------------------------------------|
| Summary          | 4 KPI cards (Revenue actual, Margin %, Revenue gap parens, Weeks until cutoff) + subtotals    |
| Targets          | PerformanceTarget upsert form with group/period prefilled                                     |
| Deliveries       | DeliveryPerformance upsert + % on_time achieved gauge                                         |
| Actuals          | SalesOrderPerformance upsert + revenue/profit comparison vs target                            |
| Weekly           | Formset with `period.weeks_count` rows (extra = calculated)                                   |
| Snapshots        | Snapshot list per group×period; button → SnapshotCreateView (meeting picker); lock icon badge |

