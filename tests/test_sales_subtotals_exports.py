from datetime import timedelta
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.meetings.models import (
    STATUS_APPROVED,
    STATUS_DRAFT,
    STATUS_PUBLISHED,
    Meeting,
    MeetingType,
)
from apps.sales_updates.models import (
    PerformanceTarget,
)
from apps.sales_updates.services import (
    group_period_subtotals,
    is_snapshot_locked,
    overall_period_totals,
    take_snapshot,
    team_period_totals,
)


@pytest.fixture
def make_user(db):
    from django.contrib.auth.models import Group as AuthGroup

    from apps.accounts.models import User

    def _make(username, groups=None):
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
    from datetime import timedelta

    from django.utils import timezone

    from apps.sales_updates.models import PERIOD_OPEN, ReportingPeriod

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
    from apps.sales_updates.models import SalesTeam

    def _make(code="T1", name="Team One"):
        leader = make_user(f"lead_{code.lower()}")
        return SalesTeam.objects.create(code=code, name=name, leader=leader, is_active=True)

    return _make


@pytest.fixture
def group_factory(db, team_factory, make_user):
    from apps.sales_updates.models import SalesGroup

    def _make(code="G1", name="Group One"):
        team = team_factory(code=code + "T", name="Team " + code)
        manager = make_user(f"mgr_{code.lower()}")
        return SalesGroup.objects.create(
            code=code, name=name, team=team, manager=manager, is_active=True
        )

    return _make


@pytest.fixture
def mtype(db):
    return MeetingType.objects.create(name="Weekly Management", code="WEEKLY")


@pytest.mark.django_db
class TestSnapshotIdempotency:
    def test_take_snapshot_duplicate_returns_same_object(
        self, period_factory, group_factory, make_user
    ):
        period = period_factory()
        group = group_factory()
        user = make_user("u1")
        s1 = take_snapshot(group, period, by_user=user, reason="first")
        s2 = take_snapshot(group, period, by_user=user, reason="second")
        assert s1.pk == s2.pk


@pytest.mark.django_db
class TestSnapshotLockPropagation:
    def test_snapshot_without_meeting_unlocked(self, period_factory, group_factory, make_user):
        period = period_factory()
        group = group_factory()
        user = make_user("u1")
        snap = take_snapshot(group, period, by_user=user)
        assert is_snapshot_locked(snap) is False

    def test_snapshot_with_draft_meeting_unlocked(
        self, db, period_factory, group_factory, make_user, mtype
    ):
        period = period_factory()
        group = group_factory()
        user = make_user("u1", groups=["System Administrator"])
        mtg = Meeting.objects.create(
            type=mtype,
            title="M",
            start_at=timezone.now() + timedelta(days=1),
            end_at=timezone.now() + timedelta(days=1, hours=1),
            status=STATUS_DRAFT,
            created_by=user,
            last_modified_by=user,
        )
        snap = take_snapshot(group, period, meeting=mtg, by_user=user)
        assert is_snapshot_locked(snap) is False

    def test_snapshot_approved_meeting_locked(
        self, db, period_factory, group_factory, make_user, mtype
    ):
        period = period_factory()
        group = group_factory()
        user = make_user("u1", groups=["System Administrator"])
        mtg = Meeting.objects.create(
            type=mtype,
            title="M",
            start_at=timezone.now() - timedelta(days=1),
            end_at=timezone.now() - timedelta(days=1) + timedelta(hours=1),
            status=STATUS_APPROVED,
            created_by=user,
            last_modified_by=user,
        )
        snap = take_snapshot(group, period, meeting=mtg, by_user=user)
        assert is_snapshot_locked(snap) is True

    def test_snapshot_published_meeting_locked(
        self, db, period_factory, group_factory, make_user, mtype
    ):
        period = period_factory()
        group = group_factory()
        user = make_user("u1", groups=["System Administrator"])
        mtg = Meeting.objects.create(
            type=mtype,
            title="M",
            start_at=timezone.now() - timedelta(days=1),
            end_at=timezone.now() - timedelta(days=1) + timedelta(hours=1),
            status=STATUS_PUBLISHED,
            created_by=user,
            last_modified_by=user,
        )
        snap = take_snapshot(group, period, meeting=mtg, by_user=user)
        assert is_snapshot_locked(snap) is True


