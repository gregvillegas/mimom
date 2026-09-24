# Sales Data Model (Phase 5 — apps.sales_updates)

## 1 — Domain Overview

The Sales module models a **reporting period** (typically 4 or 5 weeks) across a
hierarchy of `SalesTeam → SalesGroup → (group_memberships, targets, actuals,
weekly rows, snapshots)`. Every row is independently versioned and auditable;
the snapshot-of-record is a `GroupPerformanceSnapshot` linked to a Meeting so
its lock status can be propagated from the meeting status lifecycle.

All 9 domain models inherit `TimeStampedModel` (UUID PK + `created_at` +
`updated_at`) — all URL converters in `apps/sales_updates/urls.py` use
`<uuid:*>`. User FKs are still BigAutoField (the `accounts.User` model uses the
global `DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"`).

### 1a — Constants & Enums

```
3 reporting-period statuses (DRAFT → OPEN → CLOSED):
  PERIOD_DRAFT    = "DRAFT"   — initial; editable by SALES_AUTHOR_ROLES
  PERIOD_OPEN     = "OPEN"    — active; weekly commitments editable
  PERIOD_CLOSED   = "CLOSED"  — read-only; only SALES_LOCK_ROLES can reopen

4 currencies with symbols (no space between symbol & digits):
  CURRENCY_PHP  = "PHP" → "₱"   DEFAULT_CURRENCY
  CURRENCY_USD  = "USD" → "$"
  CURRENCY_EUR  = "EUR" → "€"
  CURRENCY_JPY  = "JPY" → "¥"
```

### 1b — Money Rules (invariant)

1. **All** monetary fields: `DecimalField(max_digits=16, decimal_places=2,
   default=Decimal("0.00"))`.
2. Service-layer arithmetic uses `_q(value)` helper which calls
   `Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)`.
3. `float` is prohibited from the calculation layer — it is only ever parsed
   **through** `Decimal()` at form boundary validation.
4. Percentage fields use `DecimalField(5,2)` with range `[0, 100.00]`.

## 2 — Entity Graph (9 models, 8 unique_together, 12 indexes)

```
ReportingPeriod (1) ───┬───► PerformanceTarget          (unique: group, period)
                       ├───► DeliveryPerformance        (unique: group, period)
                       ├───► SalesOrderPerformance      (unique: group, period)
                       ├───► WeeklyCommitment           (unique: group, period, week_number)
                       └───► GroupPerformanceSnapshot  (unique: group, period, meeting)

SalesTeam (1) ───────► SalesGroup (N) ───────► SalesGroupMembership (N users)
```

### 2a — `ReportingPeriod`

| Field             | Type                    | Constraint                                         |
|-------------------|-------------------------|----------------------------------------------------|
| `name`            | CharField(64)           | `Q1-2026`, etc.                                    |
| `start_date`      | DateField               | start of period (inclusive)                        |
| `end_date`        | DateField               | end of period (inclusive); `clean()` ≥ `start_date`|
| `cut_off_date`    | DateField               | ≤ end_date; date numbers are finalized             |
| `weeks_count`     | IntegerField            | `clean()` enforces ∈ {4, 5}                        |
| `status`          | CharField(8) choices    | DRAFT / OPEN / CLOSED                              |
| `currency`        | CharField(3) choices    | PHP / USD / EUR / JPY; default=PHP                 |
| `description`     | TextField blank         | Free-form notes                                    |

Derivations (read-only @properties):
- `days_until_cutoff → int` — timedelta.days between today and `cut_off_date`.
- `is_closed → bool` — `status == PERIOD_CLOSED`.

### 2b — `SalesTeam`

| Field             | Type                    |
|-------------------|-------------------------|
| `code`            | CharField(16) unique    |
| `name`            | CharField(128)          |
| `leader`          | FK → User BigInt        |
| `is_active`       | BooleanField (T)        |

### 2c — `SalesGroup`

| Field             | Type                    |
|-------------------|-------------------------|
| `code`            | CharField(16) unique    |
| `name`            | CharField(128)          |
| `team`            | FK → SalesTeam UUID     |
| `manager`         | FK → User BigInt        |
| `is_active`       | BooleanField (T)        |

### 2d — `SalesGroupMembership`

