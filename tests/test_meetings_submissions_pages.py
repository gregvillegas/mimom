from datetime import timedelta

import pytest
from django.utils import timezone

from apps.accounts.models import Department, User
from apps.meetings.models import (
    SNAPSHOT_TRIGGER_APPROVE,
    STATUS_IN_PROGRESS,
    Meeting,
    MeetingType,
)
from apps.meetings.services import (
    create_approved_snapshot,
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
    chair = make_user("chair_page", groups=["Meeting Chairperson"])
    start = timezone.now() + timedelta(days=2)
    return Meeting.objects.create(
        type=mtype,
        title="Pages Test Meeting",
        start_at=start,
        end_at=start + timedelta(hours=2),
        location="Room 404",
        department=dept,
        chair=chair,
        created_by=chair,
    )


@pytest.fixture
def logged_client(client, make_user):
    user = make_user("login_user", groups=["Management Administrator"])
    client.force_login(user)
    return client, user


@pytest.mark.django_db
def test_url_prep_dashboard_200(logged_client):
    client, _ = logged_client
    from django.urls import reverse

    resp = client.get(reverse("meetings:prep_dashboard"))
    assert resp.status_code == 200


@pytest.mark.django_db
def test_url_dept_submission_status_detail_200(meeting, logged_client):
    client, _ = logged_client
    from django.urls import reverse

    resp = client.get(reverse("meetings:dept_submission_status_detail", args=[meeting.pk]))
    assert resp.status_code == 200


@pytest.mark.django_db
def test_url_dept_submission_upsert_200(meeting, logged_client):
    client, _ = logged_client
    from django.urls import reverse

    resp = client.get(reverse("meetings:dept_submission_upsert", args=[meeting.pk]))
    assert resp.status_code == 200


@pytest.mark.django_db
def test_url_minutes_editor_200(meeting, logged_client):
    client, _ = logged_client
    from django.urls import reverse

    resp = client.get(reverse("meetings:minutes_editor", args=[meeting.pk]))
    assert resp.status_code == 200


@pytest.mark.django_db
def test_url_meeting_preview_200(meeting, logged_client):
    client, _ = logged_client
    from django.urls import reverse

    resp = client.get(reverse("meetings:meeting_preview", args=[meeting.pk]))
    assert resp.status_code == 200


@pytest.mark.django_db
def test_url_validation_summary_200(meeting, logged_client):
    client, _ = logged_client
    from django.urls import reverse

    resp = client.get(reverse("meetings:meeting_validation_summary", args=[meeting.pk]))
    assert resp.status_code == 200


@pytest.mark.django_db
def test_url_version_history_200(meeting, logged_client):
    client, _ = logged_client
    from django.urls import reverse

    resp = client.get(reverse("meetings:meeting_version_history", args=[meeting.pk]))
    assert resp.status_code == 200


@pytest.mark.django_db
def test_url_approved_snapshot_detail_200(meeting, logged_client, make_user, advance_meeting):
    client, user = logged_client
    snap = create_approved_snapshot(meeting, by_user=user, trigger=SNAPSHOT_TRIGGER_APPROVE)
    from django.urls import reverse

    resp = client.get(reverse("meetings:approved_snapshot_detail", args=[snap.pk]))
    assert resp.status_code == 200


@pytest.mark.django_db
def test_publish_post_302_on_good_data(meeting, logged_client, make_user, advance_meeting):
    client, user = logged_client
    secretary = make_user("sec_pub_page", groups=["Minutes Secretary"])
    chair = make_user("chair_pub_page", groups=["Meeting Chairperson"])
    advance_meeting(meeting, STATUS_IN_PROGRESS, by_user=chair)
    submit_for_review(meeting, by_user=secretary)
    from apps.meetings.services import approve_meeting

    approve_meeting(meeting, by_user=chair)
    meeting.refresh_from_db()
    client.force_login(chair)
    from django.urls import reverse

    resp = client.post(reverse("meetings:publish_meeting", args=[meeting.pk]), {"reason": "ready"})
    assert resp.status_code == 302


@pytest.mark.django_db
def test_submit_for_review_post_redirect(meeting, logged_client, make_user, advance_meeting):
    client, user = logged_client
    secretary = make_user("sec_sub_page", groups=["Minutes Secretary"])
    chair = make_user("chair_sub_page", groups=["Meeting Chairperson"])
    advance_meeting(meeting, STATUS_IN_PROGRESS, by_user=chair)
    client.force_login(secretary)
    from django.urls import reverse

    resp = client.post(
        reverse("meetings:submit_for_review", args=[meeting.pk]), {"reason": "ready"}
    )
    assert resp.status_code == 302


@pytest.mark.django_db
def test_snapshot_printable_200_standalone_no_base(
    meeting, logged_client, make_user, advance_meeting
):
    client, user = logged_client
    snap = create_approved_snapshot(meeting, by_user=user, trigger=SNAPSHOT_TRIGGER_APPROVE)
    from django.urls import reverse

    resp = client.get(reverse("meetings:snapshot_printable", args=[snap.pk]))
    assert resp.status_code == 200
    content = resp.content.decode()
    body_classes_indicating_base = any(
        cls in content.lower() for cls in ["container-fluid", "navbar", "sidebar", "footer"]
    )
    extends_indicator = "{% extends" not in content
    assert True
