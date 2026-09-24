from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.accounts.models import Department, User
from apps.audit.models import AuditLog
from apps.meetings.models import (
    STATUS_AGENDA_FINALIZED,
    STATUS_APPROVED,
    STATUS_ARCHIVED,
    STATUS_CLOSED,
    STATUS_DRAFT,
    STATUS_FOR_REVIEW,
    STATUS_IN_PROGRESS,
    STATUS_OPEN_UPDATES,
    STATUS_PUBLISHED,
    STATUS_RETURNED_FOR_CORRECTION,
    Meeting,
    MeetingStatusHistory,
    MeetingType,
)
from apps.meetings.services import (
    VALID_TRANSITIONS,
    transition_meeting,
)


@pytest.fixture
def mtype(db):
    return MeetingType.objects.create(name="Weekly Management", code="WEEKLY")


@pytest.fixture
def dept(db):
    return Department.objects.create(name="Operations", code="OPS")


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
    chair = make_user("chair_t", groups=["Meeting Chairperson"])
    start = timezone.now() + timedelta(days=2)
    return Meeting.objects.create(
        type=mtype,
        title="Transition Test Meeting",
        start_at=start,
        end_at=start + timedelta(hours=2),
        location="Room 101",
        department=dept,
        chair=chair,
        created_by=chair,
    )


ALL_STATUSES = [
    STATUS_DRAFT,
    STATUS_OPEN_UPDATES,
    STATUS_AGENDA_FINALIZED,
    STATUS_IN_PROGRESS,
    STATUS_FOR_REVIEW,
    STATUS_RETURNED_FOR_CORRECTION,
    STATUS_APPROVED,
    STATUS_PUBLISHED,
    STATUS_CLOSED,
    STATUS_ARCHIVED,
]


def _force_status(meeting, status):
    Meeting.objects.filter(pk=meeting.pk).update(status=status)
    meeting.refresh_from_db()


@pytest.mark.django_db(transaction=True)
class TestValidTransitionDAG:
    def test_all_valid_edges_pass(self, meeting, make_user):
        mgmt = make_user("mgmt_v", groups=["Management Administrator"])
        covered = 0
        for current in ALL_STATUSES:
            for target in VALID_TRANSITIONS.get(current, set()):
                if current == target:
                    continue
                _force_status(meeting, current)
                try:
                    transition_meeting(
                        meeting,
                        target,
                        by_user=mgmt,
                        reason="DAG coverage test",
                        skip_role_check=True,
                    )
                except ValidationError as e:
                    pytest.fail(f"Valid edge {current}->{target} raised: {e}")
                covered += 1
        assert covered >= 10

    def test_invalid_edges_raise(self, meeting, make_user):
        mgmt = make_user("mgmt_i", groups=["Management Administrator"])
        invalid_edges = [
            (STATUS_DRAFT, STATUS_PUBLISHED),
            (STATUS_DRAFT, STATUS_APPROVED),
            (STATUS_APPROVED, STATUS_IN_PROGRESS),
            (STATUS_PUBLISHED, STATUS_FOR_REVIEW),
            (STATUS_CLOSED, STATUS_DRAFT),
            (STATUS_ARCHIVED, STATUS_DRAFT),
            (STATUS_OPEN_UPDATES, STATUS_PUBLISHED),
        ]
        for current, target in invalid_edges:
            _force_status(meeting, current)
            with pytest.raises(ValidationError, match="not permitted"):
                transition_meeting(
                    meeting,
                    target,
                    by_user=mgmt,
                    reason="bad edge",
                    skip_role_check=True,
                )

    def test_same_status_raises(self, meeting, make_user):
        mgmt = make_user("mgmt_s", groups=["Management Administrator"])
        _force_status(meeting, STATUS_OPEN_UPDATES)
        with pytest.raises(ValidationError, match="identical"):
            transition_meeting(
                meeting,
                STATUS_OPEN_UPDATES,
                by_user=mgmt,
                skip_role_check=True,
            )

    def test_invalid_target_status_string_raises(self, meeting, make_user):
        mgmt = make_user("mgmt_x", groups=["Management Administrator"])
        with pytest.raises(ValidationError, match="Invalid target status"):
            transition_meeting(meeting, "NOT_A_STATUS", by_user=mgmt, skip_role_check=True)


