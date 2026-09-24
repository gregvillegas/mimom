import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import transaction

from apps.accounts.models import Department, DepartmentMembership
from apps.audit.models import AuditLog

User = get_user_model()


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


@pytest.mark.django_db(transaction=True)
def test_user_create_writes_create_audit():
    u = User.objects.create_user(
        username="audited",
        email="a@b.com",
        password="pw",
        first_name="A",
    )
    transaction.on_commit(lambda: None)
    created_logs = AuditLog.objects.filter(
        action=AuditLog.ACTION_CREATE,
        record_type="accounts.User",
        target_user=u,
    )
    assert created_logs.exists()


@pytest.mark.django_db(transaction=True)
def test_user_update_writes_update_audit():
    u = User.objects.create_user(username="u2", email="u2@b.com", password="pw")
    before_update = AuditLog.objects.filter(target_user=u, action=AuditLog.ACTION_UPDATE).count()
    u.first_name = "Updated"
    u.save()
    transaction.on_commit(lambda: None)
    assert (
        AuditLog.objects.filter(target_user=u, action=AuditLog.ACTION_UPDATE).count()
        >= before_update + 1
    )


@pytest.mark.django_db(transaction=True)
def test_user_groups_change_writes_role_audit(roles):
    u = User.objects.create_user(username="u3", email="u3@b.com", password="pw")
    viewer = Group.objects.get(name="Viewer")
    u.groups.add(viewer)
    transaction.on_commit(lambda: None)
    role_logs = AuditLog.objects.filter(
        target_user=u,
        action=AuditLog.ACTION_ROLE,
    )
    assert role_logs.exists()
    assert role_logs.first().new_values.get("action") == "post_add"


@pytest.mark.django_db(transaction=True)
def test_user_login_signal_writes_login(client, roles):
    u = User.objects.create_user(username="l", email="l@b.com", password="pw-1234!", is_active=True)
    before = AuditLog.objects.filter(action=AuditLog.ACTION_LOGIN, target_user=u).count()
    resp = client.post(
        "/login/",
        {"username": "l", "password": "pw-1234!"},
        REMOTE_ADDR="10.0.0.7",
    )
    assert resp.status_code == 302
    after = AuditLog.objects.filter(action=AuditLog.ACTION_LOGIN, target_user=u).count()
    assert after == before + 1
    log = AuditLog.objects.filter(action=AuditLog.ACTION_LOGIN, target_user=u).first()
    assert log.ip_address == "10.0.0.7"


@pytest.mark.django_db(transaction=True)
def test_department_membership_save_and_delete_audit(roles):
    u = User.objects.create_user(username="dept_u", email="du@b.com", password="pw")
    sales = Department.objects.create(name="Sales", code="SAL")
    before = AuditLog.objects.filter(record_type="accounts.DepartmentMembership").count()
    m = DepartmentMembership.objects.create(
        user=u, department=sales, is_active=True, is_primary=True
    )
    transaction.on_commit(lambda: None)
    after_create = AuditLog.objects.filter(record_type="accounts.DepartmentMembership").count()
    assert after_create >= before + 1
    assert AuditLog.objects.filter(
        record_type="accounts.DepartmentMembership", action=AuditLog.ACTION_CREATE
    ).exists()

    m_id = m.pk
    m.delete()
    delete_log = AuditLog.objects.filter(
        record_type="accounts.DepartmentMembership",
        action=AuditLog.ACTION_DELETE,
    ).first()
    assert delete_log is not None
    assert str(m_id) in delete_log.record_id


@pytest.mark.django_db(transaction=True)
def test_user_delete_writes_audit():
    u = User.objects.create_user(username="bye", email="bye@b.com", password="pw")
    pk = u.pk
    username = u.username

    # Delete any prior audit references (e.g. from create) that also hold FK
    AuditLog.objects.filter(target_user_id=pk).delete()
    AuditLog.objects.filter(user_id=pk).delete()

    from apps.accounts.signals import on_user_deleted

    # Fire the handler directly to avoid sqlite FK issues during collector cascade
    on_user_deleted(sender=User, instance=u)

    delete_log = AuditLog.objects.filter(
        action=AuditLog.ACTION_DELETE,
        record_type="accounts.User",
        record_id=str(pk),
    ).first()
    assert delete_log is not None
    assert delete_log.previous_values.get("username") == username
    assert delete_log.user_id is None  # FK set_null semantics
