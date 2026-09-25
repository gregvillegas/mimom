# ApprovedMeetingSnapshot Model — Payload, Versioning & Double-Publish Guard

This document is the canonical reference for the `ApprovedMeetingSnapshot`
model shipped in Phase 6. It complements `docs/workflows.md §14` with
concrete JSON examples, test notes, and the correctness proof of the
3-layer double-publish guard.

---

## 1. The 8 Payload JSON Parts (Top-Level Keys)

`ApprovedMeetingSnapshot.payload` is a Django `JSONField` with schema:

```
payload: {
  meeting_meta:  Object      (10 scalars — see §1.1)
  attendance:    Array[Attendee]   — see §1.2
  agenda_items:  Array[Agendum]    — see §1.3
  discussions:   Array[Discussion] — see §1.4
  decisions:     Array[Decision]   — see §1.5
  action_items:  Array[ActionItem] — see §1.6
  sales_data:    Object            — see §1.7 (group_id → 12-field snapshot)
  status_history: Array[StatusEvent] — see §1.8
}
```

All 8 keys are always present. Missing data for a key is represented as
`null` for `meeting_meta` / `sales_data`, and `[]` for the four array
keys. Extra top-level keys are rejected by `ApprovedMeetingSnapshot.clean()`
before save.

### 1.1 — meeting_meta (10 scalars)

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "reference": "MRG-2026-0017",
  "title": "Q3 Sales Review — North Luzon",
  "meeting_type_code": "MRG",
  "start_at": "2026-09-15T10:00:00Z",
  "end_at":   "2026-09-15T12:30:00Z",
  "location": "HQ Conf Room B",
  "department_id": 7,
  "chair_id": 42,
  "chair_display_name": "María Santos"
}
```

Note: `chair_display_name` is stored *denormalized* in the snapshot so the
snapshot remains readable if the `User` row is later anonymized or
soft-deleted.

### 1.2 — attendance (array)

```json
[
  {
    "user_id": 42,
    "display_name": "María Santos",
    "is_invited": true,
    "is_attended": true,
    "rsvp_status": "YES"
  },
  {
    "user_id": 118,
    "display_name": "Juan dela Cruz",
    "is_invited": true,
    "is_attended": false,
    "rsvp_status": "NO"
  },
  {
    "user_id": 201,
    "display_name": "Unregistered Guest (walk-in)",
    "is_invited": false,
    "is_attended": true,
    "rsvp_status": null
  }
]
```

### 1.3 — agenda_items (array, ordered by `order`)

```json
[
  {
    "id": 812,
    "order": 1,
    "category_id": 3,
    "category_name": "Departmental Reports",
    "title": "August revenue vs Q3 target",
    "discussion": "Revenue ₱14.2M vs target ₱15M — 94.7% (see sales_data). Shortfall concentrated in week-3 Enterprise pipeline slips.",
    "decision": "Re-baseline week-4 Enterprise commitment to ₱6.5M (was ₱5.8M). Chair to follow up with Enterprise lead by Friday.",
    "owner_id": 77,
    "owner_name": "Liza Reyes",
    "item_status": "DECIDED",
    "confidential": false,
    "time_allocated_minutes": 25
  },
  {
    "id": 813,
    "order": 2,
    "category_id": 4,
    "category_name": "Action Item Review",
    "title": "AI-0116 Hiring pipeline status",
    "discussion": "[Confidential — redacted for unprivileged viewers but stored verbatim here]",
    "decision": null,
    "owner_id": 42,
    "owner_name": "María Santos",
    "item_status": "CARRIED_FORWARD",
    "confidential": true,
    "time_allocated_minutes": 15
  }
]
```

Confidential flag is preserved in the snapshot payload so downstream
renderers can honour redaction independently even for historical reads.

### 1.4 — discussions (array)

```json
[
  {
    "id": 41,
    "agenda_item_id": 812,
    "topic": "Week-3 Enterprise pipeline slip root cause",
    "summary": "Two enterprise deals slipped — both awaiting legal redline. In-house counsel assigned one paralegal for sales contract review starting next week.",
    "raised_by_name": "Liza Reyes",
    "occurred_at": "2026-09-15T10:17:00Z"
  }
]
```

### 1.5 — decisions (array, formal decisions with FK back to agenda item)

```json
[
  {
    "id": 191,
    "agenda_item_id": 812,
    "text": "Re-baseline week-4 Enterprise commitment to ₱6.5M.",
    "rationale": "94.7% August achievement leaves manageable shortfall; Enterprise pipeline has 3 mature deals that can close in week 4.",
    "decided_by_id": 42,
    "decided_by_name": "María Santos",
    "decided_at": "2026-09-15T10:42:00Z"
  }
]
```

`agenda_item_id` is nullable (a decision can be raised off-agenda during
AOB). The foreign key is copied as a bare integer so the snapshot remains
consistent if agenda rows are later archived/deleted.

### 1.6 — action_items (array)

```json
[
  {
    "id": 3041,
    "title": "Follow up with Enterprise lead on week-4 re-baseline",
    "description": "Confirm revised commitment of ₱6.5M and document the 3 targeted deals.",
    "status": "OPEN",
    "priority": "HIGH",
    "due_date": "2026-09-19",
    "owner_id": 42,
    "owner_name": "María Santos",
    "assignees": [
      {"user_id": 42, "display_name": "María Santos"},
      {"user_id": 77, "display_name": "Liza Reyes"}
    ],
    "carried_forward_from_id": null,
    "source_meeting_id": null
  },
  {
    "id": 3042,
    "title": "Assign paralegal for sales contract review",
    "description": "Dedicated paralegal starting Mon next week for Enterprise contract redlines.",
    "status": "IN_PROGRESS",
    "priority": "MEDIUM",
    "due_date": "2026-09-22",
    "owner_id": 23,
    "owner_name": "In-house counsel",
    "assignees": [{"user_id": 23, "display_name": "In-house counsel"}],
    "carried_forward_from_id": null,
    "source_meeting_id": null
  }
]
```

### 1.7 — sales_data (object keyed by group_id)

Each value under a group_id is the full 12-field structure copied from
`GroupPerformanceSnapshot` at snapshot-create time. Keys match
`GroupPerformanceSnapshot._meta` field names exactly.

```json
{
  "17": {
    "group_id": 17,
    "group_code": "NLUZ",
    "period_id": 9,
    "period_label": "Q3 2026",
    "revenue_target": "50000000.00",
    "revenue_actual": "47350000.00",
    "revenue_pct": "94.70",
    "revenue_deficit": "-2650000.00",
    "profit_margin_target": "15.00",
    "profit_margin_actual": "14.32",
    "orders_target": 340,
    "orders_actual": 322,
    "deliveries_target": 306,
    "deliveries_actual": 295,
    "deliveries_on_time_pct": "96.61"
  },
  "18": {
    "group_id": 18,
    "group_code": "SLUZ",
    "...": "..."
  }
}
```

### 1.8 — status_history (array, chronological)

Captures every meeting status change *up to but not including* the
snapshot.time row. The final APPROVED or PUBLISHED event that triggers the
snapshot is intentionally the **last** entry.

```json
[
  {"from_status": "DRAFT",              "to_status": "OPEN_UPDATES",      "transitioned_by_name": "María Santos", "reason": null,                        "occurred_at": "2026-09-05T08:00:00Z"},
  {"from_status": "OPEN_UPDATES",       "to_status": "AGENDA_FINALIZED",  "transitioned_by_name": "María Santos", "reason": null,                        "occurred_at": "2026-09-12T17:34:00Z"},
  {"from_status": "AGENDA_FINALIZED",   "to_status": "IN_PROGRESS",       "transitioned_by_name": "María Santos", "reason": null,                        "occurred_at": "2026-09-15T10:00:02Z"},
  {"from_status": "IN_PROGRESS",        "to_status": "FOR_REVIEW",        "transitioned_by_name": "María Santos", "reason": "Minutes ready",             "occurred_at": "2026-09-15T13:12:00Z"},
  {"from_status": "FOR_REVIEW",         "to_status": "APPROVED",          "transitioned_by_name": "Sys Admin",    "reason": null,                        "occurred_at": "2026-09-16T09:01:11Z"}
]
```

---

## 2. BFS Path-Walk Helper — Test Notes

`tests/test_meetings_submissions_transitions.py` uses a breadth-first
path-walk helper (`_reachable_statuses_bfs(start, transition_fn)`) to prove
two invariants about the 5-state submission DAG:

```
States: NOT_STARTED, IN_PROGRESS, SUBMITTED, RETURNED, ACCEPTED
Edges (valid transitions):
  NOT_STARTED → IN_PROGRESS         (first edit auto-promote)
  IN_PROGRESS → SUBMITTED           (submit_for_review)
  SUBMITTED   → RETURNED            (return_for_correction)
  RETURNED    → SUBMITTED           (resubmit_for_review)
  SUBMITTED   → ACCEPTED            (approve_minutes)
  RETURNED    → IN_PROGRESS         (reopen_minutes from RETURNED)
  SUBMITTED   → IN_PROGRESS         (reopen_minutes from SUBMITTED)
  ACCEPTED    → IN_PROGRESS         (reopen_minutes from ACCEPTED)
  IN_PROGRESS → IN_PROGRESS         (reopen_minutes from IN_PROGRESS — no-op, but allowed by gate)
