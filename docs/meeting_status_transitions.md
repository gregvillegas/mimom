# Meeting Status Transition Matrix

This document is the canonical reference for the DAG (directed acyclic graph) of
statuses in the meetings domain. Edges, admin gates, and reason requirements
match exactly the Python constants in
[apps/meetings/services.py](../apps/meetings/services.py):
`VALID_TRANSITIONS`, `REQUIRE_REASON_TRANSITIONS`, and
`REQUIRE_ADMIN_TRANSITIONS`.

## 10 Statuses (Module-Level Constants)

| Label        | Constant Name                      | Display Name         | Primary Owner / Actor       |
|--------------|------------------------------------|----------------------|-----------------------------|
| D            | `STATUS_DRAFT`                     | Draft                | Meeting owner (chair/sec)   |
| O            | `STATUS_OPEN_UPDATES`              | Open for Updates     | Meeting owner + contributors|
| F            | `STATUS_AGENDA_FINALIZED`          | Agenda Finalized     | Meeting owner               |
| P            | `STATUS_IN_PROGRESS`               | In Progress          | Chair / Secretary live      |
| R            | `STATUS_FOR_REVIEW`                | For Review           | System/Mgmt Admin reviews   |
| T            | `STATUS_RETURNED_FOR_CORRECTION`   | Returned             | Owner fixes, Admin unlocks  |
| A            | `STATUS_APPROVED`                  | Approved             | Management gate             |
| U            | `STATUS_PUBLISHED`                 | Published            | Visible to entire company   |
| C            | `STATUS_CLOSED`                    | Closed               | Long-term done state        |
| X            | `STATUS_ARCHIVED`                  | Archived             | Cold storage (admin only)   |

## 10 × 10 Adjacency Matrix

Rows = **from** status. Columns = **to** status.

| From ↓ / To → | D (Draft) | O (Open) | F (Final) | P (InProg) | R (Review) | T (Return) | A (Appr) | U (Pub) | C (Close) | X (Arch) |
|---------------|-----------|----------|-----------|------------|------------|------------|----------|---------|-----------|----------|
| **D (Draft)** |           | ✅        |           |            |            |            |          |         |           | ✅ **ADMIN** |
| **O (Open)**  | ✅         |          | ✅         |            |            |            |          |         |           | ✅ **ADMIN** |
| **F (Final)** |           | ✅        |           | ✅          |            |            |          |         |           | ✅ **ADMIN** |
| **P (InProg)**|           |          | ✅         |            | ✅          |            |          |         |           | ✅ **ADMIN** |
| **R (Review)**|           |          |           | ✅          |            | ✅ **ADMIN+REASON** | ✅ **ADMIN** |         |           | ✅ **ADMIN** |
| **T (Return)**|           |          |           |            | ✅          |            |          |         |           | ✅ **ADMIN** |
| **A (Appr)**  |           |          |           |            |            | ✅ **ADMIN+REASON** |          | ✅ **ADMIN** |         | ✅ **ADMIN** |
| **U (Pub)**   |           |          |           |            |            | ✅ **ADMIN+REASON** | ✅ **ADMIN** |          | ✅ **ADMIN** | ✅ **ADMIN** |
| **C (Close)** |           |          |           |            |            |            |          | ✅       |           | ✅ **ADMIN** |
| **X (Arch)**  |           |          |           |            |            |            |          |         |           |          |

Legend:
- `✅` — edge is permitted (DAG-validated by `transition_meeting`).
- **ADMIN** — actor must be in `REOPEN_AUTHORIZED_ROLES` (System
  Administrator OR Management Administrator). Superuser is always OK.
- **ADMIN+REASON** — edge is in both `REQUIRE_ADMIN_TRANSITIONS` (target
  status) **and** `REQUIRE_REASON_TRANSITIONS` (from→to pair). Transition
  form + service reject empty or whitespace-only reason strings.
- Empty cell = `ValidationError("… is not permitted.")` from the service.
- **X (Archived)** is a sink with zero outgoing edges; un-archive is not
  allowed (restore by DB admin intervention only via shell).

## Allowed Transitions (Compact List)

From `VALID_TRANSITIONS` dictionary in services.py:

```
DRAFT                        →  OPEN_UPDATES, ARCHIVED
OPEN_UPDATES                 →  DRAFT, AGENDA_FINALIZED, ARCHIVED
AGENDA_FINALIZED             →  OPEN_UPDATES, IN_PROGRESS, ARCHIVED
IN_PROGRESS                  →  AGENDA_FINALIZED, FOR_REVIEW, ARCHIVED
FOR_REVIEW                   →  IN_PROGRESS, RETURNED_FOR_CORRECTION, APPROVED, ARCHIVED
RETURNED_FOR_CORRECTION      →  FOR_REVIEW, ARCHIVED
APPROVED                     →  RETURNED_FOR_CORRECTION, PUBLISHED, ARCHIVED
PUBLISHED                    →  APPROVED, RETURNED_FOR_CORRECTION, CLOSED, ARCHIVED
CLOSED                       →  PUBLISHED, ARCHIVED
ARCHIVED                     →  (none)
```

