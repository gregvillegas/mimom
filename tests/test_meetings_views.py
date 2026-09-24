from datetime import timedelta

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Department, User
from apps.meetings.models import (
    ITEM_STATUS_TO_BE_DISCUSSED,
    STATUS_AGENDA_FINALIZED,
    STATUS_APPROVED,
    STATUS_DRAFT,
    STATUS_FOR_REVIEW,
    STATUS_IN_PROGRESS,
    STATUS_OPEN_UPDATES,
    STATUS_PUBLISHED,
    STATUS_RETURNED_FOR_CORRECTION,
    AgendaCategory,
    AgendaItem,
    Meeting,
    MeetingStatusHistory,
    MeetingType,
)


@pytest.fixture
def mtype(db):
    return MeetingType.objects.create(name="Weekly Ops", code="OPSW")


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
def mgmt_user(make_user):
    return make_user("mgmt_ev", groups=["Management Administrator"])


@pytest.fixture
def client_logged(db, mgmt_user):
    c = Client()
    c.force_login(mgmt_user)
    return c


def _dt_str(dt):
    return dt.strftime("%Y-%m-%dT%H:%M")


@pytest.mark.django_db(transaction=True)
class TestCreateMeeting:
    def test_create_meeting_happy_path(self, client_logged, mtype, dept, mgmt_user):
        start = timezone.now() + timedelta(days=7)
        end = start + timedelta(hours=2)
        url = reverse("meetings:meeting_create")
        payload = {
            "type": mtype.pk,
            "title": "Q3 Engineering Review",
            "description": "Review OKR progress",
            "start_at": _dt_str(start),
            "end_at": _dt_str(end),
            "location": "Room 404",
            "department": dept.pk,
            "chair": mgmt_user.pk,
            "notes": "Bring laptops",
        }
        resp = client_logged.post(url, payload, follow=True)
        assert resp.status_code == 200
        m = Meeting.objects.filter(title="Q3 Engineering Review").first()
        assert m is not None
        assert m.type_id == mtype.pk
        assert m.reference.startswith("OPSW-")
        assert m.status == STATUS_DRAFT
        assert m.created_by_id == mgmt_user.pk
        assert m.chair_id == mgmt_user.pk

    def test_create_meeting_end_before_start_returns_form_error(
        self, client_logged, mtype, dept, mgmt_user
    ):
        start = timezone.now() + timedelta(days=7)
        end = start - timedelta(minutes=1)
        url = reverse("meetings:meeting_create")
        payload = {
            "type": mtype.pk,
            "title": "Bad timing",
            "start_at": _dt_str(start),
            "end_at": _dt_str(end),
            "chair": mgmt_user.pk,
        }
        resp = client_logged.post(url, payload)
        assert resp.status_code == 200
        assert Meeting.objects.filter(title="Bad timing").count() == 0