@pytest.mark.django_db(transaction=True)
class TestAdminAuthorization:
    def test_returned_requires_admin_role(self, meeting, make_user):
        chair = make_user("chair_r", groups=["Meeting Chairperson"])
        _force_status(meeting, STATUS_FOR_REVIEW)
        with pytest.raises(ValidationError, match="Administrator privileges"):
            transition_meeting(
                meeting,
                STATUS_RETURNED_FOR_CORRECTION,
                by_user=chair,
                reason="needs fix",
            )

    def test_archived_requires_admin_role(self, meeting, make_user):
        chair = make_user("chair_a", groups=["Meeting Chairperson"])
        with pytest.raises(ValidationError, match="Administrator privileges"):
            transition_meeting(meeting, STATUS_ARCHIVED, by_user=chair, reason="archiving")

    def test_management_admin_can_return_for_correction(self, meeting, make_user):
        mgmt = make_user("mgmt_ok", groups=["Management Administrator"])
        _force_status(meeting, STATUS_FOR_REVIEW)
        history = transition_meeting(
            meeting,
            STATUS_RETURNED_FOR_CORRECTION,
            by_user=mgmt,
            reason="Needs agenda fix",
        )
        assert meeting.status == STATUS_RETURNED_FOR_CORRECTION
        assert history.to_status == STATUS_RETURNED_FOR_CORRECTION

    def test_superuser_bypasses_admin_check(self, meeting, make_user):
        su = make_user("su_t", is_superuser=True)
        _force_status(meeting, STATUS_APPROVED)
        transition_meeting(
            meeting,
            STATUS_RETURNED_FOR_CORRECTION,
            by_user=su,
            reason="su override",
        )
        assert meeting.status == STATUS_RETURNED_FOR_CORRECTION


@pytest.mark.django_db(transaction=True)
class TestReasonRequirement:
    def test_returned_from_for_review_requires_reason(self, meeting, make_user):
        mgmt = make_user("mgmt_rr1", groups=["Management Administrator"])
        _force_status(meeting, STATUS_FOR_REVIEW)
        with pytest.raises(ValidationError, match="reason is required"):
            transition_meeting(
                meeting,
                STATUS_RETURNED_FOR_CORRECTION,
                by_user=mgmt,
                reason="",
            )

    def test_returned_from_approved_requires_reason(self, meeting, make_user):
        mgmt = make_user("mgmt_rr2", groups=["Management Administrator"])
        _force_status(meeting, STATUS_APPROVED)
        with pytest.raises(ValidationError, match="reason is required"):
            transition_meeting(
                meeting,
                STATUS_RETURNED_FOR_CORRECTION,
                by_user=mgmt,
                reason="   \t",
            )

    def test_returned_from_published_requires_reason(self, meeting, make_user):
        mgmt = make_user("mgmt_rr3", groups=["Management Administrator"])
        _force_status(meeting, STATUS_PUBLISHED)
        with pytest.raises(ValidationError, match="reason is required"):
            transition_meeting(
                meeting,
                STATUS_RETURNED_FOR_CORRECTION,
                by_user=mgmt,
            )

    def test_valid_return_with_reason_succeeds(self, meeting, make_user):
        mgmt = make_user("mgmt_rrok", groups=["Management Administrator"])
        _force_status(meeting, STATUS_FOR_REVIEW)
        transition_meeting(
            meeting,
            STATUS_RETURNED_FOR_CORRECTION,
            by_user=mgmt,
            reason="Minutes need corrections per department feedback",
        )
        assert meeting.status == STATUS_RETURNED_FOR_CORRECTION

    def test_normal_transition_without_reason_succeeds(self, meeting, make_user):
        mgmt = make_user("mgmt_nr", groups=["Management Administrator"])
        transition_meeting(meeting, STATUS_OPEN_UPDATES, by_user=mgmt)
        assert meeting.status == STATUS_OPEN_UPDATES


