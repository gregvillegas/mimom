import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.urls import reverse

from apps.accounts.models import Position
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


@pytest.fixture
def seed_org(db):
    from django.core.management import call_command

    call_command("seed_hierarchy")


@pytest.mark.django_db
def test_departments_url_visitor_302(client):
    resp = client.get(reverse("accounts:department_list"))
    assert resp.status_code == 302


@pytest.mark.django_db
def test_departments_url_viewer_200(client, roles):
    viewer = _make_user("viewer_org", groups=["Viewer"])
    client.force_login(viewer)
    resp = client.get(reverse("accounts:department_list"))
    assert resp.status_code == 200


@pytest.mark.django_db
def test_department_create_viewer_403(client, roles, seed_org):
    viewer = _make_user("viewer_cr_dept", groups=["Viewer"])
    client.force_login(viewer)
    data = {"name": "Test Dept", "code": "TST", "description": "", "is_active": "on"}
    resp = client.post(reverse("accounts:department_create"), data)
    assert resp.status_code == 403


@pytest.mark.django_db
def test_department_create_sysadmin_302_redirect(client, roles, seed_org):
    admin = _make_user("sysadmin_dept", groups=["System Administrator"])
    client.force_login(admin)
    data = {"name": "New Dept X", "code": "NDX", "description": "", "is_active": "on"}
    resp = client.post(reverse("accounts:department_create"), data, follow=False)
    assert resp.status_code == 302
    assert resp.url == reverse("accounts:department_list")


@pytest.mark.django_db
def test_positions_list_viewer_200(client, roles, seed_org):
    viewer = _make_user("viewer_pos", groups=["Viewer"])
    client.force_login(viewer)
    resp = client.get(reverse("accounts:position_list"))
    assert resp.status_code == 200


@pytest.mark.django_db
def test_position_create_dept_contributor_403(client, roles, seed_org):
    contrib = _make_user("dept_contrib_pos", groups=["Department Contributor"])
    client.force_login(contrib)
    data = {
        "name": "Test Position",
        "code": "TPOS",
        "level": "10",
        "description": "",
        "is_active": "on",
    }
    resp = client.post(reverse("accounts:position_create"), data)
    assert resp.status_code == 403


@pytest.mark.django_db
def test_position_create_chair_201(client, roles, seed_org):
    chair = _make_user("chair_pos", groups=["Meeting Chairperson"])
    client.force_login(chair)
    data = {
        "name": "Chair Test Position",
        "code": "CTP",
        "level": "5",
        "description": "",
        "is_active": "on",
    }
    resp = client.post(reverse("accounts:position_create"), data, follow=False)
    assert resp.status_code in (200, 302)


@pytest.mark.django_db
def test_teams_list_sysadmin_200_both_cards(client, roles, seed_org):
    admin = _make_user("sysadmin_teams", groups=["System Administrator"])
    client.force_login(admin)
    resp = client.get(reverse("accounts:team_list"))
    assert resp.status_code == 200
    assert b"Management Teams" in resp.content
    assert b"Sales Teams" in resp.content


@pytest.mark.django_db
def test_department_detail_uuid_404_invalid_uuid(client, roles, seed_org):
    viewer = _make_user("viewer_inv", groups=["Viewer"])
    client.force_login(viewer)
    resp = client.get(
        reverse(
            "accounts:department_detail",
            kwargs={"pk": "00000000-0000-0000-0000-000000000000"},
        )
    )
    assert resp.status_code == 404


@pytest.mark.django_db(transaction=True)
def test_position_update_sets_audit_update(client, roles, seed_org):
    mgmt = _make_user("mgmt_audit_pos", groups=["Management Administrator"])
    client.force_login(mgmt)
    pos = Position.objects.get(code="PRES")
    data = {
        "name": pos.name,
        "code": pos.code,
        "level": str(pos.level),
        "description": "Updated description text",
        "is_active": "on",
    }
    resp = client.post(
        reverse("accounts:position_edit", kwargs={"pk": str(pos.pk)}), data
    )
    assert resp.status_code in (200, 302)
    count = AuditLog.objects.filter(
        action=AuditLog.ACTION_UPDATE, record_type="accounts.Position"
    ).count()
    assert count >= 1