## Admin-Gated Target Statuses

`REQUIRE_ADMIN_TRANSITIONS` checks whether the *target* status of the
transition requires `System Administrator` or `Management Administrator`
privileges (evaluated after the DAG edge check). Also used by
`ArchiveAuthorizedMixin` and the author gating predicates.

| Target Status               | Admin role required? |
|-----------------------------|----------------------|
| RETURNED_FOR_CORRECTION     | ✅ Yes (REOPEN_AUTHORIZED_ROLES) |
| ARCHIVED                    | ✅ Yes (REOPEN_AUTHORIZED_ROLES) |
| FOR_REVIEW → APPROVED       | ✅ Yes (APPROVED gated by admin) |
| APPROVED → PUBLISHED        | ✅ Yes (PUBLISHED gated by admin)|
| PUBLISHED → CLOSED          | ✅ Yes (CLOSED gated by admin)   |
| All other edges (D↔O↔F↔P…)  | ❌ Owner is sufficient           |

## Reason-Required Edges

Edges where `(from_status, to_status) ∈ REQUIRE_REASON_TRANSITIONS`. Both
`TransitionForm.clean()` and `transition_meeting()` validate:
```python
if (current, target) in REQUIRE_REASON_TRANSITIONS and not (reason and reason.strip()):
    raise ValidationError("A reason is required for this status transition.")
```

| From                    | To                        | Typical reason example |
|-------------------------|---------------------------|------------------------|
| FOR_REVIEW              | RETURNED_FOR_CORRECTION   | "Minutes missing Section 3; expand XYZ decision." |
| APPROVED                | RETURNED_FOR_CORRECTION   | "Attendance list incomplete; sign-offs pending."  |
| PUBLISHED               | RETURNED_FOR_CORRECTION   | "Published version has typo in agenda item 5."    |

Stored in `MeetingStatusHistory.reason` (text column, optional but non-empty
for rows above) **and** propagated to `AuditLog.reason` for the
`ACTION_TRANSITION` event so the rationale appears in both the meeting's
status timeline and the global audit log.

## Validation & Defense Ordering

`transition_meeting(meeting, target_status, *, by_user, reason="", skip_role_check=False)`
performs checks in this order. Any step raising `ValidationError` aborts the
transition with no partial state written (inside `transaction.atomic()`):

1. **Target syntax** — `target_status` is one of the 10 known STATUS_CHOICES.
2. **Identity** — target != current status ("identical status" error).
3. **DAG edge** — `target ∈ VALID_TRANSITIONS[current]` from the table above.
4. **Admin gate** — if `target_status in REQUIRE_ADMIN_TRANSITIONS and not
   skip_role_check`: `by_user.is_superuser or by_user.has_role(*REOPEN_AUTHORIZED_ROLES)`.
5. **Reason gate** — if `(current, target) ∈ REQUIRE_REASON_TRANSITIONS`:
   `bool(reason and reason.strip())`.
6. **Row lock** — `Meeting.objects.select_for_update().get(pk=meeting.pk)` so
   two simultaneous transitions from different browsers serialize correctly.
7. **Apply** — update the meeting row; set `published_at`/`closed_at`/`archived_at`
   timestamps on first arrival at the corresponding terminal statuses; create
   `MeetingStatusHistory` row; fire `AuditLog(ACTION_TRANSITION, reason=reason)`
   via `log_audit_event(record=locked, …)`; `transaction.on_commit` defers
   the audit write until commit succeeds.
8. **Caller propagation** — updates the *caller's* Python object
   `meeting.status` and the three timestamp fields so callers don't need
   `.refresh_from_db()` for the status display.

## Common Errors

| Symptom                                                     | Root cause (check this first)                         |
|-------------------------------------------------------------|-------------------------------------------------------|
| `ValidationError: Transition from X to Y is not permitted.` | Edge missing from the matrix above; fix business flow. |
| `"This status transition requires System Administrator…"`  | Target status ∈ REQUIRE_ADMIN_TRANSITIONS.           |
| `"A reason is required for this status transition."`        | Edge ∈ REQUIRE_REASON_TRANSITIONS but reason empty.   |
| `UNIQUE(meeting_id, order)` during agenda reorder           | (Fixed: 2-phase bulk_update. Report if it recurs.)     |
| `NameError STATUS_* not defined` in test                    | Import missing from `apps.meetings.models`.            |
| Audit log missing rows after transition                     | Forgot `transaction=True` pytest marker; `on_commit` runs only after commit. |
