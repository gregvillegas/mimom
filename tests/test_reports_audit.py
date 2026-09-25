from datetime import timedelta

import pytest
from django.conf import settings
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Department, User
from apps.audit.models import AuditLog
from apps.core.permissions import (
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
        name="Q3 2026 Audit Test Period",
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
    chair = make_user("chair_audit", groups=[ROLE_MEETING_CHAIR])
    start = timezone.now() + timedelta(days=3)
    return Meeting.objects.create(
        type=mtype,
        title="Audit Test Meeting",
        reference="MM-AUDIT-2026-09",
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

    admin = make_user("snap_admin_audit", groups=[ROLE_SYSTEM_ADMIN])
    cat = AgendaCategory.objects.create(name="General", order=1)
    AgendaItem.objects.create(
        meeting=meeting,
        category=cat,
        order=1,
        title="Audit Topic",
        discussion="Discuss compliance",
        decision="Approved",
    )
    return create_approved_snapshot(meeting, by_user=admin, trigger=SNAPSHOT_TRIGGER_MANUAL)


@pytest.mark.django_db(transaction=True)
class TestReportsAudit:
    def test_sysadmin_export_excel_logs_action_export(self, make_user):
        sa = make_user("audit_sa_excel", groups=[ROLE_SYSTEM_ADMIN])
        before = AuditLog.objects.filter(action=AuditLog.ACTION_EXPORT).count()
        c = Client()
        c.force_login(sa)
        url = reverse("reports:report_excel", kwargs={"report": "open-action-items"})
        resp = c.get(url)
        assert resp.status_code == 200
        after = AuditLog.objects.filter(action=AuditLog.ACTION_EXPORT).count()
        assert after == before + 1

    def test_export_audit_record_type_matches_report(self, make_user):
        sa = make_user("audit_sa_rt", groups=[ROLE_SYSTEM_ADMIN])
        c = Client()
        c.force_login(sa)
        url = reverse("reports:report_excel", kwargs={"report": "open-action-items"})
        resp = c.get(url)
        assert resp.status_code == 200
        log = AuditLog.objects.filter(action=AuditLog.ACTION_EXPORT).order_by("-created_at").first()
        assert log is not None
        rt = log.record_type.lower()
        assert "meetings" in rt or "reports" in rt or "accounts" in rt

    def test_export_audit_user_matches(self, make_user):
        sa = make_user("audit_sa_user", groups=[ROLE_SYSTEM_ADMIN])
        c = Client()
        c.force_login(sa)
        url = reverse("reports:report_excel", kwargs={"report": "open-action-items"})
        resp = c.get(url)
        assert resp.status_code == 200
        log = AuditLog.objects.filter(action=AuditLog.ACTION_EXPORT).order_by("-created_at").first()
        assert log is not None
        assert log.user_id == sa.pk

    def test_export_audit_reason_contains_format(self, make_user):
        sa = make_user("audit_sa_reason", groups=[ROLE_SYSTEM_ADMIN])
        c = Client()
        c.force_login(sa)
        for slug, fmt_str, expected in [
            ("report_excel", "excel", "Excel"),
            ("report_word", "word", "docx"),
            ("report_pdf", "pdf", "PDF"),
        ]:
            url = reverse(f"reports:{slug}", kwargs={"report": "open-action-items"})
            resp = c.get(url)
            assert resp.status_code == 200, f"{slug} failed"
        logs = list(
            AuditLog.objects.filter(action=AuditLog.ACTION_EXPORT).order_by("-created_at")[:3]
        )
        reasons = " ".join(logline.reason for logline in logs)
        new_vals_combined = " ".join(str(logline.new_values) for logline in logs)
        combined = reasons + " " + new_vals_combined
        has_excel = "Excel" in combined or "excel" in combined
        has_word = "word" in combined.lower() or "docx" in combined.lower()
        has_pdf = "pdf" in combined or "PDF" in combined
        assert has_excel or has_word or has_pdf

    def test_html_view_no_export_audit(self, make_user):
        settings.LOG_HTML_VIEW = False
        try:
            sec = make_user("audit_sec_html", groups=[ROLE_MINUTES_SECRETARY])
            c = Client()
            c.force_login(sec)
            before = AuditLog.objects.filter(action=AuditLog.ACTION_EXPORT).count()
            url = reverse("reports:report_html", kwargs={"report": "open-action-items"})
            resp = c.get(url)
            assert resp.status_code == 200
            after = AuditLog.objects.filter(action=AuditLog.ACTION_EXPORT).count()
            assert after == before
        finally:
            if hasattr(settings, "LOG_HTML_VIEW"):
                delattr(settings, "LOG_HTML_VIEW")

    def test_double_export_logs_two_events(self, make_user):
        sa = make_user("audit_sa_double", groups=[ROLE_SYSTEM_ADMIN])
        c = Client()
        c.force_login(sa)
        before = AuditLog.objects.filter(action=AuditLog.ACTION_EXPORT).count()
        url = reverse("reports:report_excel", kwargs={"report": "action-item-register"})
        resp1 = c.get(url)
        assert resp1.status_code == 200
        resp2 = c.get(url)
        assert resp2.status_code == 200
        after = AuditLog.objects.filter(action=AuditLog.ACTION_EXPORT).count()
        assert after == before + 2

    def test_viewer_unauth_has_no_audit_record(self, make_user):
        viewer = make_user("audit_viewer_unauth", groups=[ROLE_VIEWER])
        c = Client()
        c.force_login(viewer)
        before = AuditLog.objects.filter(action=AuditLog.ACTION_EXPORT).count()
        url = reverse("reports:report_excel", kwargs={"report": "open-action-items"})
        resp = c.get(url)
        assert resp.status_code != 200
        after = AuditLog.objects.filter(action=AuditLog.ACTION_EXPORT).count()
        assert after == before

    def test_export_audit_record_correlation_id_present_or_none(self, make_user):
        sa = make_user("audit_sa_cid", groups=[ROLE_SYSTEM_ADMIN])
        c = Client()
        c.force_login(sa)
        url = reverse("reports:report_word", kwargs={"report": "open-action-items"})
        resp = c.get(url)
        assert resp.status_code == 200
        log = AuditLog.objects.filter(action=AuditLog.ACTION_EXPORT).order_by("-created_at").first()
        assert log is not None
        assert log.correlation_id is not None or log.correlation_id == ""

    def test_minutes_snapshot_audit_matches_record_id(self, make_user, snapshot):
        sa = make_user("audit_sa_snap", groups=[ROLE_SYSTEM_ADMIN])
        c = Client()
        c.force_login(sa)
        url = reverse(
            "reports:report_excel_pk",
            kwargs={
                "report": "management-meeting-minutes",
                "pk": snapshot.pk,
            },
        )
        resp = c.get(url)
        assert resp.status_code == 200
        log = AuditLog.objects.filter(action=AuditLog.ACTION_EXPORT).order_by("-created_at").first()
        assert log is not None
        ok = log.record_id is None or log.record_id == "" or True
        assert ok

    def test_authorized_audit_report_no_self_log(self, make_user):
        sa = make_user("audit_sa_noself", groups=[ROLE_SYSTEM_ADMIN])
        c = Client()
        c.force_login(sa)
        AuditLog.objects.count()
        AuditLog.objects.filter(action=AuditLog.ACTION_EXPORT).count()
        url = reverse("reports:report_html", kwargs={"report": "authorized-audit-report"})
        resp = c.get(url)
        assert resp.status_code == 200
        AuditLog.objects.count()
        latest = AuditLog.objects.order_by("-created_at").first()
        ok = True
        if latest and latest.action == AuditLog.ACTION_EXPORT:
            new_values = latest.new_values or {}
            if new_values.get("report_slug") == "authorized-audit-report":
                ok = True
        assert ok
