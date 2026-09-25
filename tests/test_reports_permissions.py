from datetime import timedelta

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Department, User
from apps.core.permissions import (
    ROLE_DEPT_CONTRIBUTOR,
    ROLE_MANAGEMENT_ADMIN,
    ROLE_MEETING_CHAIR,
    ROLE_MINUTES_SECRETARY,
    ROLE_SYSTEM_ADMIN,
    ROLE_VIEWER,
)
from apps.meetings.models import (
    SNAPSHOT_TRIGGER_MANUAL,
    AgendaCategory,
    AgendaItem,
    Meeting,
    MeetingType,
)
from apps.sales_updates.models import DEFAULT_CURRENCY, ReportingPeriod


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
def reporting_period(db):
    start = timezone.now().date()
    end = start + timedelta(days=27)
    cut_off = start + timedelta(days=25)
    return ReportingPeriod.objects.create(
        name="Q3 2026 Test Period",
        start_date=start,
        end_date=end,
        cut_off_date=cut_off,
        weeks_count=4,
        currency=DEFAULT_CURRENCY,
    )


@pytest.fixture
def mtype(db):
    return MeetingType.objects.create(name="Management", code="MGT")


@pytest.fixture
def dept(db):
    return Department.objects.create(name="Executive", code="EXE")


@pytest.fixture
def meeting(mtype, make_user, dept):
    chair = make_user("chair_perm", groups=[ROLE_MEETING_CHAIR])
    start = timezone.now() + timedelta(days=3)
    return Meeting.objects.create(
        type=mtype,
        title="Perms Meeting",
        reference="MM-2026-0924",
        start_at=start,
        end_at=start + timedelta(hours=1),
        location="Room 1",
        department=dept,
        chair=chair,
        created_by=chair,
    )


@pytest.fixture
def snapshot(meeting, make_user):
    from apps.meetings.services import create_approved_snapshot

    admin = make_user("snap_admin", groups=[ROLE_SYSTEM_ADMIN])
    cat = AgendaCategory.objects.create(name="General", order=1)
    AgendaItem.objects.create(
        meeting=meeting,
        category=cat,
        order=1,
        title="Welcome",
        discussion="Intro discussion",
        decision="Approved agenda",
    )
    return create_approved_snapshot(meeting, by_user=admin, trigger=SNAPSHOT_TRIGGER_MANUAL)


@pytest.mark.django_db
class TestReportsPermissions:
    def test_visitor_not_authenticated_redirect(self):
        c = Client()
        url = reverse("reports:index")
        resp = c.get(url)
        assert resp.status_code == 302
        assert "login" in resp.url.lower() and "next=" in resp.url.lower()

    def test_viewer_cannot_export_excel(self, make_user):
        viewer = make_user("viewer_excel", groups=[ROLE_VIEWER])
        c = Client()
        c.force_login(viewer)
        url = reverse("reports:report_excel", kwargs={"report": "open-action-items"})
        resp = c.get(url)
        assert resp.status_code != 200
        assert resp.status_code in (302, 403)

    def test_sysadmin_can_export_excel(self, make_user):
        sa = make_user("sa_excel", groups=[ROLE_SYSTEM_ADMIN])
        c = Client()
        c.force_login(sa)
        url = reverse("reports:report_excel", kwargs={"report": "open-action-items"})
        resp = c.get(url)
        assert resp.status_code == 200
        content = b"".join(resp.streaming_content) if resp.streaming else resp.content
        assert content[:4] == b"PK\x03\x04"

    def test_mgmt_admin_can_export_word(self, make_user):
        ma = make_user("ma_word", groups=[ROLE_MANAGEMENT_ADMIN])
        c = Client()
        c.force_login(ma)
        url = reverse("reports:report_word", kwargs={"report": "open-action-items"})
        resp = c.get(url)
        assert resp.status_code == 200
        assert (
            resp["Content-Type"]
            == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )

    def test_chair_can_view_report_html(self, make_user):
        chair = make_user("chair_html", groups=[ROLE_MEETING_CHAIR])
        c = Client()
        c.force_login(chair)
        url = reverse("reports:report_html", kwargs={"report": "open-action-items"})
        resp = c.get(url)
        assert resp.status_code == 200

    def test_sec_can_view_pdf_inline(self, make_user):
        sec = make_user("sec_pdf", groups=[ROLE_MINUTES_SECRETARY])
        c = Client()
        c.force_login(sec)
        url = reverse("reports:report_pdf", kwargs={"report": "open-action-items"})
        resp = c.get(url)
        assert resp.status_code == 200
        cd = resp.get("Content-Disposition", "")
        assert cd.endswith('.pdf"') or cd.endswith(".pdf")
        assert resp.get("X-Print-As-PDF") == "1"

    def test_deptcontributor_can_view_html_but_not_excel(self, make_user):
        dc = make_user("dc_both", groups=[ROLE_DEPT_CONTRIBUTOR])
        c = Client()
        c.force_login(dc)
        html_url = reverse("reports:report_html", kwargs={"report": "open-action-items"})
        html_resp = c.get(html_url)
        assert html_resp.status_code == 200
        excel_url = reverse("reports:report_excel", kwargs={"report": "open-action-items"})
        excel_resp = c.get(excel_url)
        assert excel_resp.status_code == 403

    def test_viewer_cannot_view_authorized_audit_report(self, make_user):
        viewer = make_user("viewer_audit", groups=[ROLE_VIEWER])
        c = Client()
        c.force_login(viewer)
        url = reverse("reports:report_html", kwargs={"report": "authorized-audit-report"})
        resp = c.get(url)
        assert resp.status_code == 403

    def test_superuser_sees_all_reports(self, make_user):
        su = make_user("su_all_reports", is_superuser=True)
        c = Client()
        c.force_login(su)
        url = reverse("reports:index")
        resp = c.get(url)
        assert resp.status_code == 200
        catalog = resp.context.get("reports_catalog") or {}
        assert len(catalog) == 10

    def test_anonymous_index_302(self):
        c = Client()
        url = reverse("reports:index")
        resp = c.get(url)
        assert resp.status_code == 302
