from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.accounts.models import Department, DepartmentMembership, User
from apps.action_items.models import (
    PRIORITY_HIGH,
    PRIORITY_LOW,
    PRIORITY_MEDIUM,
    PRIORITY_URGENT,
    STATUS_BLOCKED,
    STATUS_COMPLETED,
    STATUS_IN_PROGRESS,
    STATUS_OPEN,
    STATUS_REOPENED,
    STATUS_UNDER_REVIEW,
    ActionItem,
    ActionItemAssignee,
)
from apps.action_items.services import generate_action_reference


@pytest.fixture
def dept(db):
    return Department.objects.create(name="Engineering", code="ENG")


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
def owner(make_user, dept):
    user = make_user("owner_m", groups=["Department Contributor"])
    DepartmentMembership.objects.create(
        user=user, department=dept, is_active=True, is_contributor=True
    )
    return user


@pytest.fixture
def action_item(dept, owner):
    today = timezone.now().date()
    item = ActionItem.objects.create(
        title="Draft strategic roadmap",
        description="Deliver 3-year plan",
        department=dept,
        created_by=owner,
        last_modified_by=owner,
        owner=owner,
        priority=PRIORITY_MEDIUM,
        status=STATUS_OPEN,
        progress_pct=0,
        due_date=today + timedelta(days=7),
    )
    ActionItemAssignee.objects.get_or_create(
        action_item=item, user=owner, defaults={"is_primary": True, "is_supporting": False}
    )
    return item


@pytest.mark.django_db
class TestActionItemModel:
    def test_reference_generated(self, action_item):
        assert action_item.reference
        assert action_item.reference.startswith("ACT-")

    def test_manual_reference_not_overwritten(self, dept, owner):
        today = timezone.now().date()
        item = ActionItem.objects.create(
            title="Manual ref",
            department=dept,
            created_by=owner,
            owner=owner,
            status=STATUS_OPEN,
            due_date=today + timedelta(days=3),
            reference="CUSTOM-REF",
        )
        assert item.reference == "CUSTOM-REF"

    def test_invalid_progress(self, action_item):
        action_item.progress_pct = 150
        with pytest.raises(ValidationError):
            action_item.full_clean()

    def test_completed_requires_progress_100(self, action_item):
        action_item.status = STATUS_COMPLETED
        action_item.progress_pct = 90
        with pytest.raises(ValidationError):
            action_item.full_clean()
        action_item.progress_pct = 100
        action_item.blockers = ""
        action_item.full_clean()

    def test_editable_property(self, action_item):
        assert action_item.is_editable
        assert action_item.status == STATUS_OPEN
        today = timezone.now().date()
        assert not action_item.is_overdue
        action_item.due_date = today - timedelta(days=2)
        assert action_item.is_overdue
        assert action_item.overdue_age_days == 2

    def test_overdue_treated_as_active(self, action_item):
        action_item.due_date = timezone.now().date() - timedelta(days=3)
        action_item.save()
        qs = ActionItem.objects.filter(
            due_date__lt=timezone.now().date(),
            status__in=[
                STATUS_OPEN,
                STATUS_IN_PROGRESS,
                STATUS_BLOCKED,
                STATUS_UNDER_REVIEW,
                STATUS_REOPENED,
            ],
        )
        assert action_item in qs

    def test_ordering_by_priority(self, dept, owner):
        today = timezone.now().date()
        low = ActionItem.objects.create(
            title="L",
            department=dept,
            owner=owner,
            created_by=owner,
            status=STATUS_OPEN,
            priority=PRIORITY_LOW,
            due_date=today,
        )
        med = ActionItem.objects.create(
            title="M",
            department=dept,
            owner=owner,
            created_by=owner,
            status=STATUS_OPEN,
            priority=PRIORITY_MEDIUM,
            due_date=today,
        )
        high = ActionItem.objects.create(
            title="H",
            department=dept,
            owner=owner,
            created_by=owner,
            status=STATUS_OPEN,
            priority=PRIORITY_HIGH,
            due_date=today,
        )
        urg = ActionItem.objects.create(
            title="U",
            department=dept,
            owner=owner,
            created_by=owner,
            status=STATUS_OPEN,
            priority=PRIORITY_URGENT,
            due_date=today,
        )
        ordered = list(ActionItem.objects.filter(pk__in=[low.pk, med.pk, high.pk, urg.pk]))
        assert ordered[0].pk == urg.pk
        assert ordered[1].pk == high.pk
        assert ordered[2].pk == med.pk
        assert ordered[3].pk == low.pk

    def test_primary_assignee(self, action_item, owner):
        assert action_item.primary_assignee == owner
        ActionItemAssignee.objects.filter(action_item=action_item).delete()
        assert action_item.primary_assignee is None

    def test_assignee_defaults_to_supporting_when_unset(self, action_item, make_user):
        another = make_user("other")
        assign = ActionItemAssignee.objects.create(
            action_item=action_item, user=another, is_primary=False, is_supporting=False
        )
        assert assign.is_supporting is True

    def test_assignee_both_rejected(self, action_item, make_user):
        another = make_user("other2")
        with pytest.raises(ValidationError):
            bad = ActionItemAssignee(
                action_item=action_item, user=another, is_primary=True, is_supporting=True
            )
            bad.full_clean()


