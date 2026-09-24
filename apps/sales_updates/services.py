from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.audit.services import log_audit_event
from apps.sales_updates.models import (
    CURRENCY_PHP,
    CURRENCY_SYMBOLS,
    DECIMAL_DIGITS,
    ZERO_DECIMAL,
    DeliveryPerformance,
    GroupPerformanceSnapshot,
    PerformanceTarget,
    ReportingPeriod,
    SalesGroup,
    SalesOrderPerformance,
    SalesTeam,
    WeeklyCommitment,
)

if TYPE_CHECKING:
    from collections.abc import Iterable

TWO_PLACES = DECIMAL_DIGITS
HUNDRED = Decimal("100")


def _q(value: Decimal | int | float | str) -> Decimal:
    """Coerce to Decimal rounded to 2 decimal places (half-up)."""
    if isinstance(value, Decimal):
        return value.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
    return Decimal(str(value)).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def percentage_achieved(
    target: Decimal | int | float | str, actual: Decimal | int | float | str
) -> Decimal:
    """Return percentage actual/target rounded to 2dp. Returns 0 when target <= 0."""
    t = _q(target)
    a = _q(actual)
    if t <= 0:
        return ZERO_DECIMAL
    return ((a / t) * HUNDRED).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def deficit(target: Decimal | int | float | str, actual: Decimal | int | float | str) -> Decimal:
    """Return actual - target. Negative = behind target, Positive = ahead of target."""
    return (_q(actual) - _q(target)).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def currency_format(
    value: Decimal | int | float | str,
    currency: str = CURRENCY_PHP,
    *,
    with_sign: bool = False,
    negative_parens: bool = False,
) -> str:
    """Format money value with currency symbol, thousands separators, 2 decimals.

    Sign contract: negative values displayed with leading minus OR parentheses when
    negative_parens=True. Rule 50 negative values rendered consistently across the
    application: by default `-₱ 1,234.56`; in financial reports `(₱ 1,234.56)`.
    """
    amount = _q(value)
    symbol = CURRENCY_SYMBOLS.get(currency, "¤")
    negative = amount < 0
    abs_amount = abs(amount)
    # Format integer with thousands separator + 2dp
    int_part, frac_part = f"{abs_amount:.2f}".split(".")
    int_part = f"{int(int_part):,}"
    body = f"{symbol}{int_part}.{frac_part}"
    if negative:
        if negative_parens:
            return f"({body})"
        return f"-{body}"
    if with_sign and amount > 0:
        return f"+{body}"
    return body


def _group_period_rows(group: SalesGroup, period: ReportingPeriod):
    target = PerformanceTarget.objects.filter(group=group, period=period).first()
    delivery = DeliveryPerformance.objects.filter(group=group, period=period).first()
    actual = SalesOrderPerformance.objects.filter(group=group, period=period).first()
    return target, delivery, actual


def group_period_subtotals(group: SalesGroup, period: ReportingPeriod) -> dict:
    """Return a dict with target/actual/deficit/percent subtotals for one group."""
    target, delivery, actual = _group_period_rows(group, period)
    revenue_t = _q(target.revenue_target) if target else ZERO_DECIMAL
    revenue_a = _q(actual.revenue_actual) if actual else ZERO_DECIMAL
    profit_t = _q(target.profit_target) if target else ZERO_DECIMAL
    profit_a = _q(actual.profit_actual) if actual else ZERO_DECIMAL
    orders_t = target.orders_target if target else 0
    orders_a = actual.orders_actual if actual else 0
    deliv_t = target.deliveries_target if target else 0
    deliv_a = delivery.deliveries_achieved if delivery else 0
    deliv_ot = delivery.deliveries_on_time if delivery else 0
    return {
        "group": group,
        "currency": (target.currency if target else period.currency),
        "revenue_target": revenue_t,
        "revenue_actual": revenue_a,
        "revenue_deficit": deficit(revenue_t, revenue_a),
        "revenue_pct": percentage_achieved(revenue_t, revenue_a),
        "profit_target": profit_t,
        "profit_actual": profit_a,
        "profit_deficit": deficit(profit_t, profit_a),
        "profit_pct": percentage_achieved(profit_t, profit_a),
        "margin_pct_target": (
            ((profit_t / revenue_t) * HUNDRED).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
            if revenue_t > 0
            else ZERO_DECIMAL
        ),
        "margin_pct_actual": (
            ((profit_a / revenue_a) * HUNDRED).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
            if revenue_a > 0
            else ZERO_DECIMAL
        ),
        "orders_target": orders_t,
        "orders_actual": orders_a,
        "orders_pct": percentage_achieved(orders_t, orders_a),
        "deliveries_target": deliv_t,
        "deliveries_achieved": deliv_a,
        "deliveries_on_time": deliv_ot,
        "deliveries_pct": percentage_achieved(deliv_t, deliv_a),
        "on_time_pct": (
            (Decimal(deliv_ot) / Decimal(deliv_a) * HUNDRED).quantize(
                TWO_PLACES, rounding=ROUND_HALF_UP
            )
            if deliv_a > 0
            else ZERO_DECIMAL
        ),
    }


