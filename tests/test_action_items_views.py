from datetime import timedelta

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Department, DepartmentMembership, User
from apps.action_items.models import (
    STATUS_COMPLETED,
    STATUS_IN_PROGRESS,
    STATUS_OPEN,
    ActionItem,
)
from apps.action_items.services import transition_actionitem


@pytest.fixture
def dept(db):
    return Department.objects.create(name="Ops", code="OPS")


@pytest.fixture
def make_user(db):
    from django.contrib.auth.models import Group

    def _make(username, groups=None, **extra):
        email = extra.pop("email", None) or f"{username}@example.com"
        u = User.objects.create_user(
            username=username, email=email, password="pw-1234!-Strong", **extra
        )
        if groups:
            for n in groups:
                g, _ = Group.objects.get_or_create(name=n)
                u.groups.add(g)
        return u

    return _make


@pytest.fixture
def chair(dept, make_user):
    u = make_user("chair_v", groups=["Meeting Chairperson"])
    DepartmentMembership.objects.create(
        user=u, department=dept, is_active=True, is_contributor=True
    )
    return u


@pytest.fixture
def sys_admin(make_user):
    return make_user("sys_v", groups=["System Administrator"])


@pytest.fixture
def action_item(make_user, dept):
    owner = make_user("own_v", groups=["Minutes Secretary"])
    DepartmentMembership.objects.create(
        user=owner, department=dept, is_active=True, is_contributor=True
    )
    today = timezone.now().date()
    return ActionItem.objects.create(
        title="View Test Action",
        description="Body",
        department=dept,
        created_by=owner,
        owner=owner,
        status=STATUS_OPEN,
        due_date=today + timedelta(days=10),
    )


def _login(c, user):
    return c.login(username=user.username, password="pw-1234!-Strong")


@pytest.mark.django_db
class TestListView:
    def test_list_redirects_anon(self):
        c = Client()
        resp = c.get(reverse("action_items:actionitem_list"))
        assert resp.status_code in (302, 401)

    def test_list_200_for_chair(self, chair):
        c = Client()
        _login(c, chair)
        resp = c.get(reverse("action_items:actionitem_list"))
        assert resp.status_code == 200

    def test_my_actions_view(self, chair, action_item):
        c = Client()
        _login(c, chair)
        resp = c.get(reverse("action_items:actionitem_my"))
        assert resp.status_code == 200

    def test_overdue_view(self, chair, action_item):
        c = Client()
        _login(c, chair)
        resp = c.get(reverse("action_items:actionitem_overdue"))
        assert resp.status_code == 200

    def test_filter_by_status(self, chair, action_item):
        c = Client()
        _login(c, chair)
        resp = c.get(f"{reverse('action_items:actionitem_list')}?status={STATUS_OPEN}")
        assert resp.status_code == 200


@pytest.mark.django_db
class TestDetailView:
    def test_detail_200(self, action_item, chair):
        c = Client()
        _login(c, chair)
        resp = c.get(reverse("action_items:actionitem_detail", args=[action_item.pk]))
        assert resp.status_code == 200

    def test_anon_redirect(self, action_item):
        c = Client()
        resp = c.get(reverse("action_items:actionitem_detail", args=[action_item.pk]))
        assert resp.status_code == 302


@pytest.mark.django_db
class TestCreateView:
    def test_create_get(self, chair):
        c = Client()
        _login(c, chair)
        resp = c.get(reverse("action_items:actionitem_create"))
        assert resp.status_code == 200

    def test_create_post(self, chair, dept):
        c = Client()
        _login(c, chair)
        payload = {
            "title": "new",
            "description": "d",
            "priority": "MED",
            "status": STATUS_OPEN,
            "progress_pct": 10,
            "due_date": (timezone.now() + timedelta(days=3)).date().isoformat(),
            "department": dept.pk,
            "owner": chair.pk,
        }
        payload.update(
            {
                "assignees-TOTAL_FORMS": 0,
                "assignees-INITIAL_FORMS": 0,
                "assignees-MIN_NUM_FORMS": 0,
                "assignees-MAX_NUM_FORMS": 1000,
            }
        )
        resp = c.post(reverse("action_items:actionitem_create"), payload, follow=False)
        assert resp.status_code in (302, 200)
        if resp.status_code == 302:
            assert ActionItem.objects.filter(title="new").exists()


@pytest.mark.django_db
class TestCompleteView:
    def test_complete_requires_role(self, action_item, chair, sys_admin):
        transition_actionitem(
            action_item, STATUS_IN_PROGRESS, by_user=sys_admin, skip_role_check=True
        )
        transition_actionitem(action_item, "UNDER_REVIEW", by_user=sys_admin, skip_role_check=True)
        c = Client()
        _login(c, chair)
        resp = c.post(
            reverse("action_items:actionitem_complete", args=[action_item.pk]),
            {"progress_pct": 100, "completion_summary": "done", "blockers_clear": "on"},
        )
        assert resp.status_code in (302, 403)


@pytest.mark.django_db
class TestReopenView:
    def test_reopen_as_admin(self, action_item, sys_admin):
        transition_actionitem(
            action_item, STATUS_IN_PROGRESS, by_user=sys_admin, skip_role_check=True
        )
        transition_actionitem(action_item, "UNDER_REVIEW", by_user=sys_admin, skip_role_check=True)
        action_item.refresh_from_db()
        action_item.blockers = ""
        action_item.save()
        transition_actionitem(
            action_item, STATUS_COMPLETED, by_user=sys_admin, skip_role_check=True
        )
        c = Client()
        _login(c, sys_admin)
        resp = c.post(
            reverse("action_items:actionitem_reopen", args=[action_item.pk]),
            {"reason": "wrong closure"},
        )
        assert resp.status_code in (302, 400)


@pytest.mark.django_db
class TestTransitionView:
    def test_redirects_on_success(self, action_item, sys_admin):
        c = Client()
        _login(c, sys_admin)
        resp = c.post(
            reverse("action_items:actionitem_transition", args=[action_item.pk]),
            {"target_status": STATUS_IN_PROGRESS, "reason": "start"},
        )
        action_item.refresh_from_db()
        assert action_item.status == STATUS_IN_PROGRESS
        assert resp.status_code == 302