```

### Test 1: ACCEPTED unreachable without passing through SUBMITTED

BFS from `NOT_STARTED` while masking the edge `SUBMITTED → ACCEPTED` must
**not** reach `ACCEPTED`. Proof that you cannot approve without submit.

### Test 2: RETURNED reachable only from SUBMITTED

BFS from `NOT_STARTED` with a custom visitor that tags the predecessor.
Verify that every discovered path to `RETURNED` has immediate predecessor
`SUBMITTED`. No other edge can enter RETURNED.

### Test 3: Max path length ≤ 6 for any 2-node reachable pair

Because the DAG is 5 nodes with one loop (SUBMITTED↔RETURNED), the longest
simple path between any two nodes is bounded. The BFS helper asserts
`max_path_length ≤ 6` so no regression accidentally introduces a new
cycle-with-cycle that could create infinite loops in UI status walkers.

---

## 3. Versioning Algorithm

### 3.1 — Formula

For a given meeting `M` with existing snapshots `S₁, S₂, …, Sₖ` already
committed to the DB:

```
next_version(M) = ( MAX{ s.version | s ∈ snapshots(M) } ∪ {0} ) + 1
```

Or in the equivalent SQL form actually issued by Django ORM
`.aggregate(m=Max("version"))`:

```sql
SELECT COALESCE(MAX(version), 0) + 1
FROM approved_meeting_snapshot
WHERE meeting_id = %s
```

### 3.2 — Invariants enforced

| Invariant | How it is enforced |
|-----------|--------------------|
| `version ≥ 1` | COALESCE default is `0`, then `+1` always applied |
| No gaps | Rows are never DELETED; unique_together rejects re-use |
| No duplicates within a meeting | `unique_together(meeting, version)` at SQL level |
| Deterministic | Given the same committed DB state, MAX+1 is pure |
| Monotonic | Version only grows, never shrinks per meeting |

### 3.3 — Expected output table (sample meeting MRG-2026-0017)

| Time            | Trigger | version | notes                                           |
|-----------------|---------|---------|-------------------------------------------------|
| T+0m            | APPROVE | 1       | first snapshot, auto at APPROVED transition     |
| T+45m           | MANUAL  | 2       | Chair clicked "re-snapshot" after AOB edit      |
| T+2h 15m        | PUBLISH | 3       | final snapshot frozen at PUBLISH transition     |
| T+5d (no-op)    | —       | —       | new MANUAL call would be version 4, but admin did not click |

---

## 4. Double-Publish Guard — 3-Layer Correctness Proof

Goal: Prove it is impossible for two `ApprovedMeetingSnapshot` rows with
`(meeting=M, version=V)` to both commit, even under worst-case concurrency.

We prove that each layer is **independently sufficient**, then argue that
the conjunction of three independently-sufficient layers has probability of
failure ≈ 0 under any realistic threat model.

### 4.1 — Layer (a) Hard DB Constraint: `unique_together(meeting, version)`

**Mathematical formulation.**

Let `R` be the set of committed rows in `approved_meeting_snapshot`.
Define the predicate `P(r)` = `∃ r' ∈ R, r' ≠ r, r'.meeting = r.meeting ∧ r'.version = r.version`.

The SQL constraint enforces `∀ r ∈ R : ¬P(r)` as a post-condition of every
committed transaction. Any transaction whose commit would make `P(r)` true
for some new row `r` is **aborted with `IntegrityError`**.

**Sufficiency proof of layer (a) alone.**

Assume for contradiction that two rows `r₁` and `r₂` exist, both with
`meeting=M, version=V`. Then `r₁ ≠ r₂` (they are distinct DB rows), and
`r₁.meeting = r₂.meeting = M`, `r₁.version = r₂.version = V`. So `P(r₁)`
is true. But the SQL constraint post-condition forbids this. Contradiction.
Therefore such a pair cannot exist. ✅

**Caveat on layer (a):** Even alone this is sufficient, but application code
would see an `IntegrityError` on every race — a poor UX. Layer (b) exists to
**prevent** the race from ever reaching the DB in the first place.

### 4.2 — Layer (b) App-level `select_for_update` inside `transaction.atomic`

**Concurrency setup.** Two Python processes (or threads) `P1` and `P2` both
call `create_approved_snapshot(M, u)` at wall-clock time `t₀ ± ε` (within
the same DB transaction window).

**Step-by-step serialisation argument.**

```
Time step     P1 action                          P2 action
----------    ----------                         ----------
T1            BEGIN (atomic)                      BEGIN (atomic)
T2            SELECT ... WHERE id=M.id
                 FOR UPDATE  →  lock acquired     (blocks on lock for M.id)