@pytest.mark.django_db
class TestSubtotals:
    def test_subtotals_uses_decimal_rounding(self, period_factory, group_factory, make_user):
        period = period_factory()
        group = group_factory()
        user = make_user("u1")
        PerformanceTarget.objects.create(
            group=group,
            period=period,
            revenue_target=Decimal("300"),
            profit_target=Decimal("30"),
            orders_target=10,
            deliveries_target=5,
            last_modified_by=user,
        )
        from apps.sales_updates.models import (
            DeliveryPerformance,
            SalesOrderPerformance,
        )

        SalesOrderPerformance.objects.create(
            group=group,
            period=period,
            revenue_actual=Decimal("150.00"),
            profit_actual=Decimal("12.00"),
            orders_actual=5,
            last_modified_by=user,
        )
        DeliveryPerformance.objects.create(
            group=group,
            period=period,
            deliveries_planned=5,
            deliveries_achieved=3,
            deliveries_on_time=2,
            last_modified_by=user,
        )
        sub = group_period_subtotals(group, period)
        assert sub["revenue_pct"] == Decimal("50.00")
        assert sub["revenue_deficit"] == Decimal("-150.00")
        assert sub["margin_pct_target"] == Decimal("10.00")
        assert sub["margin_pct_actual"] == Decimal("8.00")
        assert sub["on_time_pct"] == Decimal("66.67")

    def test_overall_period_aggregates(self, db, team_factory, make_user, period_factory):
        team = team_factory(code="T", name="T")
        period = period_factory()
        user = make_user("u1")
        from apps.sales_updates.models import DeliveryPerformance as DP
        from apps.sales_updates.models import PerformanceTarget as PT
        from apps.sales_updates.models import SalesGroup as G
        from apps.sales_updates.models import SalesOrderPerformance as SOP

        g1 = G.objects.create(code="g1", name="g1", team=team, manager=user, is_active=True)
        g2 = G.objects.create(code="g2", name="g2", team=team, manager=user, is_active=True)
        for g in (g1, g2):
            PT.objects.create(
                group=g,
                period=period,
                revenue_target=100,
                profit_target=10,
                orders_target=10,
                deliveries_target=10,
                last_modified_by=user,
            )
            SOP.objects.create(
                group=g,
                period=period,
                revenue_actual=80,
                profit_actual=8,
                orders_actual=8,
                last_modified_by=user,
            )
            DP.objects.create(
                group=g,
                period=period,
                deliveries_planned=10,
                deliveries_achieved=8,
                deliveries_on_time=4,
                last_modified_by=user,
            )
        totals = overall_period_totals(period)
        assert totals["revenue_target"] == Decimal("200.00")
        assert totals["revenue_actual"] == Decimal("160.00")
        assert totals["revenue_pct"] == Decimal("80.00")
        assert totals["revenue_deficit"] == Decimal("-40.00")

    def test_team_period_totals_matches_overall(self, team_factory, make_user, period_factory, db):
        team = team_factory(code="T2", name="T2")
        period = period_factory()
        user = make_user("u2")
        from apps.sales_updates.models import DeliveryPerformance as DP
        from apps.sales_updates.models import PerformanceTarget as PT
        from apps.sales_updates.models import SalesGroup as G
        from apps.sales_updates.models import SalesOrderPerformance as SOP

        g = G.objects.create(code="g1t2", name="g1t2", team=team, manager=user, is_active=True)
        PT.objects.create(
            group=g,
            period=period,
            revenue_target=100,
            profit_target=10,
            orders_target=10,
            deliveries_target=10,
            last_modified_by=user,
        )
        SOP.objects.create(
            group=g,
            period=period,
            revenue_actual=100,
            profit_actual=10,
            orders_actual=10,
            last_modified_by=user,
        )
        DP.objects.create(
            group=g,
            period=period,
            deliveries_planned=10,
            deliveries_achieved=10,
            deliveries_on_time=10,
            last_modified_by=user,
        )
        team_totals = team_period_totals(team, period)
        assert team_totals["revenue_target"] == Decimal("100.00")
        assert team_totals["revenue_pct"] == Decimal("100.00")


@pytest.mark.django_db(transaction=True)
class TestAuditLockEvent:
    def test_snapshot_signal_emits_lock_on_save(
        self, db, period_factory, group_factory, make_user, mtype
    ):
        period = period_factory()
        group = group_factory()
        user = make_user("u1", groups=["System Administrator"])
        mtg = Meeting.objects.create(
            type=mtype,
            title="M",
            start_at=timezone.now(),
            end_at=timezone.now() + timedelta(hours=1),
            status=STATUS_APPROVED,
            created_by=user,
            last_modified_by=user,
        )
        AuditLog.objects.all().delete()
        take_snapshot(group, period, meeting=mtg, by_user=user)
        assert AuditLog.objects.filter(action=AuditLog.ACTION_LOCK).count() >= 1


@pytest.mark.django_db(transaction=True)
class TestExportView:
    def test_export_view_magic_bytes(self, client, period_factory, make_user):
        period = period_factory()
        user = make_user("export_admin", ["System Administrator"])
        client.force_login(user)
        resp = client.get(reverse("sales_updates:export_excel_period", args=[period.pk]))
        assert resp.status_code == 200
        assert resp["Content-Type"].startswith("application/vnd.openxmlformats")
        body = b"".join(resp.streaming_content)
        assert body[:4] == b"PK\x03\x04"

    def test_export_view_requires_export_permission(self, client, period_factory, make_user):
        period = period_factory()
        user = make_user("viewer_only", ["Viewer"])
        client.force_login(user)
        resp = client.get(reverse("sales_updates:export_excel_period", args=[period.pk]))
        assert resp.status_code in (302, 403)

    def test_export_audit_logged(self, client, period_factory, make_user):
        period = period_factory()
        user = make_user("ea", ["System Administrator"])
        client.force_login(user)
        AuditLog.objects.all().delete()
        resp = client.get(reverse("sales_updates:export_excel_period", args=[period.pk]))
        assert resp.status_code == 200
        assert AuditLog.objects.filter(action=AuditLog.ACTION_EXPORT).count() >= 1