@pytest.mark.django_db(transaction=True)
class TestEndToEndLifecycle:
    def _make_meeting(self, mtype, dept, make_user):
        chair = make_user("chair_e2e", groups=["Meeting Chairperson"])
        start = timezone.now() + timedelta(days=5)
        return Meeting.objects.create(
            type=mtype,
            title="E2E Lifecycle Meeting",
            start_at=start,
            end_at=start + timedelta(hours=2),
            location="Main Hall",
            department=dept,
            chair=chair,
            created_by=chair,
        )

    def test_transitions_through_lifecycle_via_post(self, mtype, dept, make_user, mgmt_user):
        meeting = self._make_meeting(mtype, dept, make_user)
        c = Client()
        c.force_login(mgmt_user)
        steps = [
            (STATUS_OPEN_UPDATES, ""),
            (STATUS_AGENDA_FINALIZED, ""),
            (STATUS_IN_PROGRESS, ""),
            (STATUS_FOR_REVIEW, ""),
            (STATUS_APPROVED, ""),
            (STATUS_PUBLISHED, ""),
        ]
        for target, reason in steps:
            url = reverse("meetings:meeting_transition", args=[meeting.pk])
            resp = c.post(url, {"target_status": target, "reason": reason}, follow=True)
            assert resp.status_code == 200, f"step {target} failed"
            meeting.refresh_from_db()
            assert meeting.status == target
        history = MeetingStatusHistory.objects.filter(meeting=meeting).count()
        assert history == len(steps)

    def test_published_meeting_edit_returns_403(self, mtype, dept, make_user, mgmt_user):
        meeting = self._make_meeting(mtype, dept, make_user)
        from apps.meetings.services import transition_meeting

        transition_meeting(meeting, STATUS_OPEN_UPDATES, by_user=mgmt_user)
        transition_meeting(meeting, STATUS_AGENDA_FINALIZED, by_user=mgmt_user)
        transition_meeting(meeting, STATUS_IN_PROGRESS, by_user=mgmt_user)
        transition_meeting(meeting, STATUS_FOR_REVIEW, by_user=mgmt_user)
        transition_meeting(meeting, STATUS_APPROVED, by_user=mgmt_user)
        transition_meeting(meeting, STATUS_PUBLISHED, by_user=mgmt_user)
        meeting.refresh_from_db()
        c = Client()
        c.force_login(mgmt_user)
        update_url = reverse("meetings:meeting_update", args=[meeting.pk])
        resp = c.post(
            update_url,
            {
                "type": mtype.pk,
                "title": "HACKED",
                "start_at": _dt_str(meeting.start_at),
                "end_at": _dt_str(meeting.end_at),
            },
        )
        assert resp.status_code == 403
        meeting.refresh_from_db()
        assert meeting.title != "HACKED"

    def test_returned_for_correction_flow(self, mtype, dept, make_user, mgmt_user):
        meeting = self._make_meeting(mtype, dept, make_user)
        from apps.meetings.services import transition_meeting

        transition_meeting(meeting, STATUS_OPEN_UPDATES, by_user=mgmt_user)
        transition_meeting(meeting, STATUS_AGENDA_FINALIZED, by_user=mgmt_user)
        transition_meeting(meeting, STATUS_IN_PROGRESS, by_user=mgmt_user)
        transition_meeting(meeting, STATUS_FOR_REVIEW, by_user=mgmt_user)
        c = Client()
        c.force_login(mgmt_user)
        trans_url = reverse("meetings:meeting_transition", args=[meeting.pk])
        resp = c.post(
            trans_url,
            {
                "target_status": STATUS_RETURNED_FOR_CORRECTION,
                "reason": "Missing decisions in section 3",
            },
            follow=True,
        )
        assert resp.status_code == 200
        meeting.refresh_from_db()
        assert meeting.status == STATUS_RETURNED_FOR_CORRECTION

    def test_returned_without_reason_rejected(self, mtype, dept, make_user, mgmt_user):
        meeting = self._make_meeting(mtype, dept, make_user)
        from apps.meetings.services import transition_meeting

        transition_meeting(meeting, STATUS_OPEN_UPDATES, by_user=mgmt_user)
        transition_meeting(meeting, STATUS_AGENDA_FINALIZED, by_user=mgmt_user)
        transition_meeting(meeting, STATUS_IN_PROGRESS, by_user=mgmt_user)
        transition_meeting(meeting, STATUS_FOR_REVIEW, by_user=mgmt_user)
        c = Client()
        c.force_login(mgmt_user)
        trans_url = reverse("meetings:meeting_transition", args=[meeting.pk])
        c.post(
            trans_url,
            {"target_status": STATUS_RETURNED_FOR_CORRECTION, "reason": ""},
            follow=True,
        )
        meeting.refresh_from_db()
        assert meeting.status == STATUS_FOR_REVIEW


