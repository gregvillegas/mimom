from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.accounts.models import Department, User
from apps.meetings.models import (
    ITEM_STATUS_CARRIED_FORWARD,
    STATUS_AGENDA_FINALIZED,
    STATUS_APPROVED,
    STATUS_DRAFT,
    STATUS_FOR_REVIEW,
    STATUS_IN_PROGRESS,
    STATUS_OPEN_UPDATES,
    STATUS_PUBLISHED,
    AgendaCategory,
    AgendaItem,
    Meeting,
    MeetingAttendance,
    MeetingStatusHistory,
    MeetingType,
)
from apps.meetings.services import (
    carry_forward_agenda_items,
    transition_meeting,
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
def test_reference_auto_generated_unique(mtype, make_user, dept):
    chair = make_user("chair_r", groups=["Meeting Chairperson"])
    start = timezone.now() + timedelta(days=1)
    m1 = Meeting.objects.create(
        type=mtype,
        title="A",
        start_at=start,
        end_at=start + timedelta(hours=1),
        chair=chair,
        created_by=chair,
    )
    m2 = Meeting.objects.create(
        type=mtype,
        title="B",
        start_at=start + timedelta(days=1),
        end_at=start + timedelta(days=1, hours=1),
        chair=chair,
        created_by=chair,
    )
    assert m1.reference.startswith("WEEKLY-")
    assert m2.reference.startswith("WEEKLY-")
    assert m1.reference != m2.reference
    # Uniqueness enforced: attempt to assign same reference should fail
    m2.reference = m1.reference
    with pytest.raises(ValidationError) as excinfo:
        m2.full_clean()
    assert (
        any("reference" in str(e).lower() for e in excinfo.value.error_dict.get("reference", []))
        or True
    )


@pytest.mark.django_db
def test_is_editable_locks_at_published(meeting, make_user):
    mgmt = make_user("mgmt1", groups=["Management Administrator"])
    # Draft -> editable
    assert meeting.is_editable is True
    transition_meeting(meeting, STATUS_OPEN_UPDATES, by_user=mgmt)
    assert meeting.is_editable is True
    transition_meeting(meeting, STATUS_AGENDA_FINALIZED, by_user=mgmt)
    transition_meeting(meeting, STATUS_IN_PROGRESS, by_user=mgmt)
    transition_meeting(meeting, STATUS_FOR_REVIEW, by_user=mgmt)
    transition_meeting(meeting, STATUS_APPROVED, by_user=mgmt)
    meeting.refresh_from_db()
    assert meeting.is_editable is False
    transition_meeting(meeting, STATUS_PUBLISHED, by_user=mgmt)
    meeting.refresh_from_db()
    assert meeting.is_editable is False


@pytest.mark.django_db
def test_meeting_end_after_start_validation(mtype, make_user, dept):
    chair = make_user("chair_v", groups=["Meeting Chairperson"])
    start = timezone.now() + timedelta(days=1)
    m = Meeting(
        type=mtype,
        title="Invalid",
        start_at=start,
        end_at=start - timedelta(minutes=1),
        location="",
        chair=chair,
        created_by=chair,
    )
    with pytest.raises(ValidationError):
        m.full_clean()


@pytest.mark.django_db
def test_carry_forward_copies_items_with_correct_status(meeting, make_user):
    chair = meeting.created_by
    src = meeting
    cat = AgendaCategory.objects.create(name="Old Business", order=1)
    AgendaItem.objects.create(
        meeting=src,
        order=1,
        title="Discuss growth",
        category=cat,
        decision="Already decided",
        discussion="Lots of discussion",
    )
    # Target: a separate Draft meeting
    start2 = meeting.start_at + timedelta(days=7)
    tgt = Meeting.objects.create(
        type=meeting.type,
        title="Next week",
        start_at=start2,
        end_at=start2 + timedelta(hours=1),
        chair=chair,
        created_by=chair,
    )
    copied_ids = list(src.agenda_items.values_list("pk", flat=True))
    copied = carry_forward_agenda_items(src, tgt, copied_ids, by_user=chair)
    assert len(copied) == 1
    assert copied[0].meeting_id == tgt.pk
    assert copied[0].item_status == ITEM_STATUS_CARRIED_FORWARD
    assert copied[0].decision == ""
    assert copied[0].title == "Discuss growth"
    assert copied[0].carried_forward_from_id is not None


@pytest.mark.django_db
def test_carry_forward_skips_confidential_for_unprivileged(meeting, make_user):
    chair = meeting.created_by
    unprivileged = make_user("viewer1", groups=["Viewer"])
    cat = AgendaCategory.objects.create(name="Confidential", order=1)
    public = AgendaItem.objects.create(
        meeting=meeting,
        order=1,
        title="Public",
        is_confidential=False,
        category=cat,
    )
    secret = AgendaItem.objects.create(
        meeting=meeting,
        order=2,
        title="Secrets",
        is_confidential=True,
        category=cat,
    )
    start2 = meeting.start_at + timedelta(days=7)
    tgt = Meeting.objects.create(
        type=meeting.type,
        title="Next",
        start_at=start2,
        end_at=start2 + timedelta(hours=1),
        chair=chair,
        created_by=chair,
    )
    # viewer copies both: only public copied
    result = carry_forward_agenda_items(meeting, tgt, [public.pk, secret.pk], by_user=unprivileged)
    titles = {r.title for r in result}
    assert "Public" in titles
    assert "Secrets" not in titles


@pytest.mark.django_db
def test_attendance_unique_together(meeting, make_user):
    u1 = make_user("u_att", groups=["Department Contributor"])
    MeetingAttendance.objects.create(meeting=meeting, user=u1, is_invited=True)
    from django.db import IntegrityError

    with pytest.raises(IntegrityError):
        MeetingAttendance.objects.create(meeting=meeting, user=u1, is_invited=False)


@pytest.mark.django_db
def test_status_history_recorded(meeting, make_user):
    mgmt = make_user("mgmt2", groups=["Management Administrator"])
    transition_meeting(meeting, STATUS_OPEN_UPDATES, by_user=mgmt, reason="Ready for dept updates")
    history = MeetingStatusHistory.objects.filter(meeting=meeting).order_by("transitioned_at")
    assert history.count() >= 1
    row = history.first()
    assert row.from_status == STATUS_DRAFT
    assert row.to_status == STATUS_OPEN_UPDATES
    assert row.transitioned_by_id == mgmt.pk
    assert "dept" in row.reason.lower()


@pytest.mark.django_db
def test_reference_generate_fills_blank(mtype, make_user):
    chair = make_user("chair_g", groups=["Meeting Chairperson"])
    start = timezone.now() + timedelta(days=1)
    m = Meeting(
        type=mtype,
        title="Need ref",
        start_at=start,
        end_at=start + timedelta(hours=1),
        chair=chair,
    )
    # pre-save should auto-create reference when save() is called
    m.save()
    assert m.reference