@pytest.mark.django_db(transaction=True)
class TestStatusHistoryAndAudit:
    def test_each_transition_writes_history_row(self, meeting, make_user):
        mgmt = make_user("mgmt_h", groups=["Management Administrator"])
        initial_count = MeetingStatusHistory.objects.filter(meeting=meeting).count()
        transition_meeting(meeting, STATUS_OPEN_UPDATES, by_user=mgmt, reason="Start updates")
        history = MeetingStatusHistory.objects.filter(meeting=meeting).order_by("-transitioned_at")
        assert history.count() == initial_count + 1
        latest = history.first()
        assert latest.from_status == STATUS_DRAFT
        assert latest.to_status == STATUS_OPEN_UPDATES
        assert latest.transitioned_by_id == mgmt.pk
        assert latest.reason == "Start updates"

    def test_publish_transition_writes_publish_audit(self, meeting, make_user):
        mgmt = make_user("mgmt_pub", groups=["Management Administrator"])
        _force_status(meeting, STATUS_APPROVED)
        transition_meeting(meeting, STATUS_PUBLISHED, by_user=mgmt, reason="publish ok")
        audit = AuditLog.objects.filter(
            record_id=str(meeting.pk), action=AuditLog.ACTION_PUBLISH
        ).first()
        assert audit is not None
        assert audit.user_id == mgmt.pk

    def test_approve_transition_writes_approve_audit(self, meeting, make_user):
        mgmt = make_user("mgmt_app", groups=["Management Administrator"])
        _force_status(meeting, STATUS_FOR_REVIEW)
        transition_meeting(meeting, STATUS_APPROVED, by_user=mgmt)
        audit = AuditLog.objects.filter(
            record_id=str(meeting.pk), action=AuditLog.ACTION_APPROVE
        ).first()
        assert audit is not None

    def test_archive_transition_writes_archive_audit(self, meeting, make_user):
        mgmt = make_user("mgmt_arc", groups=["Management Administrator"])
        _force_status(meeting, STATUS_CLOSED)
        transition_meeting(meeting, STATUS_ARCHIVED, by_user=mgmt, reason="retire")
        audit = AuditLog.objects.filter(
            record_id=str(meeting.pk), action=AuditLog.ACTION_ARCHIVE
        ).first()
        assert audit is not None
        assert meeting.archived_at is not None

    def test_publish_sets_published_at_timestamp(self, meeting, make_user):
        mgmt = make_user("mgmt_ts", groups=["Management Administrator"])
        _force_status(meeting, STATUS_APPROVED)
        assert meeting.published_at is None
        transition_meeting(meeting, STATUS_PUBLISHED, by_user=mgmt)
        meeting.refresh_from_db()
        assert meeting.published_at is not None

    def test_close_sets_closed_at_timestamp(self, meeting, make_user):
        mgmt = make_user("mgmt_cl", groups=["Management Administrator"])
        _force_status(meeting, STATUS_PUBLISHED)
        assert meeting.closed_at is None
        transition_meeting(meeting, STATUS_CLOSED, by_user=mgmt)
        meeting.refresh_from_db()
        assert meeting.closed_at is not None


@pytest.mark.django_db(transaction=True)
class TestTimestampsAndHistory:
    def test_full_lifecycle_each_step_writes_history(self, meeting, make_user):
        mgmt = make_user("mgmt_lc", groups=["Management Administrator"])
        expected = [
            (STATUS_DRAFT, STATUS_OPEN_UPDATES, "Open"),
            (STATUS_OPEN_UPDATES, STATUS_AGENDA_FINALIZED, "Agenda"),
            (STATUS_AGENDA_FINALIZED, STATUS_IN_PROGRESS, "Start"),
            (STATUS_IN_PROGRESS, STATUS_FOR_REVIEW, "Review"),
            (STATUS_FOR_REVIEW, STATUS_APPROVED, "Approve"),
            (STATUS_APPROVED, STATUS_PUBLISHED, "Publish"),
        ]
        for _from, _to, reason in expected:
            transition_meeting(meeting, _to, by_user=mgmt, reason=reason)
        rows = list(
            MeetingStatusHistory.objects.filter(meeting=meeting).order_by("transitioned_at")
        )
        assert len(rows) == len(expected)
        for idx, (f, t, _r) in enumerate(expected):
            assert rows[idx].from_status == f
            assert rows[idx].to_status == t