def team_period_totals(team: SalesTeam, period: ReportingPeriod) -> dict:
    """Aggregate group_period_subtotals() for every group in *team* for *period*."""
    groups = team.groups.filter(is_active=True)
    rows = [group_period_subtotals(g, period) for g in groups]
    return _aggregate_rows(rows, label=f"{team.name} team totals", team=team)


def overall_period_totals(period: ReportingPeriod) -> dict:
    """Aggregate subtotals across all active groups for a reporting period."""
    groups = SalesGroup.objects.filter(is_active=True)
    rows = [group_period_subtotals(g, period) for g in groups]
    return _aggregate_rows(rows, label=f"{period.name} overall totals")


def _aggregate_rows(rows: Iterable[dict], label: str, team: SalesTeam | None = None) -> dict:
    total = {
        "label": label,
        "team": team,
        "row_count": len(rows),
        "revenue_target": ZERO_DECIMAL,
        "revenue_actual": ZERO_DECIMAL,
        "profit_target": ZERO_DECIMAL,
        "profit_actual": ZERO_DECIMAL,
        "orders_target": 0,
        "orders_actual": 0,
        "deliveries_target": 0,
        "deliveries_achieved": 0,
        "deliveries_on_time": 0,
        "rows": list(rows),
    }
    for r in rows:
        total["revenue_target"] += r["revenue_target"]
        total["revenue_actual"] += r["revenue_actual"]
        total["profit_target"] += r["profit_target"]
        total["profit_actual"] += r["profit_actual"]
        total["orders_target"] += r["orders_target"]
        total["orders_actual"] += r["orders_actual"]
        total["deliveries_target"] += r["deliveries_target"]
        total["deliveries_achieved"] += r["deliveries_achieved"]
        total["deliveries_on_time"] += r["deliveries_on_time"]
    total["revenue_deficit"] = deficit(total["revenue_target"], total["revenue_actual"])
    total["profit_deficit"] = deficit(total["profit_target"], total["profit_actual"])
    total["revenue_pct"] = percentage_achieved(total["revenue_target"], total["revenue_actual"])
    total["profit_pct"] = percentage_achieved(total["profit_target"], total["profit_actual"])
    total["orders_pct"] = percentage_achieved(total["orders_target"], total["orders_actual"])
    total["deliveries_pct"] = percentage_achieved(
        total["deliveries_target"], total["deliveries_achieved"]
    )
    total["on_time_pct"] = (
        (Decimal(total["deliveries_on_time"]) / Decimal(total["deliveries_achieved"]) * HUNDRED)
        if total["deliveries_achieved"] > 0
        else ZERO_DECIMAL
    )
    if isinstance(total["on_time_pct"], Decimal):
        total["on_time_pct"] = total["on_time_pct"].quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
    return total


def monthly_average(values: Iterable[Decimal | int | float | str], months_count: int) -> Decimal:
    """Simple arithmetic mean across N months; months_count must be positive."""
    if months_count <= 0:
        raise ValueError("months_count must be > 0 for monthly_average.")
    numerator = sum((_q(v) for v in values), ZERO_DECIMAL)
    return (numerator / Decimal(months_count)).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def weekly_commitment_totals(snapshot: GroupPerformanceSnapshot) -> dict:
    """Return totals of committed/actual revenue+profit aggregated over a snapshot's weeks."""
    weeks = snapshot.weekly_commitments.all()
    tot_committed_rev = ZERO_DECIMAL
    tot_committed_profit = ZERO_DECIMAL
    tot_actual_rev = ZERO_DECIMAL
    tot_actual_profit = ZERO_DECIMAL
    for w in weeks:
        tot_committed_rev += _q(w.committed_revenue)
        tot_committed_profit += _q(w.committed_profit)
        tot_actual_rev += _q(w.actual_revenue)
        tot_actual_profit += _q(w.actual_profit)
    return {
        "weeks_count": weeks.count(),
        "committed_revenue": tot_committed_rev,
        "committed_profit": tot_committed_profit,
        "actual_revenue": tot_actual_rev,
        "actual_profit": tot_actual_profit,
        "revenue_deficit_vs_commitment": deficit(tot_committed_rev, tot_actual_rev),
        "profit_deficit_vs_commitment": deficit(tot_committed_profit, tot_actual_profit),
        "revenue_pct_vs_commitment": percentage_achieved(tot_committed_rev, tot_actual_rev),
        "profit_pct_vs_commitment": percentage_achieved(tot_committed_profit, tot_actual_profit),
    }


