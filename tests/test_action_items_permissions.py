from datetime import timedelta

import pytest
from django.contrib.auth.models import AnonymousUser
from django.utils import timezone

from apps.accounts.models import Department, DepartmentMembership, User
from apps.action_items.models import (
    STATUS_COMPLETED,
    STATUS_OPEN,
    ActionItem,
)
from apps.core.permissions import (
    can_complete_actionitem,
    can_create_actionitem,
    can_edit_actionitem,
    can_reopen_actionitem,
    can_view_actionitem,
)


@pytest.fixture
def dept(db):
    return Department.objects.create(name="Sales", code="SAL")


@pytest.fixture
def make_user(db):
    from django.contrib.auth.models import Group

    def _make(username, groups=None, **extra):
        email = extra.pop("email", None) or f"{username}@example.com"
        user = User.objects.create_user(
            username=username, email=email, password="pw-1234!-Strong", **extra
        )
        if groups:
            for name in groups:
                g, _ = Group.objects.get_or_create(name=name)
                user.groups.add(g)
        return user

    return _make


@pytest.fixture
def action_item(dept, make_user):
    owner = make_user("p_owner", groups=["Department Contributor"])
    DepartmentMembership.objects.create(
        user=owner, department=dept, is_active=True, is_contributor=True
    )
    today = timezone.now().date()
    return ActionItem.objects.create(
        title="Perm test",
        department=dept,
        created_by=owner,
        owner=owner,
        status=STATUS_OPEN,
        due_date=today + timedelta(days=10),
    )


class TestAnonymous:
    def test_anon_no_create(self, make_user):
        assert not can_create_actionitem(AnonymousUser())


class TestCreatePredicates:
    def test_create_roles(self, make_user):
        allowed = [
            "System Administrator",
            "Management Administrator",
            "Meeting Chairperson",
            "Minutes Secretary",
            "Department Contributor",
        ]
        for role in allowed:
            u = make_user(f"cr_{role}", groups=[role])
            assert can_create_actionitem(u)

    def test_viewer_cannot_create(self, make_user):
        u = make_user("viewer_cr", groups=["Viewer"])
        assert not can_create_actionitem(u)


class TestViewPredicates:
    def test_superuser_can_view(self, make_user, action_item):
        su = make_user("su_view", is_superuser=True)
        assert can_view_actionitem(su, action_item)

    def test_owner_can_view(self, make_user, action_item):
        assert can_view_actionitem(action_item.owner, action_item)

    def test_assignee_can_view(self, make_user, action_item):
        assignee = make_user("a_view")
        action_item.assignees.create(user=assignee, is_primary=False, is_supporting=True)
        assert can_view_actionitem(assignee, action_item)

    def test_viewer_allowed_to_view(self, make_user, action_item, dept):
        v = make_user("av_vw", groups=["Viewer"])
        assert can_view_actionitem(v, action_item)


class TestEditPredicates:
    def test_owner_can_edit(self, action_item):
        assert can_edit_actionitem(action_item.owner, action_item)

    def test_locked_items_terminal_prevent_edit(self, make_user, action_item, sys_admin=None):
        action_item.status = STATUS_COMPLETED
        action_item.progress_pct = 100
        assert not can_edit_actionitem(action_item.owner, action_item)

    def test_sysadmin_ign_locked(self, make_user, action_item):
        action_item.status = STATUS_COMPLETED
        action_item.progress_pct = 100
        action_item.save()
        admin = make_user("ai_sya", groups=["System Administrator"])
        assert not can_edit_actionitem(admin, action_item)


class TestCompletePredicates:
    def test_primary_assignee_owner_admin(self, action_item):
        assert can_complete_actionitem(action_item.owner, action_item)

    def test_anon_complete(self, make_user, action_item):
        u = make_user("randy", groups=["Viewer"])
        not can_complete_actionitem(u, action_item)


class TestReopenPredicates:
    def test_requires_admin(self, make_user, action_item):
        mgmt = make_user("ai_mg", groups=["Management Administrator"])
        assert can_reopen_actionitem(mgmt, action_item)
        assert not can_reopen_actionitem(action_item.owner, action_item)

    def test_sys_admin_allowed_owner_viewer_denied(self, make_user, action_item):
        from apps.core.permissions import can_reopen_actionitem

        sys = make_user("ai_sa", groups=["System Administrator"])
        chair = make_user("ai_ch", groups=["Meeting Chairperson"])
        viewer = make_user("ai_v", groups=["Viewer"])
        assert can_reopen_actionitem(sys, action_item) is True
        assert can_reopen_actionitem(chair, action_item) is False
        assert can_reopen_actionitem(viewer, action_item) is False

    def test_superuser_allowed(self, make_user, action_item):
        from apps.core.permissions import can_reopen_actionitem

        su = make_user("ai_su", is_superuser=True)
        assert can_reopen_actionitem(su, action_item) is True


@pytest.mark.django_db
class TestCompletePredicatesExtended:
    def test_allowed_roles(self, make_user, action_item):
        from apps.core.permissions import can_complete_actionitem

        sys = make_user("c_sa", groups=["System Administrator"])
        mgmt = make_user("c_ma", groups=["Management Administrator"])
        chair = make_user("c_ch", groups=["Meeting Chairperson"])
        sec = make_user("c_se", groups=["Minutes Secretary"])
        dc = make_user("c_dc", groups=["Department Contributor"])
        vw = make_user("c_vw", groups=["Viewer"])
        assert can_complete_actionitem(sys, action_item)
        assert can_complete_actionitem(mgmt, action_item)
        assert can_complete_actionitem(chair, action_item)
        assert can_complete_actionitem(sec, action_item)
        assert not can_complete_actionitem(vw, action_item)
        assert not can_complete_actionitem(dc, action_item)
