import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.urls import reverse

from apps.accounts.models import Department, DepartmentMembership, Position

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
def test_sidebar_sysadmin_renders_departments_link(client, roles, seed_org):
    admin = _make_user("sysadmin_sb1", groups=["System Administrator"])
    client.force_login(admin)
    resp = client.get(reverse("home"))
    assert resp.status_code == 200
    assert reverse("accounts:department_list") in resp.content.decode()


@pytest.mark.django_db
def test_sidebar_contains_positions_link(client, roles, seed_org):
    admin = _make_user("sysadmin_sb2", groups=["System Administrator"])
    client.force_login(admin)
    resp = client.get(reverse("home"))
    assert resp.status_code == 200
    content = resp.content.decode()
    assert reverse("accounts:position_list") in content
    assert 'href="' + reverse("accounts:position_list") + '"' in content


@pytest.mark.django_db
def test_sidebar_contains_teams_link(client, roles, seed_org):
    admin = _make_user("sysadmin_sb3", groups=["System Administrator"])
    client.force_login(admin)
    resp = client.get(reverse("home"))
    assert resp.status_code == 200
    content = resp.content.decode()
    assert reverse("accounts:team_list") in content
    assert 'href="' + reverse("accounts:team_list") + '"' in content


@pytest.mark.django_db
def test_offcanvas_contains_departments_link(client, roles, seed_org):
    admin = _make_user("sysadmin_off", groups=["System Administrator"])
    client.force_login(admin)
    resp = client.get(reverse("home"))
    assert resp.status_code == 200
    content = resp.content.decode()
    dept_url = reverse("accounts:department_list")
    assert dept_url in content


@pytest.mark.django_db
def test_viewer_departments_list_pagination_25(client, roles, seed_org):
    viewer = _make_user("viewer_pag", groups=["Viewer"])
    client.force_login(viewer)
    for i in range(1, 27):
        Department.objects.create(
            name=f"Extra Department {i}",
            code=f"EXD{i}",
            description=f"Test dept {i}",
            is_active=True,
        )
    resp = client.get(reverse("accounts:department_list"))
    assert resp.status_code == 200
    content = resp.content.decode()
    assert "Page 1 of 2" in content or "page=2" in content
    resp2 = client.get(reverse("accounts:department_list") + "?page=2")
    assert resp2.status_code == 200


@pytest.mark.django_db
def test_positions_list_sorted_level_asc(client, roles, seed_org):
    viewer = _make_user("viewer_sort", groups=["Viewer"])
    client.force_login(viewer)
    resp = client.get(reverse("accounts:position_list"))
    assert resp.status_code == 200
    content = resp.content.decode()
    pres_idx = content.find("President")
    gm_idx = content.find("General Manager")
    avp_idx = content.find("AVP")
    assert pres_idx != -1
    assert gm_idx != -1
    assert avp_idx != -1
    assert pres_idx < gm_idx < avp_idx


@pytest.mark.django_db
def test_department_detail_contains_members_table(client, roles, seed_org):
    viewer = _make_user("viewer_dm", groups=["Viewer"])
    user_x = _make_user("user_x_dept", groups=["Viewer"], display_name="User X")
    client.force_login(viewer)
    eng = Department.objects.get(code="ENG")
    DepartmentMembership.objects.create(
        user=user_x,
        department=eng,
        is_primary=True,
        is_active=True,
    )
    resp = client.get(reverse("accounts:department_detail", kwargs={"pk": str(eng.pk)}))
    assert resp.status_code == 200
    content = resp.content.decode()
    assert "User X" in content or "user_x_dept" in content


@pytest.mark.django_db
def test_position_detail_contains_incumbents_table(client, roles, seed_org):
    viewer = _make_user("viewer_pm", groups=["Viewer"])
    user_x = _make_user("user_x_pos", groups=["Viewer"], display_name="User X")
    client.force_login(viewer)
    pres = Position.objects.get(code="PRES")
    exec_dept = Department.objects.get(code="EXEC")
    DepartmentMembership.objects.create(
        user=user_x,
        department=exec_dept,
        position=pres,
        is_primary=True,
        is_active=True,
    )
    resp = client.get(reverse("accounts:position_detail", kwargs={"pk": str(pres.pk)}))
    assert resp.status_code == 200
    content = resp.content.decode()
    assert "User X" in content or "user_x_pos" in content


@pytest.mark.django_db
def test_org_teams_page_contains_teama_and_teamb(client, roles, seed_org):
    viewer = _make_user("viewer_teams", groups=["Viewer"])
    client.force_login(viewer)
    resp = client.get(reverse("accounts:team_list"))
    assert resp.status_code == 200
    content = resp.content.decode()
    assert "Team A" in content
    assert "Team B" in content


@pytest.mark.django_db
def test_org_teams_page_links_sales_teams(client, roles, seed_org):
    viewer = _make_user("viewer_sales_links", groups=["Viewer"])
    client.force_login(viewer)
    resp = client.get(reverse("accounts:team_list"))
    assert resp.status_code == 200
    content = resp.content.decode()
    assert reverse("sales_updates:team_list") in content