| Field             | Type                                | Notes                                     |
|-------------------|-------------------------------------|-------------------------------------------|
| `group`           | FK → SalesGroup UUID                | Part of unique_together                  |
| `user`            | FK → User BigInt                    | Part of unique_together                  |
| `role`            | CharField(32) (default=CONTRIBUTOR) | CONTRIBUTOR / MANAGER / REVIEWER          |
| `joined_on`       | DateField (default=today)           | Wrapped in `_default_joined_on()` to     |
|                   |                                     |  avoid bound-method serialization bug.    |
| `left_on`         | DateField null/blank                | `clean()`: left_on ≥ joined_on if both   |
| `is_active`       | BooleanField (T)                    |

### 2e — `PerformanceTarget` (unique group + period)

| Field                    | Type                     |
|--------------------------|--------------------------|
| `group` / `period`       | FKs (unique_together)    |
| `revenue_target`         | Decimal(16,2)            |
| `profit_target`          | Decimal(16,2)            |
| `orders_target`          | IntegerField ≥0          |
| `deliveries_target`      | IntegerField ≥0          |
| `currency`               | CharField(3) (PHP)       |
| `notes`                  | TextField (blank)        |

### 2f — `DeliveryPerformance` (unique group + period)

clean() invariant: **`deliveries_on_time ≤ deliveries_achieved ≤ deliveries_planned`**

| Field                    | Type                     |
|--------------------------|--------------------------|
| `group` / `period`       | FKs (unique_together)    |
| `deliveries_planned`     | IntegerField ≥0          |
| `deliveries_achieved`    | IntegerField ≥0          |
| `deliveries_on_time`     | IntegerField ≥0          |
| `notes`                  | TextField (blank)        |

### 2g — `SalesOrderPerformance` (unique group + period)

| Field                    | Type                     |
|--------------------------|--------------------------|
| `group` / `period`       | FKs (unique_together)    |
| `revenue_actual`         | Decimal(16,2)            |
| `profit_actual`          | Decimal(16,2)            |
| `orders_actual`          | IntegerField ≥0          |
| `currency`               | CharField(3) (PHP)       |
| `notes`                  | TextField (blank)        |

### 2h — `WeeklyCommitment` (unique group + period + week_number)

clean() invariant: **`1 ≤ week_number ≤ period.weeks_count`**

| Field                    | Type                     |
|--------------------------|--------------------------|
| `group` / `period`       | FKs                      |
| `week_number`            | IntegerField (1..wc)     |
| `revenue`                | Decimal(16,2)            |
| `profit`                 | Decimal(16,2)            |
| `orders`                 | IntegerField ≥0          |
| `notes`                  | TextField (blank)        |

`build_weekly_commitment_formset(period, extra=None)`:
- `extra = max(0, period.weeks_count - existing_count)`.
- Never hardcoded 4 columns; templates and Excel export iterate weeks 1..N.

### 2i — `GroupPerformanceSnapshot` (unique group + period + meeting)

This is the **only** model that carries justified (pre-calculated) values —
every other display in the UI recomputes from base rows via service functions.

| Field                         | Type                     | Justified value at snapshot time                 |
|-------------------------------|--------------------------|--------------------------------------------------|
| `group` / `period`            | FKs                      |                                                  |
| `meeting`                     | FK → Meeting UUID NULL   | nullable → standalone snapshots always editable  |
| `created_by`                  | FK → User BigInt NULL    |                                                  |
| `revenue_target/actual/pct`   | Decimal(16,2) / (5,2)    | `actual/target*100` with target≤0 safe 0          |
| `profit_target/actual/pct`    | Decimal(16,2) / (5,2)    |                                                  |
| `profit_margin_actual`        | Decimal(5,2)             | `profit_actual/revenue_actual * 100` (0 if rev=0)|
| `revenue_deficit/profit_deficit` | Decimal(16,2)         | `actual - target` (neg = behind plan)            |
| `orders_target/actual/pct`    | Int / Int / Dec(5,2)     |                                                  |
| `deliveries_planned/achieved/on_time/pct` | Ints / Dec(5,2) | `on_time/achieved*100` (0 if achieved=0) |
| `weekly_revenue_total`        | Decimal(16,2)            | SUM(WeeklyCommitment.revenue) for the group×period|
| `notes`                       | TextField (blank)        |                                                  |

Snapshot **lock propagation** rule:
```
def is_snapshot_locked(snapshot):
    # Lazy import to avoid circular import between sales_updates and meetings modules
    from apps.meetings.models import NON_EDITABLE_STATUSES
    if snapshot.meeting_id is None:
        return False  # standalone editable draft
    return snapshot.meeting.status in NON_EDITABLE_STATUSES
```

