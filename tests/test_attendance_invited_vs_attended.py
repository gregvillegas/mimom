from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.accounts.models import Department, User
from apps.meetings.models import (
    RSVP_MAYBE,
    RSVP_NO,
    RSVP_PENDING,
    RSVP_YES,
    Meeting,
    MeetingAttendance,
    MeetingType,
)


@pytest.fixture
def mtype(db):
    return MeetingType.objects.create(name="Standup", code="STND")


@pytest.fixture
def dept(db):
    return Department.objects.create(name="HR", code="HR")


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
def meeting(mtype, make_user, dept):
    chair = make_user("chair_at", groups=["Meeting Chairperson"])
    start = timezone.now() + timedelta(days=2)
    return Meeting.objects.create(
        type=mtype,
        title="Attendance Flags Test",
        start_at=start,
        end_at=start + timedelta(hours=1),
        location="HR Room",
        department=dept,
        chair=chair,
        created_by=chair,
    )


@pytest.mark.django_db
class TestInvitedVsAttendedFlags:
    def test_invited_true_attended_false_expected(self, meeting, make_user):
        u = make_user("u1", groups=["Department Contributor"])
        row = MeetingAttendance.objects.create(
            meeting=meeting, user=u, is_invited=True, is_attended=False, rsvp_status=RSVP_YES
        )
        assert row.is_invited is True
        assert row.is_attended is False

    def test_invited_true_attended_true_present(self, meeting, make_user):
        u = make_user("u2", groups=["Department Contributor"])
        arrived = meeting.start_at + timedelta(minutes=2)
        departed = meeting.end_at - timedelta(minutes=10)
        row = MeetingAttendance.objects.create(
            meeting=meeting,
            user=u,
            is_invited=True,
            is_attended=True,
            rsvp_status=RSVP_YES,
            arrived_at=arrived,
            departed_at=departed,
        )
        assert row.is_invited is True
        assert row.is_attended is True
        assert row.arrived_at == arrived
        assert row.departed_at == departed

    def test_walk_in_invited_false_attended_true_allowed(self, meeting, make_user):
        u = make_user("u_walkin", groups=["Department Contributor"])
        row = MeetingAttendance.objects.create(
            meeting=meeting,
            user=u,
            is_invited=False,
            is_attended=True,
            rsvp_status=RSVP_PENDING,
        )
        row.full_clean()
        assert row.is_invited is False
        assert row.is_attended is True

    def test_invited_false_attended_false_quiet_on_list(self, meeting, make_user):
        u = make_user("u_none", groups=["Department Contributor"])
        row = MeetingAttendance.objects.create(
            meeting=meeting,
            user=u,
            is_invited=False,
            is_attended=False,
            rsvp_status=RSVP_NO,
        )
        assert row.is_invited is False
        assert row.is_attended is False
        assert row.rsvp_status == RSVP_NO

    def test_departure_before_arrival_raises(self, meeting, make_user):
        u = make_user("u_bad_time", groups=["Department Contributor"])
        arrived = meeting.start_at + timedelta(minutes=30)
        departed = meeting.start_at + timedelta(minutes=5)
        row = MeetingAttendance(
            meeting=meeting,
            user=u,
            is_invited=True,
            is_attended=True,
            rsvp_status=RSVP_YES,
            arrived_at=arrived,
            departed_at=departed,
        )
        with pytest.raises(ValidationError, match="Departure time"):
            row.full_clean()


@pytest.mark.django_db
class TestRsvpStatus:
    @pytest.mark.parametrize("status", [RSVP_PENDING, RSVP_YES, RSVP_NO, RSVP_MAYBE])
    def test_all_rsvp_values_accepted(self, meeting, make_user, status):
        u = make_user(f"u_rsvp_{status}", groups=["Department Contributor"])
        row = MeetingAttendance.objects.create(
            meeting=meeting, user=u, is_invited=True, is_attended=False, rsvp_status=status
        )
        assert row.rsvp_status == status


@pytest.mark.django_db
class TestCountsAndQuerying:
    def test_invited_count_and_attended_count_distinct(self, meeting, make_user):
        invited_present = make_user("inv_pres", groups=["Department Contributor"])
        invited_absent = make_user("inv_abs", groups=["Department Contributor"])
        walkin = make_user("walkin", groups=["Department Contributor"])
        MeetingAttendance.objects.create(
            meeting=meeting, user=invited_present, is_invited=True, is_attended=True
        )
        MeetingAttendance.objects.create(
            meeting=meeting, user=invited_absent, is_invited=True, is_attended=False
        )
        MeetingAttendance.objects.create(
            meeting=meeting, user=walkin, is_invited=False, is_attended=True
        )
        invited = MeetingAttendance.objects.filter(meeting=meeting, is_invited=True).count()
        attended = MeetingAttendance.objects.filter(meeting=meeting, is_attended=True).count()
        walkin_count = MeetingAttendance.objects.filter(
            meeting=meeting, is_invited=False, is_attended=True
        ).count()
        assert invited == 2
        assert attended == 2
        assert walkin_count == 1


@pytest.mark.django_db
class TestInactiveUserGuard:
    def test_inactive_user_not_allowed_invited(self, meeting, make_user):
        inactive = make_user("inac_1", groups=["Viewer"], is_active=False)
        from apps.meetings.forms import MeetingAttendanceForm

        form = MeetingAttendanceForm(
            data={
                "user": inactive.pk,
                "is_invited": "on",
                "is_attended": "",
                "rsvp_status": RSVP_PENDING,
            },
            for_user=meeting.created_by,
        )
        assert form.is_valid() is False
