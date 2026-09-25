import pytest
from django.core.management import call_command
from django.db import IntegrityError

from apps.accounts.models import Department, Position
from apps.sales_updates.models import SalesGroup, SalesTeam


@pytest.mark.django_db
def test_seed_departments_plus_executive_total_7():
    call_command("seed_hierarchy")
    count = Department.objects.filter(
        code__in=["EXEC", "ENG", "SALES", "MKT", "ACC", "PUR", "WH"]
    ).count()
    assert count == 7


@pytest.mark.django_db
def test_seed_positions_13_names():
    call_command("seed_hierarchy")
    count = Position.objects.filter(
        code__in=[
            "PRES",
            "GM",
            "AVP",
            "SM",
            "SUPV",
            "TL",
            "AM",
            "ASUPV",
            "WSUPV",
            "PSUPV",
            "OPSM",
            "TM",
            "ASTM",
        ]
    ).count()
    assert count == 13
    assert Position.objects.get(code="PRES").level == 1
    assert Position.objects.get(code="GM").level == 2
    assert Position.objects.get(code="AVP").level == 3
    assert Position.objects.get(code="ASTM").level == 6


@pytest.mark.django_db
def test_seed_teams_a_b_exist():
    call_command("seed_hierarchy")
    assert SalesTeam.objects.filter(code="TEAMA").exists()
    assert SalesTeam.objects.filter(code="TEAMB").exists()


@pytest.mark.django_db
def test_seed_team_a_groups_CSG_A_B_C_D_I():
    call_command("seed_hierarchy")
    team_a = SalesTeam.objects.get(code="TEAMA")
    codes = {g.code for g in team_a.groups.all()}
    assert codes == {"CSG-A", "CSG-B", "CSG-C", "CSG-D", "CSG-I"}


@pytest.mark.django_db
def test_seed_team_b_groups_E_F_G_H():
    call_command("seed_hierarchy")
    team_b = SalesTeam.objects.get(code="TEAMB")
    codes = {g.code for g in team_b.groups.all()}
    assert codes == {"CSG-E", "CSG-F", "CSG-G", "CSG-H"}


@pytest.mark.django_db
def test_seed_idempotent():
    call_command("seed_hierarchy")
    dept_count = Department.objects.count()
    pos_count = Position.objects.count()
    team_count = SalesTeam.objects.count()
    group_count = SalesGroup.objects.count()
    call_command("seed_hierarchy")
    assert Department.objects.count() == dept_count
    assert Position.objects.count() == pos_count
    assert SalesTeam.objects.count() == team_count
    assert SalesGroup.objects.count() == group_count


@pytest.mark.django_db
def test_department_executive_head_set_null_then_back():
    call_command("seed_hierarchy")
    from django.contrib.auth import get_user_model

    User = get_user_model()
    exec_dept = Department.objects.get(code="EXEC")
    exec_dept.head = None
    exec_dept.full_clean()
    exec_dept.save()
    exec_dept.refresh_from_db()
    assert exec_dept.head is None
    user = User.objects.create_user(
        username="exec_user", email="exec@example.com", password="pw-1234!"
    )
    exec_dept.head = user
    exec_dept.full_clean()
    exec_dept.save()
    exec_dept.refresh_from_db()
    assert exec_dept.head == user


@pytest.mark.django_db
def test_position_president_uniqueness_by_code():
    call_command("seed_hierarchy")
    pres = Position.objects.get(code="PRES")
    obj, created = Position.objects.update_or_create(
        code="PRES",
        defaults={"name": "President", "level": 1},
    )
    assert not created
    assert obj.pk == pres.pk


@pytest.mark.django_db
def test_sales_groups_unique_together_code():
    call_command("seed_hierarchy")
    team_a = SalesTeam.objects.get(code="TEAMA")
    with pytest.raises(IntegrityError):
        SalesGroup.objects.create(code="CSG-A", team=team_a, name="Duplicate")


@pytest.mark.django_db
def test_delete_extra_groups_flag():
    call_command("seed_hierarchy")
    team_a = SalesTeam.objects.get(code="TEAMA")
    SalesGroup.objects.create(code="CSG-Z", team=team_a, name="Z")
    assert SalesGroup.objects.filter(code="CSG-Z").exists()
    call_command("seed_hierarchy", "--delete-extra")
    assert not SalesGroup.objects.filter(code="CSG-Z").exists()
