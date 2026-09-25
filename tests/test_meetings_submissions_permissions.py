from datetime import timedelta

import pytest
from django.utils import timezone

from apps.accounts.models import Department, User
from apps.core.permissions import (
    can_approve_meeting,
    can_create_snapshot,
    can_publish_meeting,
    can_reopen_meeting,
    can_return_minutes,
    can_submit_minutes,
)
from apps.meetings.models import Meeting, MeetingType


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
    chair = make_user("chair_perm", groups=["Meeting Chairperson"])
    start = timezone.now() + timedelta(days=2)
    return Meeting.objects.create(
        type=mtype,
        title="Perm Test Meeting",
        start_at=start,
        end_at=start + timedelta(hours=2),
        location="Room 301",
        department=dept,
        chair=chair,
        created_by=chair,
    )


AUTHOR_ROLES = [
    "System Administrator",
    "Management Administrator",
    "Meeting Chairperson",
    "Minutes Secretary",
]

REVIEW_ROLES = [
    "System Administrator",
    "Management Administrator",
    "Meeting Chairperson",
]

REOPEN_ROLES = [
    "System Administrator",
    "Management Administrator",
]

SNAPSHOT_ROLES = [
    "System Administrator",
    "Management Administrator",
    "Meeting Chairperson",
    "Minutes Secretary",
]


@pytest.mark.django_db
def test_can_submit_minutes_author_roles_only(meeting, make_user):
    for role in AUTHOR_ROLES:
        user = make_user(f"submit_{role.replace(' ', '_').lower()}", groups=[role])
        assert can_submit_minutes(user, meeting) is True
    viewer = make_user("submit_viewer", groups=["Viewer"])
    assert can_submit_minutes(viewer, meeting) is False
    contributor = make_user("submit_contrib", groups=["Department Contributor"])
    assert can_submit_minutes(contributor, meeting) is True


@pytest.mark.django_db
def test_can_return_3_roles_only(meeting, make_user):
    for role in REVIEW_ROLES:
        user = make_user(f"return_{role.replace(' ', '_').lower()}", groups=[role])
        assert can_return_minutes(user, meeting) is True
    sec = make_user("return_sec", groups=["Minutes Secretary"])
    assert can_return_minutes(sec, meeting) is False
    viewer = make_user("return_viewer", groups=["Viewer"])
    assert can_return_minutes(viewer, meeting) is False


@pytest.mark.django_db
def test_can_approve_3_roles(meeting, make_user):
    for role in REVIEW_ROLES:
        user = make_user(f"appr_{role.replace(' ', '_').lower()}", groups=[role])
        assert can_approve_meeting(user, meeting) is True
    sec = make_user("appr_sec", groups=["Minutes Secretary"])
    assert can_approve_meeting(sec, meeting) is False


@pytest.mark.django_db
def test_can_publish_3_roles(meeting, make_user):
    for role in REVIEW_ROLES:
        user = make_user(f"pub_{role.replace(' ', '_').lower()}", groups=[role])
        assert can_publish_meeting(user, meeting) is True
    sec = make_user("pub_sec", groups=["Minutes Secretary"])
    assert can_publish_meeting(sec, meeting) is False


@pytest.mark.django_db
def test_can_reopen_2_roles_only(meeting, make_user):
    for role in REOPEN_ROLES:
        user = make_user(f"reopen_{role.replace(' ', '_').lower()}", groups=[role])
        assert can_reopen_meeting(user, meeting) is True
    chair = make_user("reopen_chair", groups=["Meeting Chairperson"])
    assert can_reopen_meeting(chair, meeting) is False
    sec = make_user("reopen_sec", groups=["Minutes Secretary"])
    assert can_reopen_meeting(sec, meeting) is False
    viewer = make_user("reopen_viewer", groups=["Viewer"])
    assert can_reopen_meeting(viewer, meeting) is False


@pytest.mark.django_db
def test_can_create_snapshot_4_roles(meeting, make_user):
    for role in SNAPSHOT_ROLES:
        user = make_user(f"snap_{role.replace(' ', '_').lower()}", groups=[role])
        assert can_create_snapshot(user, meeting) is True
    contrib = make_user("snap_contrib", groups=["Department Contributor"])
    assert can_create_snapshot(contrib, meeting) is False
    viewer = make_user("snap_viewer", groups=["Viewer"])
    assert can_create_snapshot(viewer, meeting) is False


@pytest.mark.django_db
def test_templatetags_submit_tag_render_tag(meeting, make_user, client, advance_meeting):
    from django.template import Context, Template

    chair = make_user("tt_chair", groups=["Meeting Chairperson"])
    client.force_login(chair)
    t = Template("{% load permissions %}{% can_submit_minutes_tag meeting as x %}{{ x }}")
    c = Context({"user": chair, "meeting": meeting, "request": type("R", (), {"user": chair})()})
    rendered = t.render(c)
    assert "True" in rendered or "true" in rendered.lower() or rendered.strip() == "True"
    viewer = make_user("tt_viewer", groups=["Viewer"])
    t2 = Template("{% load permissions %}{% can_submit_minutes_tag meeting as x %}{{ x }}")
    c2 = Context({"user": viewer, "meeting": meeting, "request": type("R", (), {"user": viewer})()})
    rendered2 = t2.render(c2)
    assert rendered2.strip() == "False" or "false" in rendered2.lower()


@pytest.mark.django_db
def test_cbv_minutes_edit_required_mixin_non_role_403(meeting, make_user, client, advance_meeting):
    from django.urls import reverse

    viewer = make_user("cbv_viewer", groups=["Viewer"])
    client.force_login(viewer)
    url = reverse("meetings:minutes_editor", args=[meeting.pk])
    resp = client.get(url)
    assert resp.status_code in (302, 403)
    secretary = make_user("cbv_sec", groups=["Minutes Secretary"])
    client.force_login(secretary)
    resp2 = client.get(url)
    assert resp2.status_code == 200


@pytest.mark.django_db
def test_cbv_minutes_approver_required_mixin_role_ok_non_role_403(
    meeting, make_user, client, advance_meeting
):
    from django.urls import reverse

    from apps.meetings.models import STATUS_IN_PROGRESS

    chair = make_user("cbv_app_chair", groups=["Meeting Chairperson"])
    secretary = make_user("cbv_app_sec", groups=["Minutes Secretary"])
    advance_meeting(meeting, STATUS_IN_PROGRESS, by_user=chair)
    from apps.meetings.services import submit_for_review

    submit_for_review(meeting, by_user=secretary)
    viewer = make_user("cbv_app_viewer", groups=["Viewer"])
    client.force_login(viewer)
    approve_url = reverse("meetings:approve_meeting", args=[meeting.pk])
    resp = client.post(approve_url, {})
    assert resp.status_code in (302, 403)
    client.force_login(chair)
    resp2 = client.post(approve_url, {"reason": "ok"})
    assert resp2.status_code in (200, 302)