@pytest.mark.django_db
class TestGenerateReference:
    def test_generates_year_prefix(self, dept, owner):
        item = ActionItem(
            title="ref-t",
            department=dept,
            created_by=owner,
            owner=owner,
            status=STATUS_OPEN,
            due_date=timezone.now().date(),
        )
        ref = generate_action_reference(item)
        assert ref.startswith(f"ACT-{timezone.now().year}-")

    def test_increments(self, dept, owner, action_item):
        item2 = ActionItem.objects.create(
            title="inc t",
            department=dept,
            owner=owner,
            created_by=owner,
            status=STATUS_OPEN,
            due_date=timezone.now().date(),
        )
        assert item2.reference > action_item.reference


@pytest.mark.django_db
class TestProgressValidation:
    def test_progress_rejects_negative(self, action_item):
        action_item.progress_pct = -5
        with pytest.raises(ValidationError):
            action_item.full_clean()

    def test_progress_rejects_over_100(self, action_item):
        action_item.progress_pct = 120
        with pytest.raises(ValidationError):
            action_item.full_clean()

    def test_progress_zero_allowed(self, action_item):
        action_item.progress_pct = 0
        action_item.full_clean()

    def test_progress_100_allowed(self, action_item):
        action_item.status = STATUS_COMPLETED
        action_item.progress_pct = 100
        action_item.blockers = ""
        action_item.full_clean()

    def test_completed_requires_no_blockers(self, action_item):
        action_item.status = STATUS_COMPLETED
        action_item.progress_pct = 100
        action_item.blockers = "Needs QA approval"
        with pytest.raises(ValidationError):
            action_item.full_clean()
        action_item.blockers = ""
        action_item.full_clean()


@pytest.mark.django_db
class TestOverdueLogic:
    def test_due_today_not_overdue(self, action_item):
        action_item.due_date = timezone.now().date()
        action_item.save()
        assert not action_item.is_overdue
        assert action_item.overdue_age_days == 0

    def test_due_tomorrow_not_overdue(self, action_item):
        action_item.due_date = timezone.now().date() + timedelta(days=1)
        action_item.save()
        assert not action_item.is_overdue
        assert action_item.overdue_age_days == 0

    def test_overdue_age_10_days(self, action_item):
        action_item.due_date = timezone.now().date() - timedelta(days=10)
        action_item.save()
        assert action_item.is_overdue
        assert action_item.overdue_age_days == 10

    def test_completed_status_skips_overdue_flag(self, action_item):
        action_item.status = STATUS_COMPLETED
        action_item.progress_pct = 100
        action_item.blockers = ""
        action_item.due_date = timezone.now().date() - timedelta(days=5)
        action_item.save()
        assert action_item.is_overdue is False

    def test_overdue_queryset_service(self, dept, owner):
        from apps.action_items.services import overdue_action_items_queryset

        today = timezone.now().date()
        overdue = ActionItem.objects.create(
            title="OD one",
            department=dept,
            owner=owner,
            created_by=owner,
            status=STATUS_IN_PROGRESS,
            progress_pct=50,
            due_date=today - timedelta(days=2),
        )
        future = ActionItem.objects.create(
            title="Future one",
            department=dept,
            owner=owner,
            created_by=owner,
            status=STATUS_IN_PROGRESS,
            progress_pct=50,
            due_date=today + timedelta(days=2),
        )
        qs = overdue_action_items_queryset(owner, department=None, limit=10)
        pks = {x.pk for x in qs}
        assert overdue.pk in pks
        assert future.pk not in pks


@pytest.mark.django_db
class TestDashboardCounts:
    def test_counts_totals(self, dept, owner, make_user):
        from apps.action_items.services import dashboard_action_counts

        today = timezone.now().date()
        ActionItem.objects.create(
            title="O1",
            department=dept,
            owner=owner,
            created_by=owner,
            status=STATUS_OPEN,
            progress_pct=0,
            due_date=today + timedelta(days=5),
        )
        ActionItem.objects.create(
            title="OD",
            department=dept,
            owner=owner,
            created_by=owner,
            status=STATUS_IN_PROGRESS,
            progress_pct=50,
            due_date=today - timedelta(days=3),
        )
        counts = dashboard_action_counts(owner)
        assert counts["total_open"] >= 2
        assert counts["assigned_me"] >= 2
        assert counts["overdue"] >= 1
        assert counts["due_this_week"] >= 1
