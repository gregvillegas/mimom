from datetime import timedelta

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Department, DepartmentMembership, User
from apps.action_items.models import (
    STATUS_IN_PROGRESS,
    STATUS_OPEN,
    ActionItem,
)


@pytest.fixture
def dept(db):
    return Department.objects.create(name="HR", code="HR")


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
def user(make_user, dept):
    u = make_user("pages_u", groups=["Minutes Secretary"])
    DepartmentMembership.objects.create(
        user=u, department=dept, is_active=True, is_contributor=True
    )
    return u


def _login(c, u):
    return c.login(username=u.username, password="pw-1234!-Strong")


@pytest.mark.django_db
class TestPages:
    def test_list_page(self, user):
        c = Client()
        _login(c, user)
        resp = c.get(reverse("action_items:actionitem_list"))
        assert resp.status_code == 200

    def test_my_page(self, user):
        c = Client()
        _login(c, user)
        resp = c.get(reverse("action_items:actionitem_my"))
        assert resp.status_code == 200

    def test_department_page(self, user):
        c = Client()
        _login(c, user)
        resp = c.get(reverse("action_items:actionitem_department"))
        assert resp.status_code == 200

    def test_overdue_page(self, user):
        c = Client()
        _login(c, user)
        resp = c.get(reverse("action_items:actionitem_overdue"))
        assert resp.status_code == 200

    def test_detail_page(self, user, dept):
        today = timezone.now().date()
        item = ActionItem.objects.create(
            title="Detail page",
            department=dept,
            created_by=user,
            owner=user,
            status=STATUS_IN_PROGRESS,
            due_date=today + timedelta(days=3),
        )
        c = Client()
        _login(c, user)
        resp = c.get(reverse("action_items:actionitem_detail", args=[item.pk]))
        assert resp.status_code == 200

    def test_create_page(self, user):
        c = Client()
        _login(c, user)
        resp = c.get(reverse("action_items:actionitem_create"))
        assert resp.status_code == 200

    def test_edit_page(self, user, dept):
        today = timezone.now().date()
        item = ActionItem.objects.create(
            title="Edit page",
            department=dept,
            created_by=user,
            owner=user,
            status=STATUS_OPEN,
            due_date=today + timedelta(days=5),
        )
        c = Client()
        _login(c, user)
        resp = c.get(reverse("action_items:actionitem_update", args=[item.pk]))
        assert resp.status_code == 200
