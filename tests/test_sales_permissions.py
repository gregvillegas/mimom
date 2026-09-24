import pytest
from django.contrib.auth.models import Group as AuthGroup
from django.utils import timezone

from apps.accounts.models import User
from apps.core.permissions import (
    can_edit_sales_period,
    can_export_sales,
    can_lock_sales_snapshot,
    can_view_sales_period,
)
from apps.sales_updates.models import (
    PERIOD_CLOSED,
    PERIOD_OPEN,
    ReportingPeriod,
)


@pytest.fixture
def make_user(db):
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
        name="P",
        start_date=today,
        end_date=today,
        cut_off_date=today,
        weeks_count=4,
        status=PERIOD_OPEN,
        currency="PHP",
    )


@pytest.mark.django_db
class TestSalesPermissions:
    def test_system_admin_can_view(self, make_user):
        u = make_user("admin", ["System Administrator"])
        assert can_view_sales_period(u) is True

    def test_viewer_role_can_view(self, make_user):
        u = make_user("viewer", ["Viewer"])
        assert can_view_sales_period(u) is True

    def test_unassigned_no_view(self, make_user):
        u = make_user("x")
        assert can_view_sales_period(u) is False

    def test_viewer_cannot_edit(self, make_user, period):
        u = make_user("viewer", ["Viewer"])
        assert can_edit_sales_period(u, period) is False

    def test_sales_author_can_edit(self, make_user, period):
        u = make_user("auth", ["Department Contributor"])
        assert can_edit_sales_period(u, period) is True

    def test_closed_period_blocks_non_superuser(self, make_user, period):
        period.status = PERIOD_CLOSED
        period.save()
        u = make_user("auth", ["Department Contributor"])
        assert can_edit_sales_period(u, period) is False

    def test_export_requires_admin_or_management(self, make_user):
        admin = make_user("a", ["System Administrator"])
        mgmt = make_user("m", ["Management Administrator"])
        viewer = make_user("v", ["Viewer"])
        assert can_export_sales(admin) is True
        assert can_export_sales(mgmt) is True
        assert can_export_sales(viewer) is False

    def test_lock_requires_meeting_chair_or_higher(self, make_user):
        chair = make_user("c", ["Meeting Chairperson"])
        mgmt = make_user("m", ["Management Administrator"])
        sec = make_user("s", ["Minutes Secretary"])
        dept = make_user("d", ["Department Contributor"])
        assert can_lock_sales_snapshot(chair) is True
        assert can_lock_sales_snapshot(mgmt) is True
        assert can_lock_sales_snapshot(sec) is False
        assert can_lock_sales_snapshot(dept) is False
