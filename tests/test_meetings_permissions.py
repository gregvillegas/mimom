from datetime import timedelta

import pytest
from django.contrib.auth.models import AnonymousUser
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Department, User
from apps.core.permissions import (
    can_archive_meeting,
    can_create_meeting,
    can_edit_meeting,
    can_transition_meeting,
    can_view_confidential_items,
)
from apps.meetings.models import (
    ITEM_STATUS_TO_BE_DISCUSSED,
    STATUS_AGENDA_FINALIZED,
    STATUS_APPROVED,
    STATUS_FOR_REVIEW,
    STATUS_OPEN_UPDATES,
    STATUS_PUBLISHED,
    STATUS_RETURNED_FOR_CORRECTION,
    AgendaCategory,
    AgendaItem,
    Meeting,
    MeetingType,
)


@pytest.fixture
def mtype(db):
    return MeetingType.objects.create(name="Board", code="BOARD")


@pytest.fixture
def dept(db):
    return Department.objects.create(name="Finance", code="FIN")


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
    chair = make_user("chair_p", groups=["Meeting Chairperson"])
    start = timezone.now() + timedelta(days=3)
    return Meeting.objects.create(
        type=mtype,
        title="Perms Test",
        start_at=start,
        end_at=start + timedelta(hours=1),
        location="R2",
        department=dept,
        chair=chair,
        created_by=chair,
    )


ROLE_CREATE = [
    ("System Administrator", True),
    ("Management Administrator", True),
    ("Meeting Chairperson", True),
    ("Minutes Secretary", True),
    ("Department Contributor", False),
    ("Viewer", False),
]


@pytest.mark.django_db
class TestPredicateCreateMeeting:
    @pytest.mark.parametrize("role,expected", ROLE_CREATE)
    def test_can_create_meeting_by_role(self, make_user, role, expected):
        u = make_user(f"c_{role.replace(' ', '_')}", groups=[role])
        assert can_create_meeting(u) is expected, role

    def test_anonymous_cannot_create(self):
        assert can_create_meeting(AnonymousUser()) is False

    def test_superuser_can_create(self, make_user):
        su = make_user("su_c", is_superuser=True)
        assert can_create_meeting(su) is True

    def test_inactive_user_cannot_create(self, make_user):
        sa = make_user("sa_inactive", groups=["System Administrator"], is_active=False)
        assert can_create_meeting(sa) is False


ROLE_EDIT_DRAFT = [
    ("System Administrator", True),
    ("Management Administrator", True),
    ("Meeting Chairperson", True),
    ("Minutes Secretary", True),
    ("Department Contributor", False),
    ("Viewer", False),
]


@pytest.mark.django_db
class TestPredicateEditMeeting:
    @pytest.mark.parametrize("role,expected", ROLE_EDIT_DRAFT)
    def test_edit_draft_by_role(self, meeting, make_user, role, expected):
        u = make_user(f"e_{role.replace(' ', '_')}", groups=[role])
        assert can_edit_meeting(u, meeting) is expected, role

    def test_cannot_edit_published_even_as_chair(self, meeting, make_user):
        mgmt = make_user("mgmt_loc", groups=["Management Administrator"])
        from apps.meetings.services import transition_meeting

        transition_meeting(meeting, STATUS_OPEN_UPDATES, by_user=mgmt)
        transition_meeting(meeting, STATUS_AGENDA_FINALIZED, by_user=mgmt)
        transition_meeting(meeting, "IN_PROGRESS", by_user=mgmt)
        transition_meeting(meeting, STATUS_FOR_REVIEW, by_user=mgmt)
        transition_meeting(meeting, STATUS_APPROVED, by_user=mgmt)
        transition_meeting(meeting, STATUS_PUBLISHED, by_user=mgmt)
        meeting.refresh_from_db()
        chair = meeting.chair
        assert can_edit_meeting(chair, meeting) is False
        mgmt2 = make_user("m2", groups=["Management Administrator"])
        assert can_edit_meeting(mgmt2, meeting) is False

    def test_cannot_edit_approved(self, meeting, make_user):
        mgmt = make_user("mgmt_ed", groups=["Management Administrator"])
        from apps.meetings.services import transition_meeting

        transition_meeting(meeting, STATUS_OPEN_UPDATES, by_user=mgmt)
        transition_meeting(meeting, STATUS_AGENDA_FINALIZED, by_user=mgmt)
        transition_meeting(meeting, "IN_PROGRESS", by_user=mgmt)
        transition_meeting(meeting, STATUS_FOR_REVIEW, by_user=mgmt)
        transition_meeting(meeting, STATUS_APPROVED, by_user=mgmt)
        meeting.refresh_from_db()
        assert can_edit_meeting(mgmt, meeting) is False

    def test_chair_of_meeting_can_edit_draft(self, meeting):
        chair = meeting.chair
        assert can_edit_meeting(chair, meeting) is True

    def test_creator_can_edit_draft(self, meeting):
        creator = meeting.created_by
        assert can_edit_meeting(creator, meeting) is True

    def test_locked_draft_limits_edits_to_admins(self, meeting, make_user):
        meeting.is_locked = True
        meeting.save()
        chair = make_user("chair_loc", groups=["Meeting Chairperson"])
        assert can_edit_meeting(chair, meeting) is False
        sa = make_user("sa_loc", groups=["System Administrator"])
        assert can_edit_meeting(sa, meeting) is True
        mgmt = make_user("mgmt_loc2", groups=["Management Administrator"])
        assert can_edit_meeting(mgmt, meeting) is True

    def test_anonymous_cannot_edit(self, meeting):
        assert can_edit_meeting(AnonymousUser(), meeting) is False