@pytest.mark.django_db(transaction=True)
class TestAttendanceAndAgenda:
    def _make_meeting(self, mtype, dept, make_user):
        chair = make_user("chair_aa", groups=["Meeting Chairperson"])
        start = timezone.now() + timedelta(days=4)
        return Meeting.objects.create(
            type=mtype,
            title="Attendance & Agenda Test",
            start_at=start,
            end_at=start + timedelta(hours=1),
            location="R5",
            department=dept,
            chair=chair,
            created_by=chair,
        )

    def test_save_attendance_rows(self, mtype, dept, make_user, mgmt_user):
        meeting = self._make_meeting(mtype, dept, make_user)
        u1 = make_user("u_aa1", groups=["Department Contributor"])
        u2 = make_user("u_aa2", groups=["Department Contributor"])
        c = Client()
        c.force_login(mgmt_user)
        url = reverse("meetings:meeting_attendance", args=[meeting.pk])
        get_resp = c.get(url)
        assert get_resp.status_code == 200
        formset = get_resp.context["formset"]
        p = formset.prefix
        payload = {
            f"{p}-INITIAL_FORMS": "0",
            f"{p}-TOTAL_FORMS": "2",
            f"{p}-MIN_NUM_FORMS": "0",
            f"{p}-MAX_NUM_FORMS": "1000",
            f"{p}-0-user": u1.pk,
            f"{p}-0-is_invited": "on",
            f"{p}-0-rsvp_status": "YES",
            f"{p}-1-user": u2.pk,
            f"{p}-1-is_attended": "on",
            f"{p}-1-rsvp_status": "PENDING",
        }
        resp = c.post(url, payload, follow=True)
        assert resp.status_code == 200
        rows = list(meeting.attendance.order_by("user__username"))
        assert len(rows) == 2
        assert rows[0].is_invited is True
        assert rows[0].is_attended is False
        assert rows[1].is_invited is False
        assert rows[1].is_attended is True

    def test_agenda_item_create_and_reorder(self, mtype, dept, make_user, mgmt_user):
        meeting = self._make_meeting(mtype, dept, make_user)
        cat = AgendaCategory.objects.create(name="Standard", order=1)
        c = Client()
        c.force_login(mgmt_user)
        create_url = reverse("meetings:agenda_item_create", args=[meeting.pk])
        titles = ["Welcome", "Reports", "Actions", "AOB"]
        created_items = []
        for i, title in enumerate(titles):
            resp = c.post(
                create_url,
                {
                    "title": title,
                    "category": cat.pk,
                    "order": i,
                    "item_status": ITEM_STATUS_TO_BE_DISCUSSED,
                },
                follow=True,
            )
            assert resp.status_code == 200, f"failed for {title}"
            it = AgendaItem.objects.filter(meeting=meeting, title=title).first()
            assert it is not None
            created_items.append(it)
        actual = list(
            AgendaItem.objects.filter(meeting=meeting)
            .order_by("order")
            .values_list("title", flat=True)
        )
        assert actual == titles
        reordered = list(reversed(created_items))
        pks = [str(i.pk) for i in reordered]
        order_url = reverse("meetings:agenda_item_order", args=[meeting.pk])
        c.post(order_url, {"item_order": ",".join(pks)}, follow=True)
        new_order = list(
            AgendaItem.objects.filter(meeting=meeting)
            .order_by("order")
            .values_list("title", flat=True)
        )
        assert new_order == list(reversed(titles))


