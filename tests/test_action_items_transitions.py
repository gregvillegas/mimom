from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Department, DepartmentMembership, User
from apps.action_items.models import (
    STATUS_BLOCKED,
    STATUS_CANCELLED,
    STATUS_COMPLETED,
    STATUS_IN_PROGRESS,
    STATUS_OPEN,
    STATUS_REOPENED,
    STATUS_UNDER_REVIEW,
    ActionItem,
)
from apps.action_items.services import (
    transition_actionitem,
)
from apps.audit.models import AuditLog


@pytest.fixture
def dept(db):
    return Department.objects.create(name="IT", code="IT")


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
def mgmt_admin(make_user, dept):
    u = make_user("m_a", groups=["Management Administrator"])
    DepartmentMembership.objects.create(
        user=u, department=dept, is_active=True, is_contributor=True
    )
    return u


@pytest.fixture
def sys_admin(make_user):
    return make_user("sys_a", groups=["System Administrator"], is_staff=True)


@pytest.fixture
def action_item(dept, make_user):
    owner = make_user("ai_owner")
    DepartmentMembership.objects.create(
        user=owner, department=dept, is_active=True, is_contributor=True
    )
    today = timezone.now().date()
    item = ActionItem.objects.create(
        title="Transition item",
        department=dept,
        created_by=owner,
        last_modified_by=owner,
        owner=owner,
        status=STATUS_OPEN,
        due_date=today + timedelta(days=5),
    )
    return item


ALL_STATUSES = [
    STATUS_OPEN,
    STATUS_IN_PROGRESS,
    STATUS_BLOCKED,
    STATUS_UNDER_REVIEW,
    STATUS_COMPLETED,
    STATUS_CANCELLED,
    STATUS_REOPENED,
]