## 3 — Calculation Layer (apps.sales_updates.services)

### 3a — Pure Helpers

```
_q(value, places=2)                                → Decimal with ROUND_HALF_UP
percentage_achieved(actual, target)                → Decimal("0") when target ≤ 0
deficit(actual, target)                            → actual - target
currency_format(value, currency=PHP, *, with_sign=False, negative_parens=False)
    Adjacent-symbol rules: "₱1,234.56"; "-₱1,234.56" default; "+₱1,234.56" signed;
    "(₱1,234.56)" negative_parens financial display.
monthly_average(values, months_count)              → sum / months_count; months_count > 0
```

### 3b — Aggregation Services

Each service walks the graph and sums / divides through `_q()` at every
aggregation boundary so intermediate errors do not compound:

- **`group_period_subtotals(group, period)`** — 16-key dict:
  revenue target/actual/pct/deficit, profit target/actual/pct/deficit,
  margin_actual, orders target/actual/pct, deliveries planned/achieved/on_time/
  on_time_pct.
- **`team_period_totals(team, period)`** — union of every group under a team;
  percent keys are recomputed (NOT averaged) against the summed targets/actuals.
- **`overall_period_totals(period)`** — sum across every active group in the
  period regardless of team.
- **`weekly_commitment_totals(group, period)`** — revenue/profit/orders rolled
  up from the individual week rows plus a comparison against sales-order actuals
  that already closed.

### 3c — `@atomic take_snapshot(group, period, *, meeting, by_user, force=False)`

1. Validates permissions (SALES_AUTHOR_ROLES).
2. Builds dict via `group_period_subtotals` + weekly rollups.
3. `GroupPerformanceSnapshot.objects.create(**justified_values)`.
4. On `IntegrityError` (unique_together 3-tuple already exists): rollback,
   return existing snapshot instead of creating duplicate.
5. Signal handler `apps.sales_updates.signals.snapshot_post_save` is connected
   via `apps.sales_updates.apps.SalesUpdatesConfig.ready()` → emits
   `log_audit_event(record=snapshot, action=ACTION_LOCK, ...)` the **first**
   time `is_snapshot_locked()` transitions from False → True. Audit write is
   deferred to `transaction.on_commit`; tests that read AuditLog MUST mark
   `@pytest.mark.django_db(transaction=True)` or the commit hook never fires.

## 4 — Snapshot Lock Matrix

| `snapshot.meeting` | `meeting.status`  | in `NON_EDITABLE_STATUSES` | `is_snapshot_locked()` | editable by SYS_ADMIN via override? |
|--------------------|-------------------|----------------------------|------------------------|-------------------------------------|
| `None`             | N/A               | N/A                        | **False** (always)     | N/A — already fully editable        |
| set                | DRAFT             | ✘                          | False                  | N/A                                  |
| set                | IN_REVIEW         | ✘                          | False                  | N/A                                  |
| set                | MINUTES_DRAFT     | ✘                          | False                  | N/A                                  |
| set                | APPROVED          | ✔                          | True                   | No — lock is structural             |
| set                | PUBLISHED         | ✔                          | True                   | No — lock is structural             |
| set                | CANCELLED         | ✔                          | True                   | No — lock is structural             |

## 5 — Template Formatting (apps.sales_updates.templatetags.sales_formatting)

5 filters + 1 simple_tag:

```django
{% load sales_formatting %}
{{ value|currency:currency }}                 → "₱1,234.56" default (minus for <0)
{{ value|currency_signed:currency }}          → "+₱1,234.56" or "-₱1,234.56"
{{ value|currency_parens:currency }}          → "(₱1,234.56)" financial-style negatives
{{ value|percentage }}                        → "12.34%"
{{ value|negative_class }}                    → "text-danger" if <0 else ""
{% currency_cell value currency signed=True %} → colored <span class="text-danger">...
{% currency_cell value currency parens=True %} → colored parentheses cell
```

All rendering follows the **no-space symbol rule**: `CURRENCY_SYMBOLS[currency]`
is concatenated directly before the integer-digit group with no space character.
This is enforced both in `currency_format()` and in `currency_cell()` — tests
assert `formatted.startswith("₱")` and `"₱ " not in formatted`.