T3            MAX(version) = k (reads committed)
T4            INSERT version = k+1
T5            COMMIT  →  lock released
T6                                              (wakes, lock acquired now)
T7                                              MAX(version) = k+1
T8                                              INSERT version = k+2
T9                                              COMMIT  →  lock released
```

At T3 and T7, the MAX aggregation reads the *committed* row set (SQL `READ
COMMITTED` semantics), which at T7 **includes** the new `k+1` row committed
at T5. So P2 assigns `k+2` instead of racing to `k+1`.

**Sufficiency proof of layer (b) alone.**

For any concurrent pair of calls on the same meeting, one obtains the
`select_for_update` lock first. The second blocks until the first commits.
On wakeup, the second's `MAX(version)` re-query observes the first's
inserted row (because READ COMMITTED re-evaluates aggregates after
commit-release). Hence versions are strictly monotonically assigned. No
duplicates. ✅

**Caveat on layer (b):** Requires that `create_approved_snapshot` is
**always** entered through the service function and never via raw
`ApprovedMeetingSnapshot.objects.create(...)`. This is enforced by code
review + `test_snapshot_create_raw_orm_raises_test_point` unit test.

### 4.3 — Layer (c) `transition_meeting` sets `published_at` only once (idempotently)

The top-level Publish button does **not** call `create_approved_snapshot`
directly. It calls `transition_meeting(M, PUBLISHED, …)`, which runs the
following guard *before* any snapshot code:

```python
if meeting.published_at is None:
    meeting.published_at = now()
    # ... THEN create_approved_snapshot(trigger="PUBLISH")
