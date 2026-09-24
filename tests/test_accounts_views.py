import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.urls import reverse

from apps.accounts.models import Department, DepartmentMembership
from apps.audit.models import AuditLog

User = get_user_model()


def _make_user(username, *, groups=None, is_active=True, is_staff=False, **extra):
    email = extra.pop("email", None) or f"{username}@example.com"
    u = User.objects.create_user(
        username=username,
        email=email,
        password="pw-1234!",
        is_active=is_active,
        is_staff=is_staff,
        **extra,
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
    return Group.objects.all()


@pytest.mark.django_db
def test_user_list_search_and_filter(client, roles):
    mgmt = _make_user("mgmt", groups=["Management Administrator"])
    _make_user("alpha", groups=["Viewer"])
    _make_user("beta", groups=["Viewer"], is_active=False)
    client.force_login(mgmt)

    resp = client.get(reverse("accounts:user_list"))
    assert resp.status_code == 200
    assert b"alpha" in resp.content and b"beta" in resp.content

    resp = client.get(reverse("accounts:user_list") + "?q=alpha")
    assert resp.status_code == 200
    assert b"alpha" in resp.content
    assert b"beta" not in resp.content

    resp = client.get(reverse("accounts:user_list") + "?status=inactive")
    assert resp.status_code == 200
    assert b"beta" in resp.content
    assert b"alpha" not in resp.content


@pytest.mark.django_db(transaction=True)
def test_user_create_view_creates_user_and_audit(client, roles):
    mgmt = _make_user("mgmt2", groups=["Management Administrator"])
    client.force_login(mgmt)
    group_pks = list(
        Group.objects.filter(name__in=["Viewer", "Department Contributor"]).values_list(
            "pk", flat=True
        )
    )
    data = {
        "username": "newuser",
        "email": "new@example.com",
        "first_name": "New",
        "last_name": "User",
        "password1": "V3ryStr0ng!-Pass",
        "password2": "V3ryStr0ng!-Pass",
        "groups": group_pks,
        "theme": "auto",
        "is_active": "on",
    }
    resp = client.post(reverse("accounts:user_create"), data, follow=False)
    assert resp.status_code in (302, 200), resp.status_code
    created = User.objects.filter(username="newuser").first()
    assert created is not None, (
        f"errors: {resp.context.get('form').errors if hasattr(resp, 'context') and resp.context else ''}"
    )
    assert set(created.groups.values_list("name", flat=True)) == {
        "Viewer",
        "Department Contributor",
    }
    assert AuditLog.objects.filter(action=AuditLog.ACTION_CREATE, target_user=created).exists()


@pytest.mark.django_db(transaction=True)
def test_user_update_view_writes_diff_audit(client, roles):
    mgmt = _make_user("mgmt3", groups=["Management Administrator"])
    target = _make_user("target", groups=["Viewer"], first_name="Old", last_name="A")
    client.force_login(mgmt)
    group_pks = list(
        Group.objects.filter(name="Management Administrator").values_list("pk", flat=True)
    )
    resp = client.post(
        reverse("accounts:user_edit", args=[target.pk]),
        {
            "username": "target",
            "email": "target@example.com",
            "first_name": "New",
            "last_name": "A",
            "is_active": "on",
            "groups": group_pks,
            "theme": "light",
        },
    )
    assert resp.status_code in (302, 200), resp.status_code
    target.refresh_from_db()
    assert target.first_name == "New"
    update_log = AuditLog.objects.filter(action=AuditLog.ACTION_UPDATE, target_user=target).first()
    assert update_log is not None
    assert update_log.changes.get("first_name", {}).get("old") == "Old"
    assert update_log.changes.get("first_name", {}).get("new") == "New"


@pytest.mark.django_db
def test_profile_me_renders(client, roles):
    contrib = _make_user("c3", groups=["Department Contributor"])
    client.force_login(contrib)
    resp = client.get(reverse("accounts:profile_me"))
    assert resp.status_code == 200
    assert b"c3@example.com" in resp.content


@pytest.mark.django_db
def test_profile_other_pk_200(client, roles):
    mgmt = _make_user("m4", groups=["Management Administrator"])
    target = _make_user("t4", groups=["Viewer"])
    client.force_login(mgmt)
    resp = client.get(reverse("accounts:profile_detail", args=[target.pk]))
    assert resp.status_code == 200


@pytest.mark.django_db
def test_profile_edit_self(client, roles):
    user = _make_user("p", groups=["Viewer"], display_name="Before")
    client.force_login(user)
    resp = client.post(
        reverse("accounts:profile_edit"),
        {
            "display_name": "After",
            "first_name": user.first_name or "",
            "last_name": user.last_name or "",
            "initials": "",
            "phone": "",
            "signature_text": "",
            "theme": "auto",
            "bio": "Hi",
        },
    )
    assert resp.status_code == 302, resp.status_code
    user.refresh_from_db()
    assert user.display_name == "After"


@pytest.mark.django_db(transaction=True)
def test_department_assignments_view(client, roles):
    mgmt = _make_user("m5", groups=["Management Administrator"])
    target = _make_user("t5", groups=["Viewer"])
    sales = Department.objects.create(name="Sales", code="SALES")
    client.force_login(mgmt)

    resp = client.get(reverse("accounts:department_assignments", args=[target.pk]))
    assert resp.status_code == 200

    formset_prefix = "department_memberships"
    data = {
        f"{formset_prefix}-TOTAL_FORMS": "1",
        f"{formset_prefix}-INITIAL_FORMS": "0",
        f"{formset_prefix}-MIN_NUM_FORMS": "0",
        f"{formset_prefix}-MAX_NUM_FORMS": "1000",
        f"{formset_prefix}-0-department": sales.pk,
        f"{formset_prefix}-0-position": "",
        f"{formset_prefix}-0-is_primary": "on",
        f"{formset_prefix}-0-is_contributor": "on",
        f"{formset_prefix}-0-is_active": "on",
        f"{formset_prefix}-0-date_joined": "",
        f"{formset_prefix}-0-notes": "",
        f"{formset_prefix}-0-id": "",
        f"{formset_prefix}-0-user": "",
        f"{formset_prefix}-0-DELETE": "",
    }
    resp = client.post(
        reverse("accounts:department_assignments", args=[target.pk]),
        data,
        follow=False,
    )
    assert resp.status_code in (302, 200), (
        resp.status_code,
        resp.context.get("formset").errors if hasattr(resp, "context") and resp.context else "",
    )
    mship = DepartmentMembership.objects.filter(user=target, department=sales).first()
    assert mship is not None
    assert mship.is_primary is True
    assert mship.is_contributor is True
    assert AuditLog.objects.filter(action=AuditLog.ACTION_ASSIGN, target_user=target).exists()


@pytest.mark.django_db
def test_password_change_flow(client, roles):
    user = _make_user("pwuser", groups=["Viewer"])
    client.force_login(user)
    resp = client.get(reverse("accounts:password_change"))
    assert resp.status_code == 200
    resp = client.post(
        reverse("accounts:password_change"),
        {
            "old_password": "pw-1234!",
            "new_password1": "N3wP@ss-Strong!",
            "new_password2": "N3wP@ss-Strong!",
        },
    )
    assert resp.status_code == 302, (
        resp.status_code,
        resp.context.get("form").errors if hasattr(resp, "context") and resp.context else "",
    )
    assert resp.url == reverse("accounts:password_change_done")
    resp2 = client.get(reverse("accounts:password_change_done"))
    assert resp2.status_code == 200