@pytest.mark.django_db(transaction=True)
class TestMeetingListAndDetail:
    def test_list_renders_with_filters(self, client_logged, mtype, dept, make_user):
        chair = make_user("ch_li", groups=["Meeting Chairperson"])
        for i in range(3):
            start = timezone.now() + timedelta(days=i + 1)
            Meeting.objects.create(
                type=mtype,
                title=f"List Meeting {i}",
                start_at=start,
                end_at=start + timedelta(hours=1),
                department=dept,
                chair=chair,
                created_by=chair,
            )
        url = reverse("meetings:meeting_list")
        resp = client_logged.get(url + "?q=List+Meeting")
        assert resp.status_code == 200
        page = resp.content.decode()
        assert "List Meeting 0" in page
        assert "List Meeting 1" in page

    def test_list_calendar_view(self, client_logged, mtype, dept, make_user):
        chair = make_user("ch_cal", groups=["Meeting Chairperson"])
        start = timezone.now() + timedelta(days=2)
        Meeting.objects.create(
            type=mtype,
            title="Calendar Meet",
            start_at=start,
            end_at=start + timedelta(hours=1),
            department=dept,
            chair=chair,
            created_by=chair,
        )
        url = reverse("meetings:meeting_list")
        resp = client_logged.get(url + "?view=calendar")
        assert resp.status_code == 200
        assert "calendar_cells" in resp.context
        assert len(resp.context["calendar_cells"]) == 42

    def test_detail_renders_tabs(self, mtype, dept, make_user, client_logged):
        chair = make_user("ch_dt", groups=["Meeting Chairperson"])
        start = timezone.now() + timedelta(days=1)
        m = Meeting.objects.create(
            type=mtype,
            title="Detail Test",
            start_at=start,
            end_at=start + timedelta(hours=1),
            department=dept,
            chair=chair,
            created_by=chair,
        )
        url = reverse("meetings:meeting_detail", args=[m.pk])
        resp = client_logged.get(url)
        assert resp.status_code == 200
        content = resp.content.decode()
        assert "Summary" in content
        assert "Agenda" in content
        assert "Attendance" in content


@pytest.mark.django_db(transaction=True)
class TestCarryForward:
    def test_carry_forward_post_creates_items(self, mtype, dept, make_user, mgmt_user):
        chair = make_user("ch_cf", groups=["Meeting Chairperson"])
        start_src = timezone.now() + timedelta(days=1)
        src = Meeting.objects.create(
            type=mtype,
            title="Source CF",
            start_at=start_src,
            end_at=start_src + timedelta(hours=1),
            department=dept,
            chair=chair,
            created_by=chair,
        )
        start_tgt = start_src + timedelta(days=7)
        tgt = Meeting.objects.create(
            type=mtype,
            title="Target CF",
            start_at=start_tgt,
            end_at=start_tgt + timedelta(hours=1),
            department=dept,
            chair=chair,
            created_by=chair,
        )
        cat = AgendaCategory.objects.create(name="Old")
        item = AgendaItem.objects.create(
            meeting=src,
            order=0,
            title="Carry me",
            category=cat,
            item_status=ITEM_STATUS_TO_BE_DISCUSSED,
            decision="Decided X",
        )
        c = Client()
        c.force_login(mgmt_user)
        url = reverse("meetings:meeting_carry_forward", args=[tgt.pk])
        resp = c.post(
            url,
            {"source_meeting": str(src.pk), "item_ids": str(item.pk)},
            follow=True,
        )
        assert resp.status_code == 200
        copied = AgendaItem.objects.filter(meeting=tgt).first()
        assert copied is not None
        assert copied.title == "Carry me"
        assert copied.decision == ""
        assert copied.carried_forward_from_id == item.pk


@pytest.mark.django_db(transaction=True)
class TestDashboardCounts:
    def test_dashboard_counts_helper(self, mtype, dept, make_user, mgmt_user):
        from apps.meetings.views import dashboard_summary_counts

        chair = make_user("ch_dc", groups=["Meeting Chairperson"])
        start = timezone.now() + timedelta(days=1)
        for _ in range(2):
            Meeting.objects.create(
                type=mtype,
                title="Dash",
                start_at=start,
                end_at=start + timedelta(hours=1),
                department=dept,
                chair=chair,
                created_by=chair,
            )
        counts = dashboard_summary_counts()
        assert counts["meeting_counts"][STATUS_DRAFT] == 2
        assert counts["meeting_total"] == 2
        assert "upcoming_meetings" in counts
