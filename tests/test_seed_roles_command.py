import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.core.management import call_command

from apps.accounts.models import DepartmentMembership

User = get_user_model()


@pytest.mark.django_db
def test_seed_roles_creates_six_groups_first_run(capsys):
    Group.objects.all().delete()
    call_command("seed_roles")
    captured = capsys.readouterr()
    assert Group.objects.count() == 6
    for name in [
        "System Administrator",
        "Management Administrator",
        "Meeting Chairperson",
        "Minutes Secretary",
        "Department Contributor",
        "Viewer",
    ]:
        assert Group.objects.filter(name=name).exists()
        assert f"Created group: {name}" in captured.out


@pytest.mark.django_db
def test_seed_roles_idempotent(capsys):
    Group.objects.all().delete()
    call_command("seed_roles")
    capsys.readouterr()  # discard first run output
    after_first = Group.objects.count()
    assert after_first == 6

    call_command("seed_roles")
    captured = capsys.readouterr()
    after_second = Group.objects.count()
    assert after_second == after_first
    assert "Created group:" not in captured.out  # second run no new groups


@pytest.mark.django_db
def test_seed_roles_reset_perms_flag(capsys):
    Group.objects.all().delete()
    call_command("seed_roles")
    mgmt = Group.objects.get(name="Management Administrator")
    original_count = mgmt.permissions.count()
    assert original_count > 0

    one_perm = mgmt.permissions.first()
    mgmt.permissions.remove(one_perm)
    mgmt.save()
    assert mgmt.permissions.count() == original_count - 1

    call_command("seed_roles")
    mgmt.refresh_from_db()
    assert mgmt.permissions.count() == original_count

    call_command("seed_roles", "--reset-perms")
    captured = capsys.readouterr()
    mgmt.refresh_from_db()
    assert mgmt.permissions.count() == original_count
    assert "+ Ensured" in captured.out


@pytest.mark.django_db
def test_management_admin_has_department_membership_edit():
    call_command("seed_roles")
    mgmt = Group.objects.get(name="Management Administrator")
    ct = ContentType.objects.get_for_model(DepartmentMembership)
    view_perm = Permission.objects.get(content_type=ct, codename="view_departmentmembership")
    change_perm = Permission.objects.get(content_type=ct, codename="change_departmentmembership")
    add_perm = Permission.objects.get(content_type=ct, codename="add_departmentmembership")
    assert view_perm in mgmt.permissions.all()
    assert change_perm in mgmt.permissions.all()
    assert add_perm in mgmt.permissions.all()


@pytest.mark.django_db
def test_viewer_has_only_view_perms():
    call_command("seed_roles")
    viewer = Group.objects.get(name="Viewer")
    for p in viewer.permissions.select_related("content_type"):
        assert p.codename.startswith("view_"), f"Viewer has non-view perm: {p.codename}"


@pytest.mark.django_db
def test_system_admin_has_user_add_permission():
    call_command("seed_roles")
    sa = Group.objects.get(name="System Administrator")
    ct = ContentType.objects.get_for_model(User)
    add = Permission.objects.get(content_type=ct, codename="add_user")
    assert add in sa.permissions.all()
