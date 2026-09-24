from datetime import timedelta

import pytest
from django.utils import timezone

from apps.accounts.models import Department, DepartmentMembership, User
from apps.action_items.models import (
    STATUS_CANCELLED,
    STATUS_COMPLETED,
    STATUS_IN_PROGRESS,
    STATUS_OPEN,
    ActionItem,
    ActionItemCarryForwardLink,
)
from apps.action_items.services import (
    carry_forward_action_items,
    transition_actionitem,
)


@pytest.fixture
def dept(db):
    return Department.objects.create(name="QAT", code="QAT")


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
def admin(make_user):
    return make_user("cf_a", groups=["System Administrator"])


@pytest.fixture
def owner(make_user, dept):
    u = make_user("cf_o", groups=["Minutes Secretary"])
    DepartmentMembership.objects.create(
        user=u, department=dept, is_active=True, is_contributor=True
    )
    return u


@pytest.fixture
def items(owner, dept):
    today = timezone.now().date()
    items_list = []
    for i, title in enumerate(["A", "B", "C", "D"]):
        item = ActionItem.objects.create(
            title=f"CF {title}",
            department=dept,
            created_by=owner,
            owner=owner,
            status=STATUS_OPEN,
            due_date=today + timedelta(days=3 + i),
            priority="MED",
        )
        items_list.append(item)
    return items_list


@pytest.mark.django_db(transaction=True)
class TestCarryForward:
    def test_creates_four_new_open_items(self, items, admin):
        created = carry_forward_action_items(items, by_user=admin)
        assert len(created) == 4
        for new in created:
            assert new.status == STATUS_OPEN
            assert new.carried_forward_from is not None

    def test_skips_terminal_status_by_default(self, items, admin):
        to_complete = items[0]
        transition_actionitem(to_complete, STATUS_IN_PROGRESS, by_user=admin, skip_role_check=True)
        transition_actionitem(to_complete, "UNDER_REVIEW", by_user=admin, skip_role_check=True)
        to_complete.refresh_from_db()
        to_complete.blockers = ""
        to_complete.save()
        transition_actionitem(to_complete, STATUS_COMPLETED, by_user=admin, skip_role_check=True)
        items[1].status = STATUS_CANCELLED
        items[1].save()
        created = carry_forward_action_items(items, by_user=admin)
        assert len(created) == 2

    def test_override_includes_completed(self, items, admin):
        transition_actionitem(items[0], STATUS_IN_PROGRESS, by_user=admin, skip_role_check=True)
        transition_actionitem(items[0], "UNDER_REVIEW", by_user=admin, skip_role_check=True)
        items[0].refresh_from_db()
        items[0].blockers = ""
        items[0].save()
        transition_actionitem(items[0], STATUS_COMPLETED, by_user=admin, skip_role_check=True)
        created = carry_forward_action_items(items, by_user=admin, include_completed=True)
        assert len(created) == 4

    def test_override_includes_cancelled(self, items, admin):
        items[0].status = STATUS_CANCELLED
        items[0].save()
        created = carry_forward_action_items(items, by_user=admin, include_cancelled=True)
        assert len(created) == 4

    def test_override_both_terminals_included(self, items, admin):
        transition_actionitem(items[0], STATUS_IN_PROGRESS, by_user=admin, skip_role_check=True)
        transition_actionitem(items[0], "UNDER_REVIEW", by_user=admin, skip_role_check=True)
        items[0].refresh_from_db()
        items[0].blockers = ""
        items[0].save()
        transition_actionitem(items[0], STATUS_COMPLETED, by_user=admin, skip_role_check=True)
        items[1].status = STATUS_CANCELLED
        items[1].save()
        created = carry_forward_action_items(
            items, by_user=admin, include_completed=True, include_cancelled=True
        )
        assert len(created) == 4

    def test_idempotent_same_scope(self, items, admin):
        first = carry_forward_action_items(items, by_user=admin)
        second = carry_forward_action_items(items, by_user=admin)
        assert len(first) == len(second)
        for a, b in zip(first, second, strict=True):
            assert a.pk == b.pk

    def test_creates_link_records(self, items, admin):
        before = ActionItemCarryForwardLink.objects.count()
        carry_forward_action_items(items, by_user=admin)
        after = ActionItemCarryForwardLink.objects.count()
        assert after - before == 4

    def test_empty_sources_returns_empty(self, admin):
        assert carry_forward_action_items([], by_user=admin) == []

    def test_audit_for_carry_forward(self, items, admin):
        carry_forward_action_items(items, by_user=admin)
        from apps.audit.models import AuditLog

        assert AuditLog.objects.filter(
            record_type="action_items.actionitem", action="CARRY_FORWARD"
        ).count() >= len(items)


@pytest.mark.django_db(transaction=True)
class TestCarryForwardDuplicatePrevent:
    def test_different_scopes_produce_multiple(self, items, admin):
        a = carry_forward_action_items(items, by_user=admin, target_scope_key="scope-a")
        b = carry_forward_action_items(items, by_user=admin, target_scope_key="scope-b")
        assert len(a) == len(b)
        assert {x.pk for x in a} != {x.pk for x in b}
