import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.urls import reverse

from apps.accounts.forms import DepartmentMembershipForm
from apps.accounts.models import Department

User = get_user_model()


def _make_user(username, *, groups=None, is_active=True):
    u = User.objects.create_user(
        username=username,
        email=f"{username}@example.com",
        password="pw-1234!",
        is_active=is_active,
    )
    if groups:
        u.groups.set(Group.objects.filter(name__in=groups))
    return u


@pytest.fixture
def roles(db):
    for n in [
        "System Administrator",
        "Management Administrator",
        "Meeting Chairperson",
        "Minutes Secretary",
        "Department Contributor",
        "Viewer",
    ]:
        Group.objects.get_or_create(name=n)


@pytest.mark.django_db
def test_contributor_forbidden_user_list(client, roles):
    contrib = _make_user("c", groups=["Department Contributor"])
    client.force_login(contrib)
    resp = client.get(reverse("accounts:user_list"))
    assert resp.status_code == 403


@pytest.mark.django_db
def test_viewer_forbidden_user_list(client, roles):
    viewer = _make_user("v", groups=["Viewer"])
    client.force_login(viewer)
    resp = client.get(reverse("accounts:user_list"))
    assert resp.status_code == 403


@pytest.mark.django_db
def test_viewer_forbidden_user_edit(client, roles):
    viewer = _make_user("v", groups=["Viewer"])
    target = _make_user("t", groups=["Viewer"])
    client.force_login(viewer)
    resp = client.get(reverse("accounts:user_edit", args=[target.pk]))
    assert resp.status_code == 403


@pytest.mark.django_db
def test_contributor_forbidden_user_edit(client, roles):
    contrib = _make_user("c", groups=["Department Contributor"])
    target = _make_user("t", groups=["Viewer"])
    client.force_login(contrib)
    resp = client.get(reverse("accounts:user_edit", args=[target.pk]))
    assert resp.status_code == 403


@pytest.mark.django_db
def test_contributor_forbidden_assignments(client, roles):
    contrib = _make_user("c", groups=["Department Contributor"])
    target = _make_user("t", groups=["Viewer"])
    client.force_login(contrib)
    resp = client.get(reverse("accounts:department_assignments", args=[target.pk]))
    assert resp.status_code == 403


@pytest.mark.django_db
def test_management_admin_allowed_user_list(client, roles):
    mgmt = _make_user("m", groups=["Management Administrator"])
    client.force_login(mgmt)
    resp = client.get(reverse("accounts:user_list"))
    assert resp.status_code == 200


@pytest.mark.django_db
def test_contributor_can_view_own_profile(client, roles):
    contrib = _make_user("c", groups=["Department Contributor"])
    client.force_login(contrib)
    resp = client.get(reverse("accounts:profile_me"))
    assert resp.status_code == 200


@pytest.mark.django_db
def test_inactive_user_blocked_on_assignment_form():
    Group.objects.get_or_create(name="Viewer")
    inactive = _make_user("inactive", groups=["Viewer"], is_active=False)
    dept = Department.objects.create(name="Sales", code="SAL")
    form = DepartmentMembershipForm(
        for_user=inactive,
        data={
            "department": dept.pk,
            "position": "",
            "is_primary": False,
            "is_contributor": False,
            "is_active": True,
            "date_joined": "",
            "notes": "",
        },
    )
    assert form.is_valid() is False
    assert any("inactive user" in msg for msg in form.errors.get("__all__", []))


@pytest.mark.django_db
def test_inactive_user_assignment_can_stay_inactive():
    Group.objects.get_or_create(name="Viewer")
    inactive = _make_user("inactive2", groups=["Viewer"], is_active=False)
    dept = Department.objects.create(name="R&D", code="RND")
    form = DepartmentMembershipForm(
        for_user=inactive,
        data={
            "department": dept.pk,
            "position": "",
            "is_primary": False,
            "is_contributor": False,
            "is_active": False,
            "date_joined": "",
            "notes": "",
        },
    )
    assert form.is_valid() is True, form.errors


@pytest.mark.django_db
def test_reactivate_assignment_after_user_reactivated():
    Group.objects.get_or_create(name="Viewer")
    u = _make_user("floater", groups=["Viewer"], is_active=False)
    dept = Department.objects.create(name="HR", code="HR")
    form_off = DepartmentMembershipForm(
        for_user=u,
        data={
            "department": dept.pk,
            "position": "",
            "is_primary": True,
            "is_contributor": False,
            "is_active": False,
            "date_joined": "",
            "notes": "",
        },
    )
    assert form_off.is_valid() is True

    u.is_active = True
    u.save()

    form_on = DepartmentMembershipForm(
        for_user=u,
        data={
            "department": dept.pk,
            "position": "",
            "is_primary": True,
            "is_contributor": False,
            "is_active": True,
            "date_joined": "",
            "notes": "",
        },
    )
    assert form_on.is_valid() is True, form_on.errors


@pytest.mark.django_db
def test_anonymous_redirected_not_403(client, roles):
    resp = client.get(reverse("accounts:user_list"))
    assert resp.status_code == 302
    assert "/login/" in resp["Location"]
