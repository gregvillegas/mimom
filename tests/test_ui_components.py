import pytest
from django.contrib.auth.models import Group
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Department, User
from apps.action_items.models import ActionItem, STATUS_OPEN
from apps.meetings.models import Meeting, MeetingType


@pytest.fixture
def make_user(db):
    def _make(username, groups=None, **extra):
        email = extra.pop("email", None) or f"{username}@example.com"
        u = User.objects.create_user(
            username=username, email=email, password="pw-1234!-Strong", **extra
        )
        if groups:
            for n in groups:
                g, _ = Group.objects.get_or_create(name=n)
                u.groups.add(g)
        return u

    return _make


@pytest.fixture
def sysadmin(make_user):
    return make_user("sys_admin_ui", groups=["System Administrator"])


@pytest.fixture
def viewer(make_user):
    return make_user("viewer_ui", groups=["Viewer"])


@pytest.fixture
def dept(db):
    return Department.objects.create(name="Operations", code="OPS")


@pytest.fixture
def mtype(db):
    return MeetingType.objects.create(name="Weekly Ops", code="OPSW")


@pytest.mark.django_db
def test_dashboard_kpi_cards_reponsive_classes_SysAdmin(sysadmin):
    c = Client()
    c.force_login(sysadmin)
    resp = c.get(reverse("home"))
    assert resp.status_code == 200
    content = resp.content.decode("utf-8")
    assert "card card-hover" in content
    assert "card-stats" in content
    assert "col-sm-12 col-md-6 col-lg-3" in content


@pytest.mark.django_db
def test_messages_toast_on_login_success_feedback(viewer):
    c = Client()
    resp = c.post(
        reverse("login"),
        {"username": viewer.username, "password": "pw-1234!-Strong"},
        follow=True,
    )
    assert resp.status_code == 200
    content = resp.content.decode("utf-8")
    assert (
        "IntranetUI.showToast" in content
        or "toast-container" in content
        or "bootstrap.Toast" in content
    )


@pytest.mark.django_db
def test_forms_sticky_submit_bar_on_meeting_form(sysadmin, mtype):
    c = Client()
    c.force_login(sysadmin)
    resp = c.get(reverse("meetings:meeting_create"))
    assert resp.status_code == 200
    content = resp.content.decode("utf-8")
    assert "sticky-submit-bar" in content
    assert 'type="submit"' in content


@pytest.mark.django_db
def test_forms_alerts_container_present_for_non_field_errors(sysadmin, mtype, dept):
    c = Client()
    c.force_login(sysadmin)
    resp = c.post(
        reverse("meetings:meeting_create"),
        {
            "type": mtype.pk,
            "title": "",
            "start_at_0": "",
            "start_at_1": "",
        },
    )
    assert resp.status_code == 200
    content = resp.content.decode("utf-8")
    assert (
        "alerts_container" in content
        or "alert alert-danger validation-summary" in content
        or 'role="alert"' in content
    )


@pytest.mark.django_db
def test_empty_state_appears_actionitem_list(viewer):
    assert ActionItem.objects.count() == 0
    c = Client()
    c.force_login(viewer)
    resp = c.get(reverse("action_items:actionitem_list"))
    assert resp.status_code == 200
    content = resp.content.decode("utf-8")
    assert "empty-state" in content or "empty_state" in content


@pytest.mark.django_db
def test_tables_scrollable_wrap_meeting_list(sysadmin, mtype, dept):
    c = Client()
    c.force_login(sysadmin)
    resp = c.get(reverse("meetings:meeting_list"))
    assert resp.status_code == 200
    content = resp.content.decode("utf-8")
    assert "scrollable-table-wrap" in content
    assert '<caption class="visually-hidden"' in content
    assert "sticky-thead" in content


@pytest.mark.django_db
def test_tables_data_label_attr_td_meeting_list(sysadmin, mtype, dept):
    start = timezone.now() + timezone.timedelta(days=7)
    Meeting.objects.create(
        type=mtype,
        title="Label Test Meeting",
        start_at=start,
        end_at=start + timezone.timedelta(hours=2),
        department=dept,
    )
    c = Client()
    c.force_login(sysadmin)
    resp = c.get(reverse("meetings:meeting_list"))
    assert resp.status_code == 200
    content = resp.content.decode("utf-8")
    assert 'data-label="Reference"' in content
    assert 'data-label="Title"' in content


@pytest.mark.django_db
def test_search_filter_panel_meeting_list_has_reset_button(sysadmin, mtype, dept):
    c = Client()
    c.force_login(sysadmin)
    resp = c.get(reverse("meetings:meeting_list") + "?q=abc")
    assert resp.status_code == 200
    content = resp.content.decode("utf-8")
    assert "filter-form-card" in content
    assert "reset" in content.lower()


@pytest.mark.django_db
def test_pagination_aria_label_exists_actionitem_list(sysadmin, dept):
    for i in range(27):
        ActionItem.objects.create(
            title=f"Paginate AI {i}",
            status=STATUS_OPEN,
            due_date=timezone.now().date() + timezone.timedelta(days=i + 1),
            department=dept,
        )
    c = Client()
    c.force_login(sysadmin)
    resp = c.get(reverse("action_items:actionitem_list"))
    assert resp.status_code == 200
    content = resp.content.decode("utf-8")
    assert (
        'aria-label="Action item pagination"' in content
        or "pagination-lg" in content
    )


@pytest.mark.django_db
def test_sidebar_collapse_button_present_desktop(sysadmin):
    c = Client()
    c.force_login(sysadmin)
    resp = c.get(reverse("home"))
    assert resp.status_code == 200
    content = resp.content.decode("utf-8")
    assert "sidebar-collapse-btn" in content
    assert "data-intranet-sidebar-collapse" in content
    assert "aria-expanded" in content


@pytest.mark.django_db
def test_confirm_dialog_modal_in_base_html(sysadmin):
    c = Client()
    c.force_login(sysadmin)
    resp = c.get(reverse("home"))
    assert resp.status_code == 200
    content = resp.content.decode("utf-8")
    assert 'id="confirmDialogModal"' in content
    assert 'aria-labelledby="confirmDialogModalLabel"' in content
