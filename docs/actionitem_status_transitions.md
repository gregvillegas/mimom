# Action Item Status Transitions (Phase 4)

Statuses live as **module-level** constants in
[apps/action_items/models.py](../apps/action_items/models.py):

| Key              | Label         | Editable? | Notes                                  |
|------------------|---------------|-----------|----------------------------------------|
| `STATUS_OPEN`    | OPEN          | yes       | Initial state.                         |
| `STATUS_IN_PROGRESS` | IN_PROGRESS | yes    | Active work; progress >= 10 auto-set.  |
| `STATUS_BLOCKED` | BLOCKED       | yes       | Needs blockers resolved to continue.   |
| `STATUS_UNDER_REVIEW` | UNDER_REVIEW | yes   | Waiting for reviewer sign-off.         |
| `STATUS_COMPLETED` | COMPLETED   | **no**    | Terminal; 4-layer lock; progress=100.  |
| `STATUS_CANCELLED` | CANCELLED   | **no**    | Terminal; 4-layer lock.                |
| `STATUS_REOPENED` | REOPENED     | yes       | Admin-only entry from terminal states. |

Transition DAG is enforced in
[apps/action_items/services.py](../apps/action_items/services.py) inside the
`VALID_TRANSITIONS` set. `transition_actionitem()` performs all validations in
the order described at the bottom of this document before any DB write.

## 7×7 Adjacency Matrix

Rows = source status, columns = target status. ✅ = allowed, ❌ = disallowed.

| FROM ↓  TO →  | OPEN | IN_PROGRESS | BLOCKED | UNDER_REVIEW | COMPLETED | CANCELLED | REOPENED |
|---------------|------|-------------|---------|--------------|-----------|-----------|----------|
| **OPEN**      | —    | ✅          | ✅      | ✅           | ❌        | ❌        | ❌       |
| **IN_PROGRESS** | ❌  | —           | ✅      | ✅           | ✅        | ❌        | ❌       |
| **BLOCKED**   | ❌   | ✅          | —       | ✅           | ❌        | ❌        | ❌       |
| **UNDER_REVIEW** | ❌ | ✅          | ❌      | —            | ✅        | ✅        | ❌       |
| **COMPLETED** | ❌   | ❌          | ❌      | ❌           | —         | ❌        | ✅ (admin + reason) |
| **CANCELLED** | ❌   | ❌          | ❌      | ❌           | ❌        | —         | ✅ (admin + reason) |
| **REOPENED**  | ❌   | ✅          | ✅      | ✅           | ❌        | ❌        | —        |

## Reason-Required Transitions

These `(from, to)` pairs additionally require a non-empty `reason` string,
enforced by `REQUIRE_REASON_TRANSITIONS` set in
`apps.action_items.services`. The `ReopenForm.clean()` independently re-checks
the reason to prevent form-level bypass.

| Source Status  | Target Status  | Why reason is required                                   |
|----------------|----------------|----------------------------------------------------------|
| UNDER_REVIEW   | CANCELLED      | Justify abandoning an action mid-review cycle.           |
| COMPLETED      | REOPENED       | Audit trail: explain undo of a terminal completed state. |
| CANCELLED      | REOPENED       | Audit trail: explain revival of a cancelled action.      |
| (any)          | BLOCKED        | Must describe the current blocker(s) being recorded.     |

## Admin-Only Transitions

REOPEN target is restricted to users in `ACTION_REOPEN_ROLES = (System
Administrator, Management Administrator)`. Same role gate is present in both
the transition service **and** `ActionItemReopenForm`, independently.

| Source Status  | Target Status | Admin Roles Only                        |
|----------------|---------------|-----------------------------------------|
| COMPLETED      | REOPENED      | Sys Admin / Mgmt Admin (`ACTION_REOPEN_ROLES`) |
| CANCELLED      | REOPENED      | Sys Admin / Mgmt Admin (`ACTION_REOPEN_ROLES`) |

## Validation Order (inside transition_actionitem)

All checks run BEFORE any DB mutation. Order is significant because an earlier
failing check short-circuits and raises a clean `ValidationError` before
touching data:

1. **Fresh re-fetch** — look up `ActionItem.objects.get(pk=item.pk)` from the
   DB inside an atomic block; ignore the caller's in-memory instance (avoids
   stale state races).
2. **DAG membership** — `(source_status, target_status)` ∈ VALID_TRANSITIONS,
   else `ValidationError(f"{from} -> {to} not allowed")`.
3. **Role check** — if target == REOPENED, `by_user` must hold
   `ACTION_REOPEN_ROLES` OR be superuser; `skip_role_check=True` bypasses for
   tests / command-line tools only.
4. **Reason check** — if the transition ∈ `REQUIRE_REASON_TRANSITIONS`, then
   `reason.strip()` must be non-empty.
5. **Target-specific validations**:
   - Target == COMPLETED ⇒ `item.blockers.strip()` must be empty ⇒ raise if
     unresolved blockers remain. `item.progress_pct = 100` is forced next.
   - Target == IN_PROGRESS ⇒ if `item.progress_pct == 0`, bump to 10 minimum.
6. **Row lock via select_for_update** — acquire DB row lock on the re-fetched
   item so two concurrent transition calls can't double-write.
7. **Mutation, history, audit**:
   - Write `item.status = target_status` + any progress bump.
   - Insert `ActionItemStatusHistory(from, to, reason, by_user)`.
   - Insert one `AuditLog` record with a specific action constant:
     `ACTION_COMPLETE` if target=COMPLETED, `ACTION_REOPEN` if
     target=REOPENED, `ACTION_TRANSITION` otherwise.
8. **Return** `ActionItemStatusHistory` object to the caller. The service
   additionally mutates `item.status` in-place on the *original caller
   instance* so downstream views/templates see the new status without a
   manual `.refresh_from_db()`.

## Completion + Reopen Audit Signals (Side-Effects)

- **COMPLETE** — the view layer also writes an `ActionItemUpdate` with
  `[Completion]` prefix + user-provided completion summary; this is distinct
  from the `AuditLog.ACTION_COMPLETE` row (which captures the state-machine
  transition, not the narrative).
- **REOPEN** — the reopen-count counter on the ActionItem is incremented
  (service-level), enabling dashboards to highlight "chronically re-opened"
  actions.
