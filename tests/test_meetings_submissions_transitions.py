from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.accounts.models import Department, User
from apps.audit.models import AuditLog
from apps.meetings.models import (
    SNAPSHOT_TRIGGER_APPROVE,
    SNAPSHOT_TRIGGER_PUBLISH,
    STATUS_APPROVED,
    STATUS_CLOSED,
    STATUS_FOR_REVIEW,
    STATUS_IN_PROGRESS,
    STATUS_PUBLISHED,
    STATUS_RETURNED_FOR_CORRECTION,
    SUBMISSION_RETURNED,
    SUBMISSION_SUBMITTED,
    ApprovedMeetingSnapshot,
    DepartmentSubmission,
    Meeting,
    MeetingType,
)
from apps.meetings.services import (
    approve_meeting,
    close_meeting,
    publish_meeting,
    reopen_meeting,
    resubmit_for_review,
    return_for_correction,
    submit_for_review,
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
    m = Meeting.objects.create(
        type=mtype,
        title="Sample Monday Meeting",
        start_at=start,
        end_at=start + timedelta(hours=2),
        location="Room 301",
        department=dept,
        chair=chair,
        created_by=chair,
    )
    DepartmentSubmission.objects.create(
        meeting=m, department=dept, submission_state=SUBMISSION_SUBMITTED, contributor=chair
    )
    return m


@pytest.mark.django_db(transaction=True)
def test_submit_for_review_state_for_review_plus_audit_submit(meeting, make_user, advance_meeting):
    secretary = make_user("sec_sub", groups=["Minutes Secretary"])
    advance_meeting(meeting, STATUS_IN_PROGRESS, by_user=secretary)
    meeting.refresh_from_db()
    before_submit_count = AuditLog.objects.filter(action=AuditLog.ACTION_SUBMIT).count()
    submit_for_review(meeting, by_user=secretary, reason="Ready for review")
    meeting.refresh_from_db()
    assert meeting.status == STATUS_FOR_REVIEW
    after_submit_count = AuditLog.objects.filter(action=AuditLog.ACTION_SUBMIT).count()
    assert after_submit_count > before_submit_count


@pytest.mark.django_db(transaction=True)
def test_return_for_correction_requires_non_empty_reason(meeting, make_user, advance_meeting):
    chair = make_user("chair_ret", groups=["Meeting Chairperson"])
    secretary = make_user("sec_ret", groups=["Minutes Secretary"])
    advance_meeting(meeting, STATUS_IN_PROGRESS, by_user=chair)
    submit_for_review(meeting, by_user=secretary)
    meeting.refresh_from_db()
    with pytest.raises(ValidationError):
        return_for_correction(meeting, by_user=chair, reason="")
    with pytest.raises(ValidationError):
        return_for_correction(meeting, by_user=chair, reason="   ")


@pytest.mark.django_db(transaction=True)
def test_return_state_returned_plus_dept_submission_returned(meeting, make_user, advance_meeting):
    chair = make_user("chair_ret2", groups=["Meeting Chairperson"])
    secretary = make_user("sec_ret2", groups=["Minutes Secretary"])
    advance_meeting(meeting, STATUS_IN_PROGRESS, by_user=chair)
    submit_for_review(meeting, by_user=secretary)
    meeting.refresh_from_db()
    dept_sub = DepartmentSubmission.objects.get(meeting=meeting)
    dept_sub.submission_state = SUBMISSION_SUBMITTED
    dept_sub.save()
    return_for_correction(
        meeting,
        by_user=chair,
        reason="Missing sales data",
        management_remarks="Please add Q3 figures",
    )
    meeting.refresh_from_db()
    assert meeting.status == STATUS_RETURNED_FOR_CORRECTION
    dept_sub.refresh_from_db()
    assert dept_sub.submission_state == SUBMISSION_RETURNED


@pytest.mark.django_db(transaction=True)
def test_resubmit_for_review_state_and_dept_plus_audit_resubmit(
    meeting, make_user, advance_meeting
):
    chair = make_user("chair_resub", groups=["Meeting Chairperson"])
    secretary = make_user("sec_resub", groups=["Minutes Secretary"])
    advance_meeting(meeting, STATUS_IN_PROGRESS, by_user=chair)
    submit_for_review(meeting, by_user=secretary)
    return_for_correction(meeting, by_user=chair, reason="Needs more info")
    meeting.refresh_from_db()
    before_resub = AuditLog.objects.filter(action=AuditLog.ACTION_RESUBMIT).count()
    resubmit_for_review(meeting, by_user=secretary, reason="Fixed issues")
    meeting.refresh_from_db()
    assert meeting.status == STATUS_FOR_REVIEW
    dept_sub = DepartmentSubmission.objects.get(meeting=meeting)
    assert dept_sub.submission_state == SUBMISSION_SUBMITTED
    after_resub = AuditLog.objects.filter(action=AuditLog.ACTION_RESUBMIT).count()
    assert after_resub > before_resub


@pytest.mark.django_db(transaction=True)
def test_approve_state_approved_plus_create_snapshot_plus_audit_approve(
    meeting, make_user, advance_meeting
):
    chair = make_user("chair_app", groups=["Meeting Chairperson"])
    secretary = make_user("sec_app", groups=["Minutes Secretary"])
    advance_meeting(meeting, STATUS_IN_PROGRESS, by_user=chair)
    submit_for_review(meeting, by_user=secretary)
    meeting.refresh_from_db()
    before_app_audit = AuditLog.objects.filter(action=AuditLog.ACTION_APPROVE).count()
    before_snaps = ApprovedMeetingSnapshot.objects.filter(meeting=meeting).count()
    approve_meeting(meeting, by_user=chair)
    meeting.refresh_from_db()
    assert meeting.status == STATUS_APPROVED
    after_snaps = ApprovedMeetingSnapshot.objects.filter(
        meeting=meeting, trigger=SNAPSHOT_TRIGGER_APPROVE
    ).count()
    assert after_snaps > before_snaps
    after_app_audit = AuditLog.objects.filter(action=AuditLog.ACTION_APPROVE).count()
    assert after_app_audit > before_app_audit


@pytest.mark.django_db(transaction=True)
def test_publish_state_published_plus_snapshot_publish_plus_audit_publish(
    meeting, make_user, advance_meeting
):
    chair = make_user("chair_pub", groups=["Meeting Chairperson"])
    secretary = make_user("sec_pub", groups=["Minutes Secretary"])
    advance_meeting(meeting, STATUS_IN_PROGRESS, by_user=chair)
    submit_for_review(meeting, by_user=secretary)
    approve_meeting(meeting, by_user=chair)
    meeting.refresh_from_db()
    before_pub_audit = AuditLog.objects.filter(action=AuditLog.ACTION_PUBLISH).count()
    before_pub_snaps = ApprovedMeetingSnapshot.objects.filter(
        meeting=meeting, trigger=SNAPSHOT_TRIGGER_PUBLISH
    ).count()
    publish_meeting(meeting, by_user=chair)
    meeting.refresh_from_db()
    assert meeting.status == STATUS_PUBLISHED
    assert meeting.published_at is not None
    after_pub_snaps = ApprovedMeetingSnapshot.objects.filter(
        meeting=meeting, trigger=SNAPSHOT_TRIGGER_PUBLISH
    ).count()
    assert after_pub_snaps > before_pub_snaps
    after_pub_audit = AuditLog.objects.filter(action=AuditLog.ACTION_PUBLISH).count()
    assert after_pub_audit > before_pub_audit


@pytest.mark.django_db(transaction=True)
def test_publish_twice_guard_integrity_error_prevention(meeting, make_user, advance_meeting):
    chair = make_user("chair_pub2", groups=["Meeting Chairperson"])
    secretary = make_user("sec_pub2", groups=["Minutes Secretary"])
    advance_meeting(meeting, STATUS_IN_PROGRESS, by_user=chair)
    submit_for_review(meeting, by_user=secretary)
    approve_meeting(meeting, by_user=chair)
    publish_meeting(meeting, by_user=chair)
    meeting.refresh_from_db()
    first_pub = meeting.published_at
    with pytest.raises((ValidationError, IntegrityError, Exception)):
        publish_meeting(meeting, by_user=chair)
    meeting.refresh_from_db()
    assert meeting.published_at == first_pub


@pytest.mark.django_db(transaction=True)
def test_close_state_closed_only_approved_published_closable(meeting, make_user, advance_meeting):
    chair = make_user("chair_close", groups=["Meeting Chairperson"])
    secretary = make_user("sec_close", groups=["Minutes Secretary"])
    advance_meeting(meeting, STATUS_IN_PROGRESS, by_user=chair)
    submit_for_review(meeting, by_user=secretary)
    approve_meeting(meeting, by_user=chair)
    meeting.refresh_from_db()
    close_meeting(meeting, by_user=chair, reason="Meeting cycle completed")
    meeting.refresh_from_db()
    assert meeting.status == STATUS_CLOSED
    assert meeting.closed_at is not None


@pytest.mark.django_db(transaction=True)
def test_reopen_from_approved_to_returned_for_correction(meeting, make_user, advance_meeting):
    mgmt = make_user("mgmt_reopen", groups=["Management Administrator"])
    chair = make_user("chair_reopen", groups=["Meeting Chairperson"])
    secretary = make_user("sec_reopen", groups=["Minutes Secretary"])
    advance_meeting(meeting, STATUS_IN_PROGRESS, by_user=chair)
    submit_for_review(meeting, by_user=secretary)
    approve_meeting(meeting, by_user=chair)
    meeting.refresh_from_db()
    assert meeting.status == STATUS_APPROVED
    reopen_meeting(
        meeting,
        by_user=mgmt,
        target_status=STATUS_RETURNED_FOR_CORRECTION,
        reason="Critical correction needed",
    )
    meeting.refresh_from_db()
    assert meeting.status == STATUS_RETURNED_FOR_CORRECTION


@pytest.mark.django_db(transaction=True)
def test_reopen_requires_non_empty_reason(meeting, make_user, advance_meeting):
    mgmt = make_user("mgmt_reopen2", groups=["Management Administrator"])
    chair = make_user("chair_reopen2", groups=["Meeting Chairperson"])
    secretary = make_user("sec_reopen2", groups=["Minutes Secretary"])
    advance_meeting(meeting, STATUS_IN_PROGRESS, by_user=chair)
    submit_for_review(meeting, by_user=secretary)
    approve_meeting(meeting, by_user=chair)
    meeting.refresh_from_db()
    with pytest.raises(ValidationError):
        reopen_meeting(
            meeting, by_user=mgmt, target_status=STATUS_RETURNED_FOR_CORRECTION, reason=""
        )


@pytest.mark.django_db(transaction=True)
def test_reopen_unauth_role_raises(meeting, make_user, advance_meeting):
    viewer = make_user("viewer_reopen", groups=["Viewer"])
    chair = make_user("chair_reopen3", groups=["Meeting Chairperson"])
    secretary = make_user("sec_reopen3", groups=["Minutes Secretary"])
    advance_meeting(meeting, STATUS_IN_PROGRESS, by_user=chair)
    submit_for_review(meeting, by_user=secretary)
    approve_meeting(meeting, by_user=chair)
    meeting.refresh_from_db()
    with pytest.raises(ValidationError):
        reopen_meeting(
            meeting,
            by_user=viewer,
            target_status=STATUS_RETURNED_FOR_CORRECTION,
            reason="Should not work",
        )


@pytest.mark.django_db(transaction=True)
def test_close_reason_required(meeting, make_user, advance_meeting):
    chair = make_user("chair_close2", groups=["Meeting Chairperson"])
    secretary = make_user("sec_close2", groups=["Minutes Secretary"])
    advance_meeting(meeting, STATUS_IN_PROGRESS, by_user=chair)
    submit_for_review(meeting, by_user=secretary)
    approve_meeting(meeting, by_user=chair)
    meeting.refresh_from_db()
    with pytest.raises((ValidationError, Exception)):
        close_meeting(meeting, by_user=chair, reason="")


@pytest.mark.django_db(transaction=True)
def test_reopen_published_to_approved_allowed(meeting, make_user, advance_meeting):
    mgmt = make_user("mgmt_reopen_pub", groups=["Management Administrator"])
    chair = make_user("chair_reopen_pub", groups=["Meeting Chairperson"])
    secretary = make_user("sec_reopen_pub", groups=["Minutes Secretary"])
    advance_meeting(meeting, STATUS_IN_PROGRESS, by_user=chair)
    submit_for_review(meeting, by_user=secretary)
    approve_meeting(meeting, by_user=chair)
    publish_meeting(meeting, by_user=chair)
    meeting.refresh_from_db()
    assert meeting.status == STATUS_PUBLISHED
    reopen_meeting(
        meeting, by_user=mgmt, target_status=STATUS_APPROVED, reason="Unpublish for minor tweaks"
    )
    meeting.refresh_from_db()
    assert meeting.status == STATUS_APPROVED


@pytest.mark.django_db(transaction=True)
def test_transaction_atomic_rollback_on_error_partial(meeting, make_user, advance_meeting):
    chair = make_user("chair_atomic", groups=["Meeting Chairperson"])
    secretary = make_user("sec_atomic", groups=["Minutes Secretary"])
    advance_meeting(meeting, STATUS_IN_PROGRESS, by_user=chair)
    submit_for_review(meeting, by_user=secretary)
    meeting.refresh_from_db()
    status_before = meeting.status
    snap_count_before = ApprovedMeetingSnapshot.objects.filter(meeting=meeting).count()
    with pytest.raises(ValidationError), transaction.atomic():
        approve_meeting(meeting, by_user=chair)
        raise ValidationError("Simulated failure after approve")
    meeting.refresh_from_db()
    snap_count_after = ApprovedMeetingSnapshot.objects.filter(meeting=meeting).count()
    assert meeting.status == status_before
    assert snap_count_after == snap_count_before