@pytest.mark.django_db
class TestPredicateArchiveMeeting:
    @pytest.mark.parametrize(
        "role,expected",
        [
            ("System Administrator", True),
            ("Management Administrator", True),
            ("Meeting Chairperson", False),
            ("Minutes Secretary", False),
            ("Viewer", False),
            ("Department Contributor", False),
        ],
    )
    def test_archive_by_role(self, make_user, meeting, role, expected):
        u = make_user(f"a_{role.replace(' ', '_')}", groups=[role])
        assert can_archive_meeting(u, meeting) is expected, role

    def test_superuser_can_archive(self, make_user, meeting):
        su = make_user("su_a", is_superuser=True)
        assert can_archive_meeting(su, meeting) is True


@pytest.mark.django_db
class TestPredicateTransitionMeeting:
    def test_returned_for_correction_requires_admin(self, meeting, make_user):
        chair = make_user("chair_tr", groups=["Meeting Chairperson"])
        assert can_transition_meeting(chair, meeting, STATUS_RETURNED_FOR_CORRECTION) is False
        mgmt = make_user("mgmt_tr", groups=["Management Administrator"])
        assert can_transition_meeting(mgmt, meeting, STATUS_RETURNED_FOR_CORRECTION) is True

    def test_normal_roles_can_advance(self, meeting, make_user):
        chair = make_user("chair_ad", groups=["Meeting Chairperson"])
        assert can_transition_meeting(chair, meeting, STATUS_OPEN_UPDATES) is True
        minsec = make_user("ms_ad", groups=["Minutes Secretary"])
        assert can_transition_meeting(minsec, meeting, STATUS_OPEN_UPDATES) is True


CONFIDENTIAL_ROLES_ALLOWED = [
    "System Administrator",
    "Management Administrator",
    "Meeting Chairperson",
    "Minutes Secretary",
]
CONFIDENTIAL_ROLES_DENIED = [
    "Department Contributor",
    "Viewer",
]


@pytest.mark.django_db
class TestPredicateViewConfidential:
    @pytest.mark.parametrize("role", CONFIDENTIAL_ROLES_ALLOWED)
    def test_viewer_roles_allowed(self, meeting, make_user, role):
        u = make_user(f"cf_{role.replace(' ', '_')}", groups=[role])
        assert can_view_confidential_items(u, meeting=meeting) is True, role

    @pytest.mark.parametrize("role", CONFIDENTIAL_ROLES_DENIED)
    def test_viewer_roles_denied(self, meeting, make_user, role):
        u = make_user(f"cv_{role.replace(' ', '_')}", groups=[role])
        assert can_view_confidential_items(u, meeting=meeting) is False, role

    def test_agenda_item_owner_can_view_their_own_confidential(self, meeting, make_user, dept):
        owner = make_user("owner_cf", groups=["Department Contributor"])
        cat = AgendaCategory.objects.create(name="Cat1")
        item = AgendaItem.objects.create(
            meeting=meeting,
            order=1,
            title="Secret Item",
            is_confidential=True,
            category=cat,
            owner=owner,
            item_status=ITEM_STATUS_TO_BE_DISCUSSED,
        )
        assert can_view_confidential_items(owner, agenda_item=item) is True

    def test_department_head_can_view_dept_confidential(self, meeting, make_user, dept):
        head = make_user("head_cf", groups=["Department Contributor"])
        dept.head = head
        dept.save()
        cat = AgendaCategory.objects.create(name="Cat2")
        item = AgendaItem.objects.create(
            meeting=meeting,
            order=1,
            title="Dept secret",
            is_confidential=True,
            category=cat,
            department=dept,
            item_status=ITEM_STATUS_TO_BE_DISCUSSED,
        )
        assert can_view_confidential_items(head, agenda_item=item) is True

    def test_meeting_chair_can_view_confidential_items(self, meeting):
        chair = meeting.chair
        cat = AgendaCategory.objects.create(name="Cat3")
        item = AgendaItem.objects.create(
            meeting=meeting,
            order=1,
            title="Chair sees this",
            is_confidential=True,
            category=cat,
            item_status=ITEM_STATUS_TO_BE_DISCUSSED,
        )
        assert can_view_confidential_items(chair, meeting=meeting, agenda_item=item) is True

    def test_anonymous_cannot_view_confidential(self, meeting):
        assert can_view_confidential_items(AnonymousUser(), meeting=meeting) is False