@pytest.mark.django_db(transaction=True)
class TestTransitionGraph:
    def test_open_to_progress(self, action_item, sys_admin):
        h = transition_actionitem(action_item, STATUS_IN_PROGRESS, by_user=sys_admin)
        action_item.refresh_from_db()
        assert action_item.status == STATUS_IN_PROGRESS
        assert action_item.progress_pct >= 10
        assert h.from_status == STATUS_OPEN
        assert h.to_status == STATUS_IN_PROGRESS
        assert action_item.status_history.exists()

    def test_progress_to_complete_sets_progress_100(self, action_item, sys_admin):
        transition_actionitem(action_item, STATUS_IN_PROGRESS, by_user=sys_admin)
        transition_actionitem(action_item, STATUS_UNDER_REVIEW, by_user=sys_admin)
        action_item.refresh_from_db()
        transition_actionitem(action_item, STATUS_COMPLETED, by_user=sys_admin)
        action_item.refresh_from_db()
        assert action_item.status == STATUS_COMPLETED
        assert action_item.progress_pct == 100
        assert action_item.completed_at is not None

    def test_same_status_raises(self, action_item, sys_admin):
        with pytest.raises(ValidationError):
            transition_actionitem(action_item, STATUS_OPEN, by_user=sys_admin)

    def test_invalid_status_rejected(self, action_item, sys_admin):
        action_item.status = STATUS_OPEN
        with pytest.raises(ValidationError):
            transition_actionitem(action_item, STATUS_REOPENED, by_user=sys_admin)

    def test_completed_with_blockers_rejected(self, action_item, sys_admin):
        action_item.blockers = "waiting on legal review"
        action_item.save()
        transition_actionitem(action_item, STATUS_IN_PROGRESS, by_user=sys_admin)
        transition_actionitem(action_item, STATUS_UNDER_REVIEW, by_user=sys_admin)
        action_item.refresh_from_db()
        with pytest.raises(ValidationError):
            transition_actionitem(action_item, STATUS_COMPLETED, by_user=sys_admin)
        action_item.blockers = ""
        action_item.save()
        action_item.status = STATUS_UNDER_REVIEW
        action_item.save()
        transition_actionitem(action_item, STATUS_COMPLETED, by_user=sys_admin)
        action_item.refresh_from_db()
        assert action_item.status == STATUS_COMPLETED

    def test_reopen_requires_reason(self, action_item, sys_admin):
        transition_actionitem(action_item, STATUS_IN_PROGRESS, by_user=sys_admin)
        transition_actionitem(action_item, STATUS_UNDER_REVIEW, by_user=sys_admin)
        action_item.refresh_from_db()
        transition_actionitem(action_item, STATUS_COMPLETED, by_user=sys_admin)
        action_item.refresh_from_db()
        with pytest.raises(ValidationError):
            transition_actionitem(action_item, STATUS_REOPENED, by_user=sys_admin, reason="")
        h = transition_actionitem(
            action_item, STATUS_REOPENED, by_user=sys_admin, reason="bad quality"
        )
        action_item.refresh_from_db()
        assert action_item.status == STATUS_REOPENED
        assert action_item.reopened_count == 1
        assert h.reason == "bad quality"

    def test_reopen_role_locked_without_admin(self, action_item, make_user):
        non_admin = make_user("chump")
        transition_actionitem(
            action_item, STATUS_IN_PROGRESS, by_user=action_item.created_by, skip_role_check=True
        )
        transition_actionitem(
            action_item, STATUS_UNDER_REVIEW, by_user=action_item.created_by, skip_role_check=True
        )
        action_item.refresh_from_db()
        transition_actionitem(
            action_item, STATUS_COMPLETED, by_user=action_item.created_by, skip_role_check=True
        )
        action_item.refresh_from_db()
        with pytest.raises(ValidationError):
            transition_actionitem(action_item, STATUS_REOPENED, by_user=non_admin, reason="x")

    def test_transition_logs_audit(self, action_item, sys_admin):
        transition_actionitem(action_item, STATUS_IN_PROGRESS, by_user=sys_admin)
        log = AuditLog.objects.filter(
            record_type="action_items.actionitem", action="TRANSITION"
        ).first()
        assert log is not None
        assert log.action == AuditLog.ACTION_TRANSITION

    def test_complete_specific_audit_action(self, action_item, sys_admin):
        transition_actionitem(action_item, STATUS_IN_PROGRESS, by_user=sys_admin)
        transition_actionitem(action_item, STATUS_UNDER_REVIEW, by_user=sys_admin)
        action_item.refresh_from_db()
        action_item.blockers = ""
        action_item.save()
        transition_actionitem(action_item, STATUS_COMPLETED, by_user=sys_admin)
        log = AuditLog.objects.filter(
            record_type="action_items.actionitem", action="COMPLETE"
        ).first()
        assert log is not None

    def test_cancel_from_under_review_requires_reason(self, action_item, sys_admin):
        transition_actionitem(action_item, STATUS_IN_PROGRESS, by_user=sys_admin)
        transition_actionitem(action_item, STATUS_UNDER_REVIEW, by_user=sys_admin)
        action_item.refresh_from_db()
        with pytest.raises(ValidationError):
            transition_actionitem(action_item, STATUS_CANCELLED, by_user=sys_admin, reason="")
        transition_actionitem(action_item, STATUS_CANCELLED, by_user=sys_admin, reason="abandoned")
        action_item.refresh_from_db()
        assert action_item.status == STATUS_CANCELLED

    def test_progress_to_blocked_preserves_progress(self, action_item, sys_admin):
        transition_actionitem(action_item, STATUS_IN_PROGRESS, by_user=sys_admin)
        action_item.refresh_from_db()
        action_item.progress_pct = 60
        action_item.save()
        transition_actionitem(
            action_item, STATUS_BLOCKED, by_user=sys_admin, reason="waiting on vendor"
        )
        action_item.refresh_from_db()
        assert action_item.status == STATUS_BLOCKED
        assert action_item.progress_pct == 60

    def test_in_progress_min_10_progress(self, action_item, sys_admin):
        assert action_item.progress_pct == 0
        transition_actionitem(action_item, STATUS_IN_PROGRESS, by_user=sys_admin)
        action_item.refresh_from_db()
        assert action_item.progress_pct >= 10

    def test_status_history_written_once(self, action_item, sys_admin):
        from apps.action_items.models import ActionItemStatusHistory

        before = ActionItemStatusHistory.objects.filter(action_item=action_item).count()
        transition_actionitem(action_item, STATUS_IN_PROGRESS, by_user=sys_admin)
        after = ActionItemStatusHistory.objects.filter(action_item=action_item).count()
        assert after - before == 1

    def test_audit_transition_action_logged(self, action_item, sys_admin):
        from apps.audit.models import AuditLog

        with transaction.atomic():
            transition_actionitem(action_item, STATUS_IN_PROGRESS, by_user=sys_admin)
        action_item.refresh_from_db()
        transition_actionitem(action_item, STATUS_COMPLETED, by_user=sys_admin)
        rows = AuditLog.objects.filter(
            record_type="action_items.actionitem", record_id=str(action_item.pk)
        ).values_list("action", flat=True)
        assert "COMPLETE" in list(rows)
