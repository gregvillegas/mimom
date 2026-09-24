from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.utils import timezone

from apps.accounts.models import User
from apps.sales_updates.models import (
    CURRENCY_USD,
    PERIOD_CLOSED,
    PERIOD_OPEN,
    DeliveryPerformance,
    GroupPerformanceSnapshot,
    PerformanceTarget,
    ReportingPeriod,
    SalesGroup,
    SalesGroupMembership,
    SalesTeam,
    WeeklyCommitment,
)
from apps.sales_updates.services import (
    _q,
    currency_format,
    deficit,
    monthly_average,
    percentage_achieved,
    weekly_commitment_totals,
)

Z = Decimal("0.00")


@pytest.fixture
def make_user(db):
    def _make(username, groups=None):
        from django.contrib.auth.models import Group as AuthGroup

        user = User.objects.create_user(
            username=username,
            email=f"{username}@example.com",
            password="pw-1234!-Strong",
        )
        for g in groups or []:
            gg, _ = AuthGroup.objects.get_or_create(name=g)
            user.groups.add(gg)
        return user

    return _make


@pytest.fixture
def period_factory(db):
    today = timezone.now().date()

    def _make(name="Q1", weeks=4, status=PERIOD_OPEN, currency="PHP"):
        return ReportingPeriod.objects.create(
            name=name,
            start_date=today - timedelta(days=7),
            end_date=today + timedelta(days=(weeks * 7) - 7),
            cut_off_date=today + timedelta(days=(weeks * 7) - 10),
            weeks_count=weeks,
            status=status,
            currency=currency,
        )

    return _make


@pytest.fixture
def team_factory(db, make_user):
    def _make(code="T1", name="Team One"):
        leader = make_user(f"lead_{code.lower()}")
        return SalesTeam.objects.create(code=code, name=name, leader=leader, is_active=True)

    return _make


@pytest.fixture
def group_factory(db, team_factory, make_user):
    def _make(code="G1", name="Group One"):
        team = team_factory(code=code + "T", name="Team " + code)
        manager = make_user(f"mgr_{code.lower()}")
        return SalesGroup.objects.create(
            code=code, name=name, team=team, manager=manager, is_active=True
        )

    return _make


# ------------------------- Calculation-only tests -------------------------


@pytest.mark.django_db
class TestCoreCalculations:
    """Rule 45 — pure Decimal arithmetic, sign conventions, rounding."""

    def test_q_quantizes_to_two_places_half_up(self):
        assert _q(Decimal("1.225")) == Decimal("1.23")
        assert _q(Decimal("1.224999")) == Decimal("1.22")
        assert _q("100.126") == Decimal("100.13")

    def test_percentage_achieved_target_zero_returns_zero(self):
        assert percentage_achieved(0, 50) == Z
        assert percentage_achieved(-5, 50) == Z

    def test_percentage_achieved_rounds_half_up(self):
        assert percentage_achieved(3, 1) == Decimal("33.33")

    def test_percentage_achieved_100_when_equal(self):
        assert percentage_achieved(100, 100) == Decimal("100.00")

    def test_deficit_sign_negative_when_behind(self):
        assert deficit(100, 90) == Decimal("-10.00")

    def test_deficit_positive_when_ahead(self):
        assert deficit(100, 120) == Decimal("20.00")

    def test_deficit_quantizes_to_2_places(self):
        assert deficit(Decimal("10"), Decimal("3.333")) == Decimal("-6.67")

    def test_monthly_average_three_weeks(self):
        values = [Decimal("10"), Decimal("20"), Decimal("30")]
        assert monthly_average(values, 3) == Decimal("20.00")

    def test_monthly_average_empty_returns_zero(self):
        assert monthly_average([], 1) == Z

    def test_monthly_average_invalid_months_count(self):
        with pytest.raises(ValueError):
            monthly_average([], 0)

    def test_monthly_average_five_weeks_rounding(self):
        values = [Decimal(1), Decimal(2), Decimal(3), Decimal(4), Decimal(5)]
        assert monthly_average(values, 5) == Decimal("3.00")

    def test_currency_format_php_default(self):
        assert currency_format(Decimal("1234.56")) == "₱1,234.56"

    def test_currency_format_usd_signed(self):
        result = currency_format(Decimal("-123.40"), CURRENCY_USD, with_sign=True)
        assert result == "-$123.40"

    def test_currency_format_jpy_negative_parens(self):
        result = currency_format(Decimal("-1234"), "JPY", negative_parens=True)
        assert result == "(¥1,234.00)"

    def test_currency_format_euro_positive_parens_is_plain(self):
        result = currency_format(Decimal("125.5"), "EUR", negative_parens=True)
        assert result == "€125.50"