@transaction.atomic
def take_snapshot(
    group: SalesGroup, period: ReportingPeriod, *, meeting=None, by_user=None, reason: str = ""
) -> GroupPerformanceSnapshot:
    """Freeze target+actual+delivery+weekly values into a GroupPerformanceSnapshot.

    Idempotent: if (group, period, meeting) already exists, return the existing row
    without duplicating it. The unique_together DB constraint prevents duplicates at
    the lowest layer even if a concurrent request sneaks past this check.
    """
    existing = GroupPerformanceSnapshot.objects.filter(
        group=group, period=period, meeting=meeting
    ).first()
    if existing is not None:
        return existing
    target, delivery, actual = _group_period_rows(group, period)
    snap = GroupPerformanceSnapshot.objects.create(
        group=group,
        period=period,
        meeting=meeting,
        revenue_target=_q(target.revenue_target) if target else ZERO_DECIMAL,
        revenue_actual=_q(actual.revenue_actual) if actual else ZERO_DECIMAL,
        profit_target=_q(target.profit_target) if target else ZERO_DECIMAL,
        profit_actual=_q(actual.profit_actual) if actual else ZERO_DECIMAL,
        orders_target=target.orders_target if target else 0,
        orders_actual=actual.orders_actual if actual else 0,
        deliveries_target=target.deliveries_target if target else 0,
        deliveries_achieved=delivery.deliveries_achieved if delivery else 0,
        deliveries_on_time=delivery.deliveries_on_time if delivery else 0,
        currency=(target.currency if target else period.currency),
        created_by=by_user,
        notes=reason,
    )
    # Copy current WeeklyCommitment rows for this group+period IF they are attached
    # to a prior snapshot; otherwise seed empty 1..N rows for period.weeks_count.
    prior_source = (
        GroupPerformanceSnapshot.objects.filter(group=group, period=period)
        .exclude(pk=snap.pk)
        .order_by("-created_at")
        .first()
    )
    if prior_source is not None:
        for week in prior_source.weekly_commitments.all():
            WeeklyCommitment.objects.create(
                snapshot=snap,
                week_number=week.week_number,
                committed_revenue=week.committed_revenue,
                committed_profit=week.committed_profit,
                actual_revenue=week.actual_revenue,
                actual_profit=week.actual_profit,
                notes=week.notes,
            )
    else:
        for n in range(1, period.weeks_count + 1):
            WeeklyCommitment.objects.get_or_create(snapshot=snap, week_number=n, defaults={})
    log_audit_event(
        record_type="sales_updates.groupperformancesnapshot",
        record=snap,
        action=AuditLog.ACTION_CREATE,
        user=by_user,
        reason=reason or f"Snapshot for {period.name}/{group.code}",
    )
    return snap


def is_snapshot_locked(snapshot: GroupPerformanceSnapshot) -> bool:
    """Rule 14: a snapshot linked to an approved/published meeting is locked.

    Circular-import safe — meetings models imported lazily. Snapshots without a
    meeting link are editable (never locked) so finance can correct figures.
    """
    if not getattr(snapshot, "meeting_id", None):
        return False
    try:
        from apps.meetings.models import NON_EDITABLE_STATUSES
    except Exception:
        NON_EDITABLE_STATUSES = set()
    return getattr(snapshot.meeting, "status", None) in NON_EDITABLE_STATUSES


def current_reporting_period() -> ReportingPeriod | None:
    """Return the OPEN reporting period whose date range contains today, if any."""
    today = timezone.now().date()
    return (
        ReportingPeriod.objects.filter(
            status="OPEN",
            start_date__lte=today,
            end_date__gte=today,
        )
        .order_by("start_date")
        .first()
    )


def sales_dashboard_data(user) -> tuple[dict, list[dict]]:
    """Dashboard widget data — lazy imported from core.views.home().

    Returns a tuple of (counts_dict, upcoming_deadlines_list) matching the 4 KPI
    cards plus "Current Period" sidebar card.
    """
    period = current_reporting_period()
    counts = {
        "current_period": period.name if period else "No open period",
        "cut_off_date": period.cut_off_date.isoformat() if period else None,
        "days_until_cutoff": period.days_until_cutoff if period else 0,
        "revenue_actual": str(ZERO_DECIMAL),
        "revenue_target": str(ZERO_DECIMAL),
        "revenue_pct": str(ZERO_DECIMAL),
        "revenue_deficit": str(ZERO_DECIMAL),
        "profit_pct_actual": str(ZERO_DECIMAL),
        "weeks_count": period.weeks_count if period else 0,
    }
    periods_summary: list[dict] = []
    if period is not None:
        totals = overall_period_totals(period)
        counts["revenue_actual"] = str(totals["revenue_actual"])
        counts["revenue_target"] = str(totals["revenue_target"])
        counts["revenue_pct"] = str(totals["revenue_pct"])
        counts["revenue_deficit"] = str(totals["revenue_deficit"])
        counts["profit_pct_actual"] = (
            str(totals["margin_pct_actual"])
            if totals.get("margin_pct_actual")
            else str(ZERO_DECIMAL)
        )
        for row in totals["rows"]:
            if row["revenue_deficit"] < 0:
                periods_summary.append(
                    {
                        "group_code": row["group"].code,
                        "group_name": row["group"].name,
                        "deficit": str(row["revenue_deficit"]),
                        "pct": str(row["revenue_pct"]),
                    }
                )
    return counts, periods_summary
