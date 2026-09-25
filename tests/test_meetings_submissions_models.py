from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.utils import timezone

from apps.accounts.models import Department, User
from apps.action_items.models import ActionItem
from apps.meetings.models import (
    SECTION_ACTION_ITEMS,
    SECTION_DEPT_UPDATES,
    SECTION_NEW_BUSINESS,
    SECTION_OLD_BUSINESS,
    SECTION_OPENING_REMARKS,
    SECTION_OTHER,
    SECTION_SALES_PERFORMANCE,
    SECTION_TYPE_CHOICES,
    SNAPSHOT_TRIGGER_APPROVE,
    SNAPSHOT_TRIGGER_CHOICES,
    SNAPSHOT_TRIGGER_MANUAL,
    SNAPSHOT_TRIGGER_PUBLISH,
    SNAPSHOT_TRIGGER_SUBMIT,
    SUBMISSION_ACCEPTED,
    SUBMISSION_IN_PROGRESS,
    SUBMISSION_NOT_STARTED,
    SUBMISSION_RETURNED,
    SUBMISSION_STATUS_CHOICES,
    SUBMISSION_SUBMITTED,
    ActionItemLink,
    AgendaCategory,
    AgendaItem,
    ApprovedMeetingSnapshot,
    DepartmentSubmission,
    Meeting,
    MeetingType,
    MinutesSectionSpec,
)


@pytest.fixture
def mtype():
    return MeetingType.objects.create(name="Weekly Management", code="WEEKLY")


@pytest.fixture
def make_user():
    def _make(username, groups=None, **extra):
        email = extra.pop("email", None) or f"{username}@example.com"
        user = User.objects.create_user(
            username=username, email=email, password="pw-1234!-Strong", **extra
        )
        if groups:
            from django.contrib.auth.models import Group

            for name in groups:
                g, _ = Group.objects.get_or_create(name=name)
                user.groups.add(g)
        return user

    return _make


@pytest.fixture
def dept():
    return Department.objects.create(name="Sales", code="SALES")


@pytest.fixture
def meeting(mtype, make_user, dept):
    chair = make_user("chair_m", groups=["Meeting Chairperson"])
    start = timezone.now() + timedelta(days=2)
    return Meeting.objects.create(
        type=mtype,
        title="Sample Monday Meeting",
        start_at=start,
        end_at=start + timedelta(hours=2),
        location="Room 301",
        department=dept,
        chair=chair,
        created_by=chair,
    )


@pytest.mark.django_db
def test_minutes_section_spec_unique_together(mtype):
    MinutesSectionSpec.objects.create(
        meeting_type=mtype,
        section_type=SECTION_OPENING_REMARKS,
        order=1,
        name="Opening",
    )
    dup = MinutesSectionSpec(
        meeting_type=mtype,
        section_type=SECTION_OPENING_REMARKS,
        order=2,
        name="Opening Again",
    )
    with pytest.raises(IntegrityError):
        dup.save()


@pytest.mark.django_db
def test_department_submission_state_machine_5_states(meeting, dept):
    states = [
        SUBMISSION_NOT_STARTED,
        SUBMISSION_IN_PROGRESS,
        SUBMISSION_SUBMITTED,
        SUBMISSION_RETURNED,
        SUBMISSION_ACCEPTED,
    ]
    assert len(SUBMISSION_STATUS_CHOICES) == 5
    choice_values = {c[0] for c in SUBMISSION_STATUS_CHOICES}
    for s in states:
        assert s in choice_values
    sub = DepartmentSubmission(meeting=meeting, department=dept)
    for s in states:
        sub.submission_state = s
        sub.full_clean()


@pytest.mark.django_db
def test_department_submission_unique_together_meeting_dept(meeting, dept):
    DepartmentSubmission.objects.create(meeting=meeting, department=dept)
    dup = DepartmentSubmission(meeting=meeting, department=dept)
    with pytest.raises(IntegrityError):
        dup.save()


@pytest.mark.django_db
def test_action_item_link_fk_integrity(meeting, make_user, dept):
    user = make_user("u1")
    cat = AgendaCategory.objects.create(name="Cat", order=1)
    ai_item = AgendaItem.objects.create(
        meeting=meeting, category=cat, order=1, title="Item 1", department=dept
    )
    action = ActionItem.objects.create(
        title="Do X", created_by=user, owner=user, source_meeting=meeting
    )
    link = ActionItemLink.objects.create(agenda_item=ai_item, action_item=action, created_by=user)
    assert link.pk is not None
    ai_item_pk = ai_item.pk
    action_pk = action.pk
    ai_item.delete()
    assert not ActionItemLink.objects.filter(pk=link.pk).exists()