# ------------------------------ Model tests ------------------------------


@pytest.mark.django_db
class TestReportingPeriodModel:
    def test_weeks_count_only_4_or_5_valid(self, period_factory):
        p = period_factory(weeks=4)
        assert p.pk is not None

    def test_weeks_count_3_fails_clean(self, period_factory):
        p = period_factory(weeks=4)
        p.weeks_count = 3
        with pytest.raises(ValidationError):
            p.full_clean()

    def test_weeks_count_6_fails_clean(self, period_factory):
        p = period_factory(weeks=4)
        p.weeks_count = 6
        with pytest.raises(ValidationError):
            p.full_clean()

    def test_days_until_cutoff_calculated(self, period_factory):
        today = timezone.now().date()
        p = ReportingPeriod(
            name="X",
            start_date=today - timedelta(days=2),
            end_date=today + timedelta(days=40),
            cut_off_date=today + timedelta(days=3),
            weeks_count=5,
        )
        assert p.days_until_cutoff == 3

    def test_is_locked_closed(self, period_factory):
        p = period_factory(status=PERIOD_CLOSED)
        assert p.is_locked is True

    def test_is_locked_open_is_false(self, period_factory):
        p = period_factory(status=PERIOD_OPEN)
        assert p.is_locked is False

    def test_end_must_be_after_start(self, period_factory):
        today = timezone.now().date()
        p = ReportingPeriod(
            name="Inv",
            start_date=today,
            end_date=today - timedelta(days=1),
            cut_off_date=today,
            weeks_count=4,
        )
        with pytest.raises(ValidationError):
            p.full_clean()


@pytest.mark.django_db
class TestPerformanceTargetUniqueTogether:
    def test_duplicate_raises_integrity_error(self, period_factory, group_factory):
        period = period_factory()
        group = group_factory()
        PerformanceTarget.objects.create(group=group, period=period)
        with pytest.raises(IntegrityError):
            PerformanceTarget.objects.create(group=group, period=period)


@pytest.mark.django_db
class TestDeliveryPerformanceModel:
    def test_clean_on_time_greater_than_achieved_fails(self, period_factory, group_factory):
        period = period_factory()
        group = group_factory()
        d = DeliveryPerformance(
            group=group,
            period=period,
            deliveries_planned=5,
            deliveries_achieved=3,
            deliveries_on_time=4,
        )
        with pytest.raises(ValidationError):
            d.full_clean()

    def test_clean_achieved_greater_than_planned_fails(self, period_factory, group_factory):
        period = period_factory()
        group = group_factory()
        d = DeliveryPerformance(
            group=group,
            period=period,
            deliveries_planned=3,
            deliveries_achieved=5,
            deliveries_on_time=1,
        )
        with pytest.raises(ValidationError):
            d.full_clean()


@pytest.mark.django_db
class TestWeeklyCommitmentWeekNumber:
    def test_max_week_number_capped(self, period_factory, group_factory, make_user):
        period = period_factory(weeks=4)
        group = group_factory()
        user = make_user("creator")
        snap = GroupPerformanceSnapshot.objects.create(
            group=group,
            period=period,
            created_by=user,
        )
        WeeklyCommitment.objects.create(
            snapshot=snap,
            week_number=4,
        )
        wc = WeeklyCommitment(snapshot=snap, week_number=5)
        with pytest.raises(ValidationError):
            wc.full_clean()

    def test_weekly_totals_sum(self, period_factory, group_factory, make_user):
        period = period_factory(weeks=4)
        group = group_factory()
        user = make_user("creator")
        snap = GroupPerformanceSnapshot.objects.create(
            group=group,
            period=period,
            created_by=user,
        )
        for w in (1, 2, 3, 4):
            WeeklyCommitment.objects.create(
                snapshot=snap,
                week_number=w,
                committed_revenue=Decimal(w) * 100,
                committed_profit=Decimal(w) * 10,
                actual_revenue=Decimal(w) * 90,
                actual_profit=Decimal(w) * 9,
            )
        totals = weekly_commitment_totals(snap)
        assert totals["committed_revenue"] == Decimal("1000.00")
        assert totals["committed_profit"] == Decimal("100.00")
        assert totals["actual_revenue"] == Decimal("900.00")
        assert totals["actual_profit"] == Decimal("90.00")


@pytest.mark.django_db
class TestGroupMembershipClean:
    def test_left_on_before_joined_fails(self, group_factory, make_user):
        group = group_factory()
        user = make_user("mem1")
        m = SalesGroupMembership(
            group=group,
            user=user,
            role="Sales Rep",
            joined_on=timezone.now().date(),
            left_on=timezone.now().date() - timedelta(days=1),
        )
        with pytest.raises(ValidationError):
            m.full_clean()
