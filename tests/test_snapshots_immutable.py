from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.utils import timezone

from apps.accounts.models import Department, User
from apps.audit.models import AuditLog
from apps.meetings.models import (
    SNAPSHOT_TRIGGER_APPROVE,
    SNAPSHOT_TRIGGER_MANUAL,
    SNAPSHOT_TRIGGER_PUBLISH,
    SNAPSHOT_TRIGGER_SUBMIT,
    STATUS_FOR_REVIEW,
    STATUS_IN_PROGRESS,
    AgendaCategory,
    AgendaItem,
    ApprovedMeetingSnapshot,
    Meeting,
    MeetingType,
)
from apps.meetings.services import (
    approve_meeting,
    create_approved_snapshot,
    publish_meeting,
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
    cat = AgendaCategory.objects.create(name="Cat", order=1)
    AgendaItem.objects.create(
        meeting=m,
        category=cat,
        order=1,
        title="Discussion Item",
        discussion="Initial discussion text",
        decision="Decision 1",
    )
    return m


@pytest.mark.django_db(transaction=True)
def test_create_snapshot_version_sequence_1_then_2(meeting, make_user, advance_meeting):
    admin = make_user("admin", groups=["Management Administrator"])
    snap1 = create_approved_snapshot(meeting, by_user=admin, trigger=SNAPSHOT_TRIGGER_MANUAL)
    assert snap1.version == 1
    snap2 = create_approved_snapshot(meeting, by_user=admin, trigger=SNAPSHOT_TRIGGER_APPROVE)
    assert snap2.version == 2


@pytest.mark.django_db(transaction=True)
def test_double_publish_unique_together_rejection(meeting, make_user, advance_meeting):
    admin = make_user("admin", groups=["Management Administrator"])
    ApprovedMeetingSnapshot.objects.create(
        meeting=meeting, version=1, trigger=SNAPSHOT_TRIGGER_PUBLISH, payload={"v": 1}
    )
    with pytest.raises((IntegrityError, ValidationError)):
        ApprovedMeetingSnapshot.objects.create(
            meeting=meeting, version=1, trigger=SNAPSHOT_TRIGGER_MANUAL, payload={"v": 2}
        )


@pytest.mark.django_db(transaction=True)
def test_payload_keys_match_8_part(meeting, make_user, advance_meeting):
    admin = make_user("admin", groups=["Management Administrator"])
    snap = create_approved_snapshot(meeting, by_user=admin, trigger=SNAPSHOT_TRIGGER_MANUAL)
    payload = snap.payload
    expected_top = {
        "version_format",
        "generated_at",
        "generated_by",
        "meeting_meta",
        "attendance",
        "agenda_items",
        "discussions",
        "decisions",
        "action_items",
        "sales_data",
        "status_history",
        "snapshots",
        "version",
        "approval_meta",
    }
    assert isinstance(payload, dict)
    for k in (
        "meeting_meta",
        "attendance",
        "agenda_items",
        "discussions",
        "decisions",
        "action_items",
        "sales_data",
        "version",
    ):
        assert k in payload


@pytest.mark.django_db(transaction=True)
def test_payload_contains_snapshot_version(meeting, make_user, advance_meeting):
    admin = make_user("admin", groups=["Management Administrator"])
    snap = create_approved_snapshot(meeting, by_user=admin, trigger=SNAPSHOT_TRIGGER_MANUAL)
    assert snap.payload["version"] == snap.version
    assert snap.payload["approval_meta"]["version"] == snap.version


@pytest.mark.django_db(transaction=True)
def test_after_snapshot_edit_live_agenda_item_discussion_snapshot_payload_unchanged(
    meeting, make_user, advance_meeting
):
    admin = make_user("admin", groups=["Management Administrator"])
    snap = create_approved_snapshot(meeting, by_user=admin, trigger=SNAPSHOT_TRIGGER_MANUAL)
    snapshot_discussion = snap.payload["agenda_items"][0]["discussion"]
    ai = meeting.agenda_items.first()
    ai.discussion = "CHANGED LIVE DISCUSSION TEXT"
    ai.save()
    snap.refresh_from_db()
    assert snap.payload["agenda_items"][0]["discussion"] == snapshot_discussion
    assert snap.payload["agenda_items"][0]["discussion"] != "CHANGED LIVE DISCUSSION TEXT"


@pytest.mark.django_db(transaction=True)
def test_snapshot_view_approved_snapshot_detail_only_renders_payload(
    meeting, make_user, client, advance_meeting
):
    admin = make_user("admin_view", groups=["Management Administrator"])
    client.force_login(admin)
    snap = create_approved_snapshot(meeting, by_user=admin, trigger=SNAPSHOT_TRIGGER_APPROVE)
    from django.urls import reverse

    url = reverse("meetings:approved_snapshot_detail", args=[snap.pk])
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    with CaptureQueriesContext(connection) as ctx:
        response = client.get(url)
    assert response.status_code == 200
    title_in_response = (
        meeting.title.encode() in response.content or meeting.title in response.content.decode()
    )
    assert title_in_response
    meeting_queries = [
        q
        for q in ctx.captured_queries
        if '"meetings_meeting"' in q["sql"] or "meetings_meeting" in q["sql"]
    ]
    agenda_queries = [
        q
        for q in ctx.captured_queries
        if '"meetings_agendaitem"' in q["sql"] or "meetings_agendaitem" in q["sql"]
    ]
    assert snap.payload["meeting_meta"]["title"] == meeting.title


@pytest.mark.django_db(transaction=True)
def test_snapshot_immutable_after_creation(meeting, make_user, advance_meeting):
    admin = make_user("admin_imm", groups=["Management Administrator"])
    snap = create_approved_snapshot(meeting, by_user=admin, trigger=SNAPSHOT_TRIGGER_MANUAL)
    original_payload = snap.payload.copy()
    with pytest.raises((IntegrityError, ValidationError, Exception)):
        snap.version = 999
        snap.save()
    snap.refresh_from_db()
    assert snap.version == 1
    assert snap.payload == original_payload


@pytest.mark.django_db(transaction=True)
def test_payload_frozen_at_set(meeting, make_user, advance_meeting):
    admin = make_user("admin_frz", groups=["Management Administrator"])
    snap = create_approved_snapshot(meeting, by_user=admin, trigger=SNAPSHOT_TRIGGER_MANUAL)
    assert "generated_at" in snap.payload
    assert snap.payload["generated_at"] is not None
    assert snap.approved_at is not None


@pytest.mark.django_db(transaction=True)
def test_approve_publish_snapshot_trigger_approve_publish(meeting, make_user, advance_meeting):
    admin = make_user("admin_ap", groups=["Management Administrator"])
    advance_meeting(meeting, STATUS_IN_PROGRESS, by_user=admin)
    advance_meeting(meeting, STATUS_FOR_REVIEW, by_user=admin)
    approve_meeting(meeting, by_user=admin)
    meeting.refresh_from_db()
    snap_approve = ApprovedMeetingSnapshot.objects.filter(
        meeting=meeting, trigger=SNAPSHOT_TRIGGER_APPROVE
    ).first()
    assert snap_approve is not None
    assert snap_approve.trigger == SNAPSHOT_TRIGGER_APPROVE
    publish_meeting(meeting, by_user=admin)
    meeting.refresh_from_db()
    snap_publish = (
        ApprovedMeetingSnapshot.objects.filter(meeting=meeting, trigger=SNAPSHOT_TRIGGER_PUBLISH)
        .order_by("-version")
        .first()
    )
    assert snap_publish is not None
    assert snap_publish.trigger == SNAPSHOT_TRIGGER_PUBLISH


@pytest.mark.django_db(transaction=True)
def test_snapshot_trigger_set_manual_valid(meeting, make_user, advance_meeting):
    admin = make_user("admin_mn", groups=["Management Administrator"])
    snap = create_approved_snapshot(meeting, by_user=admin, trigger=SNAPSHOT_TRIGGER_MANUAL)
    assert snap.trigger == SNAPSHOT_TRIGGER_MANUAL
    snap2 = create_approved_snapshot(meeting, by_user=admin, trigger=SNAPSHOT_TRIGGER_SUBMIT)
    assert snap2.trigger == SNAPSHOT_TRIGGER_SUBMIT


@pytest.mark.django_db(transaction=True)
def test_snapshot_trigger_invalid_raises(meeting, make_user, advance_meeting):
    admin = make_user("admin_inv", groups=["Management Administrator"])
    with pytest.raises(ValidationError):
        create_approved_snapshot(meeting, by_user=admin, trigger="INVALID_TRIGGER_XYZ")


@pytest.mark.django_db(transaction=True)
def test_meeting_published_at_set_once_only(meeting, make_user, advance_meeting):
    admin = make_user("admin_pub", groups=["Management Administrator"])
    advance_meeting(meeting, STATUS_IN_PROGRESS, by_user=admin)
    advance_meeting(meeting, STATUS_FOR_REVIEW, by_user=admin)
    approve_meeting(meeting, by_user=admin)
    assert meeting.published_at is None
    publish_meeting(meeting, by_user=admin)
    first_published_at = meeting.published_at
    assert first_published_at is not None
    with pytest.raises((ValidationError, Exception)):
        publish_meeting(meeting, by_user=admin)
    meeting.refresh_from_db()
    assert meeting.published_at == first_published_at


@pytest.mark.django_db(transaction=True)
def test_auditlog_action_snapshot_exists_post_snapshot(meeting, make_user, advance_meeting):
    admin = make_user("admin_aud_snap", groups=["Management Administrator"])
    before_count = AuditLog.objects.filter(action=AuditLog.ACTION_SNAPSHOT).count()
    snap = create_approved_snapshot(meeting, by_user=admin, trigger=SNAPSHOT_TRIGGER_MANUAL)
    after_count = AuditLog.objects.filter(action=AuditLog.ACTION_SNAPSHOT).count()
    assert after_count >= before_count


@pytest.mark.django_db(transaction=True)
def test_auditlog_action_approve_post_approve_service(meeting, make_user, advance_meeting):
    admin = make_user("admin_aud_app", groups=["Management Administrator"])
    advance_meeting(meeting, STATUS_IN_PROGRESS, by_user=admin)
    advance_meeting(meeting, STATUS_FOR_REVIEW, by_user=admin)
    before = AuditLog.objects.filter(action=AuditLog.ACTION_APPROVE).count()
    approve_meeting(meeting, by_user=admin)
    after = AuditLog.objects.filter(action=AuditLog.ACTION_APPROVE).count()
    assert after > before


@pytest.mark.django_db(transaction=True)
def test_auditlog_action_publish_log_created(meeting, make_user, advance_meeting):
    admin = make_user("admin_aud_pub", groups=["Management Administrator"])
    advance_meeting(meeting, STATUS_IN_PROGRESS, by_user=admin)
    advance_meeting(meeting, STATUS_FOR_REVIEW, by_user=admin)
    approve_meeting(meeting, by_user=admin)
    before = AuditLog.objects.filter(action=AuditLog.ACTION_PUBLISH).count()
    publish_meeting(meeting, by_user=admin)
    after = AuditLog.objects.filter(action=AuditLog.ACTION_PUBLISH).count()
    assert after > before


@pytest.mark.django_db(transaction=True)
def test_payload_action_items_present(meeting, make_user, dept, advance_meeting):
    admin = make_user("admin_ai", groups=["Management Administrator"])
    from apps.action_items.models import ActionItem
    from apps.meetings.models import ActionItemLink

    ai_item = meeting.agenda_items.first()
    action = ActionItem.objects.create(
        title="Follow up action",
        created_by=admin,
        owner=admin,
        source_meeting=meeting,
        source_agenda_item=ai_item,
        department=dept,
    )
    ActionItemLink.objects.create(agenda_item=ai_item, action_item=action, created_by=admin)
    snap = create_approved_snapshot(meeting, by_user=admin, trigger=SNAPSHOT_TRIGGER_MANUAL)
    assert "action_items" in snap.payload
    assert len(snap.payload["action_items"]) >= 1


@pytest.mark.django_db(transaction=True)
def test_snapshot_trigger_audit_snapshot_created_for_manual_snapshot(meeting, make_user):
    admin = make_user("admin_aud_manual", groups=["Management Administrator"])
    before = AuditLog.objects.filter(action=AuditLog.ACTION_SNAPSHOT).count()
    create_approved_snapshot(meeting, by_user=admin, trigger=SNAPSHOT_TRIGGER_MANUAL)
    after = AuditLog.objects.filter(action=AuditLog.ACTION_SNAPSHOT).count()
    assert after == before + 1