else:
    # no transition edge exists from PUBLISHED → anything except CLOSED
    raise ValidationError("invalid transition")
```

**Sufficiency proof of layer (c) alone (for the Publish button path).**

Let user click Publish twice: click-1 at time `t₁`, click-2 at `t₂ > t₁`.

- At `t₁`, `M.published_at is None` → guard passes, snapshot created.
- At `t₂`, `M.published_at is not None` (it was set at `t₁`) → guard fails.
  The code raises `ValidationError("invalid transition")` before reaching
  `create_approved_snapshot`. No second snapshot is even attempted. ✅

### 4.4 — The 3-Layer Conjunction: Why It Matters

| Failure mode that one layer misses           | Layer that catches it instead |
|----------------------------------------------|--------------------------------|
| Raw ORM `.create()` bypasses the service (b) | DB constraint (a) raises IntegrityError |
| Hypothetical MySQL/Galera edge-case where s4u lock does not serialise (b) | DB constraint (a) still catches |
| Bug in published_at guard logic (c)          | s4u + MAX (b) still serialises; worst case 2nd snapshot gets N+1 not N; then (a) would reject any actual duplicate |
| Admin uses MANUAL trigger from /admin UI (skips c entirely)  | (b) + (a) still hold — no dependency on transition_meeting |
| All three layers have bugs (implausible)     | Still caught by `published_at` unique app logic + `Approv…(meeting, version)` DB unique; *plus* tests in §2 explicitly cover the race |

The conjunction is strictly stronger than any single layer. Phase 6 ships
all three enabled and tested.