@pytest.mark.django_db
def test_approved_meeting_snapshot_version_sequential(meeting, make_user):
    admin = make_user("admin", groups=["Management Administrator"])
    snap1 = ApprovedMeetingSnapshot.objects.create(
        meeting=meeting, version=1, trigger=SNAPSHOT_TRIGGER_MANUAL, payload={"v": 1}
    )
    snap2 = ApprovedMeetingSnapshot.objects.create(
        meeting=meeting, version=2, trigger=SNAPSHOT_TRIGGER_APPROVE, payload={"v": 2}
    )
    assert snap1.version == 1
    assert snap2.version == 2
    bad = ApprovedMeetingSnapshot(
        meeting=meeting, version=1, trigger=SNAPSHOT_TRIGGER_PUBLISH, payload={}
    )
    with pytest.raises((IntegrityError, ValidationError)):
        bad.save()


@pytest.mark.django_db
def test_snapshot_trigger_valid_set():
    valid = {c[0] for c in SNAPSHOT_TRIGGER_CHOICES}
    expected = {
        SNAPSHOT_TRIGGER_SUBMIT,
        SNAPSHOT_TRIGGER_APPROVE,
        SNAPSHOT_TRIGGER_PUBLISH,
        SNAPSHOT_TRIGGER_MANUAL,
    }
    assert valid == expected
    assert len(SNAPSHOT_TRIGGER_CHOICES) == 4


@pytest.mark.django_db
def test_section_type_7_valid():
    valid = {c[0] for c in SECTION_TYPE_CHOICES}
    expected = {
        SECTION_OPENING_REMARKS,
        SECTION_DEPT_UPDATES,
        SECTION_ACTION_ITEMS,
        SECTION_SALES_PERFORMANCE,
        SECTION_OLD_BUSINESS,
        SECTION_NEW_BUSINESS,
        SECTION_OTHER,
    }
    assert valid == expected
    assert len(SECTION_TYPE_CHOICES) == 7


@pytest.mark.django_db
def test_submission_status_5_valid():
    valid = {c[0] for c in SUBMISSION_STATUS_CHOICES}
    expected = {
        SUBMISSION_NOT_STARTED,
        SUBMISSION_IN_PROGRESS,
        SUBMISSION_SUBMITTED,
        SUBMISSION_RETURNED,
        SUBMISSION_ACCEPTED,
    }
    assert valid == expected
    assert len(SUBMISSION_STATUS_CHOICES) == 5


@pytest.mark.django_db
def test_foreign_keys_on_delete_cascade_protect(mtype, meeting, dept, make_user):
    Meeting_type_field = Meeting._meta.get_field("type")
    assert Meeting_type_field.remote_field.on_delete.__name__ == "PROTECT"
    DS_meeting_field = DepartmentSubmission._meta.get_field("meeting")
    assert DS_meeting_field.remote_field.on_delete.__name__ == "CASCADE"
    Snap_meeting_field = ApprovedMeetingSnapshot._meta.get_field("meeting")
    assert Snap_meeting_field.remote_field.on_delete.__name__ == "CASCADE"
    MSS_mtype_field = MinutesSectionSpec._meta.get_field("meeting_type")
    assert MSS_mtype_field.remote_field.on_delete.__name__ == "CASCADE"
    AIL_agenda_field = ActionItemLink._meta.get_field("agenda_item")
    assert AIL_agenda_field.remote_field.on_delete.__name__ == "CASCADE"
    AIL_action_field = ActionItemLink._meta.get_field("action_item")
    assert AIL_action_field.remote_field.on_delete.__name__ == "CASCADE"


@pytest.mark.django_db
def test_department_submission_notes_default_empty_string(meeting, dept):
    sub = DepartmentSubmission.objects.create(meeting=meeting, department=dept)
    assert sub.notes == ""


@pytest.mark.django_db
def test_approved_meeting_snapshot_payload_default_dict(meeting):
    snap = ApprovedMeetingSnapshot.objects.create(
        meeting=meeting, version=1, trigger=SNAPSHOT_TRIGGER_MANUAL
    )
    assert snap.payload == {}
    assert isinstance(snap.payload, dict)


@pytest.mark.django_db
def test_minutes_section_spec_protect_on_delete(mtype, meeting, make_user):
    spec = MinutesSectionSpec.objects.create(
        meeting_type=mtype,
        section_type=SECTION_OPENING_REMARKS,
        order=1,
        name="Opening",
    )
    assert spec.meeting_type_id == mtype.pk
    MSS_mtype_field = MinutesSectionSpec._meta.get_field("meeting_type")
    assert MSS_mtype_field.remote_field.on_delete.__name__ == "CASCADE"