@pytest.mark.django_db
class TestViewPermissions403:
    def _login(self, client, user):
        client.force_login(user)

    def test_meeting_create_403_for_viewer(self, make_user):
        c = Client()
        viewer = make_user("v_cr", groups=["Viewer"])
        self._login(c, viewer)
        url = reverse("meetings:meeting_create")
        resp = c.get(url)
        assert resp.status_code in (302, 403)

    def test_meeting_update_403_for_viewer(self, meeting, make_user):
        c = Client()
        viewer = make_user("v_up", groups=["Viewer"])
        self._login(c, viewer)
        url = reverse("meetings:meeting_update", args=[meeting.pk])
        resp = c.get(url)
        assert resp.status_code == 403

    def test_meeting_update_403_when_published(self, meeting, make_user):
        mgmt = make_user("mgmt_p403", groups=["Management Administrator"])
        from apps.meetings.services import transition_meeting

        transition_meeting(meeting, STATUS_OPEN_UPDATES, by_user=mgmt)
        transition_meeting(meeting, STATUS_AGENDA_FINALIZED, by_user=mgmt)
        transition_meeting(meeting, "IN_PROGRESS", by_user=mgmt)
        transition_meeting(meeting, STATUS_FOR_REVIEW, by_user=mgmt)
        transition_meeting(meeting, STATUS_APPROVED, by_user=mgmt)
        transition_meeting(meeting, STATUS_PUBLISHED, by_user=mgmt)
        meeting.refresh_from_db()
        c = Client()
        chair = meeting.chair
        self._login(c, chair)
        url = reverse("meetings:meeting_update", args=[meeting.pk])
        resp = c.get(url)
        assert resp.status_code == 403
        resp_post = c.post(url, {"title": "Hacked title"})
        assert resp_post.status_code == 403

    def test_meeting_archive_403_for_chair(self, meeting, make_user):
        c = Client()
        chair = make_user("ch_ar", groups=["Meeting Chairperson"])
        self._login(c, chair)
        url = reverse("meetings:meeting_archive", args=[meeting.pk])
        resp = c.post(url)
        assert resp.status_code in (302, 403)

    def test_agenda_item_create_403_for_viewer(self, meeting, make_user):
        c = Client()
        viewer = make_user("v_ag", groups=["Viewer"])
        self._login(c, viewer)
        url = reverse("meetings:agenda_item_create", args=[meeting.pk])
        resp = c.get(url)
        assert resp.status_code in (302, 403)

    def test_attendance_403_for_viewer(self, meeting, make_user):
        c = Client()
        viewer = make_user("v_at", groups=["Viewer"])
        self._login(c, viewer)
        url = reverse("meetings:meeting_attendance", args=[meeting.pk])
        resp = c.get(url)
        assert resp.status_code == 403


@pytest.mark.django_db
class TestConfidentialRedactionInResponse:
    def test_detail_hides_confidential_text_for_viewer(self, meeting, make_user, dept):
        cat = AgendaCategory.objects.create(name="General")
        AgendaItem.objects.create(
            meeting=meeting,
            order=1,
            title="Public Title",
            discussion="Public discussion",
            is_confidential=False,
            category=cat,
            item_status=ITEM_STATUS_TO_BE_DISCUSSED,
        )
        AgendaItem.objects.create(
            meeting=meeting,
            order=2,
            title="Confidential Title",
            discussion="Sensitive strategy discussion",
            is_confidential=True,
            category=cat,
            item_status=ITEM_STATUS_TO_BE_DISCUSSED,
        )
        c = Client()
        viewer = make_user("vr_cf", groups=["Viewer"])
        c.force_login(viewer)
        url = reverse("meetings:meeting_detail", args=[meeting.pk])
        resp = c.get(url)
        assert resp.status_code == 200
        content = resp.content.decode()
        assert "Public Title" in content
        assert "[Confidential]" in content
        assert "Sensitive strategy discussion" not in content

    def test_detail_shows_confidential_for_admin(self, meeting, make_user, dept):
        cat = AgendaCategory.objects.create(name="General")
        AgendaItem.objects.create(
            meeting=meeting,
            order=1,
            title="Confidential Title",
            discussion="Sensitive strategy discussion",
            is_confidential=True,
            category=cat,
            item_status=ITEM_STATUS_TO_BE_DISCUSSED,
        )
        c = Client()
        mgmt = make_user("mr_cf", groups=["Management Administrator"])
        c.force_login(mgmt)
        url = reverse("meetings:meeting_detail", args=[meeting.pk])
        resp = c.get(url)
        assert resp.status_code == 200
        content = resp.content.decode()
        assert "Sensitive strategy discussion" in content
