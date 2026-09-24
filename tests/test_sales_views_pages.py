from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.sales_updates.models import (
    PERIOD_OPEN,
    GroupPerformanceSnapshot,
    PerformanceTarget,
    ReportingPeriod,
    SalesGroup,
    SalesTeam,
)


@pytest.fixture
def make_user(db):
    from django.contrib.auth.models import Group as AuthGroup

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
def period(db):
    today = timezone.now().date()
    return ReportingPeriod.objects.create(
        name="Q1",
        start_date=today - timedelta(days=7),
        end_date=today + timedelta(days=21),
        cut_off_date=today + timedelta(days=18),
        weeks_count=4,
        status=PERIOD_OPEN,
        currency="PHP",
    )


@pytest.fixture
def team(db, make_user):
    return SalesTeam.objects.create(
        code="T1", name="Team 1", is_active=True, leader=make_user("lead1")
    )


@pytest.fixture
def group(db, team, make_user):
    return SalesGroup.objects.create(
        code="G1",
        name="Group 1",
        team=team,
        manager=make_user("mgr1"),
        is_active=True,
    )


@pytest.mark.django_db
class TestPagesSmoke:
    def test_period_list_auth_required(self, client, db):
        resp = client.get(reverse("sales_updates:period_list"))
        assert resp.status_code in (302, 401)

    def test_period_list_authorized(self, client, make_user, period):
        user = make_user("viewer", ["Viewer"])
        client.force_login(user)
        resp = client.get(reverse("sales_updates:period_list"))
        assert resp.status_code == 200

    def test_group_dashboard_authorized(self, client, make_user, period):
        user = make_user("viewer", ["Viewer"])
        client.force_login(user)
        resp = client.get(reverse("sales_updates:group_dashboard"))
        assert resp.status_code == 200
        resp2 = client.get(reverse("sales_updates:group_dashboard_period", args=[period.pk]))
        assert resp2.status_code == 200

    def test_export_page_authorized(self, client, make_user, period):
        user = make_user("viewer", ["Viewer"])
        client.force_login(user)
        resp = client.get(reverse("sales_updates:exports_page"))
        assert resp.status_code == 200

    def test_group_period_detail(self, client, make_user, period, group):
        user = make_user("viewer", ["Viewer"])
        client.force_login(user)
        url = reverse("sales_updates:group_period_detail", args=[group.pk, period.pk])
        resp = client.get(url)
        assert resp.status_code == 200

    def test_period_create(self, client, make_user, period):
        user = make_user("admin", ["System Administrator"])
        client.force_login(user)
        today = timezone.now().date()
        client.post(
            reverse("sales_updates:period_create"),
            {
                "name": "Q2",
                "start_date": (today + timedelta(days=30)).isoformat(),
                "end_date": (today + timedelta(days=60)).isoformat(),
                "cut_off_date": (today + timedelta(days=55)).isoformat(),
                "weeks_count": 4,
                "status": "DRAFT",
                "currency": "USD",
                "notes": "",
            },
            follow=True,
        )
        assert ReportingPeriod.objects.filter(name="Q2").exists()

    def test_target_upsert(self, client, make_user, period, group):
        user = make_user("editor", ["Department Contributor"])
        client.force_login(user)
        url = reverse("sales_updates:target_upsert", args=[group.pk, period.pk])
        client.post(
            url,
            {
                "group": str(group.pk),
                "period": str(period.pk),
                "revenue_target": "10000.00",
                "profit_target": "2000.00",
                "orders_target": "10",
                "deliveries_target": "5",
                "currency": "PHP",
            },
            follow=True,
        )
        assert PerformanceTarget.objects.filter(group=group, period=period).exists()

    def test_snapshot_detail(self, client, make_user, period, group):
        user = make_user("admin", ["System Administrator"])
        client.force_login(user)
        snap = GroupPerformanceSnapshot.objects.create(
            group=group,
            period=period,
            created_by=user,
        )
        url = reverse("sales_updates:snapshot_detail", args=[snap.pk])
        resp = client.get(url)
        assert resp.status_code == 200

    def test_snapshot_printable(self, client, make_user, period, group):
        user = make_user("viewer", ["Viewer"])
        client.force_login(user)
        snap = GroupPerformanceSnapshot.objects.create(
            group=group,
            period=period,
            created_by=user,
        )
        url = reverse("sales_updates:snapshot_printable", args=[snap.pk])
        resp = client.get(url)
        assert resp.status_code == 200

    def test_home_dashboard_with_sales(self, client, make_user):
        user = make_user("any", ["Viewer"])
        client.force_login(user)
        resp = client.get(reverse("home"))
        assert resp.status_code == 200


@pytest.mark.django_db
class TestDashboardViews:
    def test_core_home_lazy_import_never_500(self, client, make_user):
        user = make_user("u1", ["System Administrator"])
        client.force_login(user)
        resp = client.get(reverse("home"))
        assert resp.status_code == 200
