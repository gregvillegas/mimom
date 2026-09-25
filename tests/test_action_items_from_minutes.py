from datetime import timedelta

import pytest
from django.db import IntegrityError
from django.utils import timezone

from apps.accounts.models import Department, User
from apps.action_items.models import ActionItem
from apps.meetings.models import (
    ActionItemLink,
    AgendaCategory,
    AgendaItem,
    Meeting,
    MeetingType,
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
    chair = make_user("chair_ai", groups=["Meeting Chairperson"])
    start = timezone.now() + timedelta(days=2)
    m = Meeting.objects.create(
        type=mtype,
        title="AI Test Meeting",
        start_at=start,
        end_at=start + timedelta(hours=2),
        location="Room 500",
        department=dept,
        chair=chair,
        created_by=chair,
    )
    cat = AgendaCategory.objects.create(name="Discuss", order=1)
    ai = AgendaItem.objects.create(
        meeting=m,
        category=cat,
        order=1,
        title="Project X Review",
        department=dept,
    )
    return m


@pytest.mark.django_db
def test_action_item_created_via_form_save_action_item_link_created(meeting, make_user, client):
    secretary = make_user("sec_ai1", groups=["Minutes Secretary"])
    agenda_item = meeting.agenda_items.first()
    client.force_login(secretary)
    from django.urls import reverse

    url = reverse("meetings:action_item_from_minutes_create", args=[meeting.pk])
    url_with_agenda = f"{url}?agenda_item={agenda_item.pk}"
    resp = client.get(url_with_agenda)
    assert resp.status_code == 200
    owner = make_user("owner_ai1", groups=["Department Contributor"])
    post_data = {
        "title": "Follow up on Project X action",
        "description": "Need to send update email to stakeholders",
        "owner": owner.pk,
        "priority": "MED",
        "due_date": (timezone.now() + timedelta(days=7)).date().isoformat(),
        "agenda_item": str(agenda_item.pk),
    }
    before_action_count = ActionItem.objects.count()
    before_link_count = ActionItemLink.objects.count()
    resp_post = client.post(url_with_agenda, post_data)
    assert resp_post.status_code == 302
    after_action_count = ActionItem.objects.count()
    after_link_count = ActionItemLink.objects.count()
    assert after_action_count > before_action_count
    assert after_link_count > before_link_count


@pytest.mark.django_db
def test_action_item_source_agenda_item_fk_set(meeting, make_user, client):
    secretary = make_user("sec_ai2", groups=["Minutes Secretary"])
    agenda_item = meeting.agenda_items.first()
    owner = make_user("owner_ai2", groups=["Department Contributor"])
    client.force_login(secretary)
    from django.urls import reverse

    url = reverse("meetings:action_item_from_minutes_create", args=[meeting.pk])
    url_with_agenda = f"{url}?agenda_item={agenda_item.pk}"
    post_data = {
        "title": "Source FK check item",
        "description": "Verify source_agenda_item is set",
        "owner": owner.pk,
        "priority": "MED",
        "due_date": (timezone.now() + timedelta(days=5)).date().isoformat(),
        "agenda_item": str(agenda_item.pk),
    }
    client.post(url_with_agenda, post_data)
    new_action = ActionItem.objects.filter(title="Source FK check item").first()
    assert new_action is not None
    assert new_action.source_agenda_item_id == agenda_item.pk


@pytest.mark.django_db
def test_owner_dept_prefills(meeting, make_user):
    secretary = make_user("sec_ai3", groups=["Minutes Secretary"])
    agenda_item = meeting.agenda_items.first()
    owner = make_user("owner_ai3", groups=["Department Contributor"])
    agenda_item.owner = owner
    agenda_item.department = meeting.department
    agenda_item.save()
    from apps.meetings.forms import ActionItemCreateFromMinutesForm

    form = ActionItemCreateFromMinutesForm(
        source_meeting=meeting,
        source_agenda_item=agenda_item,
    )
    owner_initial = form.initial.get("owner")
    assert owner_initial is not None or form.instance.department_id is not None


@pytest.mark.django_db
def test_source_meeting_set(meeting, make_user, client):
    secretary = make_user("sec_ai4", groups=["Minutes Secretary"])
    agenda_item = meeting.agenda_items.first()
    owner = make_user("owner_ai4", groups=["Department Contributor"])
    client.force_login(secretary)
    from django.urls import reverse

    url = reverse("meetings:action_item_from_minutes_create", args=[meeting.pk])
    url_with_agenda = f"{url}?agenda_item={agenda_item.pk}"
    post_data = {
        "title": "Source Meeting Verify",
        "description": "Check source_meeting FK",
        "owner": owner.pk,
        "priority": "MED",
        "due_date": (timezone.now() + timedelta(days=3)).date().isoformat(),
        "agenda_item": str(agenda_item.pk),
    }
    client.post(url_with_agenda, post_data)
    new_action = ActionItem.objects.filter(title="Source Meeting Verify").first()
    assert new_action is not None
    assert new_action.source_meeting_id == meeting.pk


@pytest.mark.django_db
def test_after_create_redirects_to_minutes_editor(meeting, make_user, client):
    secretary = make_user("sec_ai5", groups=["Minutes Secretary"])
    agenda_item = meeting.agenda_items.first()
    owner = make_user("owner_ai5", groups=["Department Contributor"])
    client.force_login(secretary)
    from django.urls import reverse

    url = reverse("meetings:action_item_from_minutes_create", args=[meeting.pk])
    url_with_agenda = f"{url}?agenda_item={agenda_item.pk}"
    post_data = {
        "title": "Redirect test item",
        "description": "Check redirect after save",
        "owner": owner.pk,
        "priority": "MED",
        "due_date": (timezone.now() + timedelta(days=4)).date().isoformat(),
        "agenda_item": str(agenda_item.pk),
    }
    resp = client.post(url_with_agenda, post_data, follow=False)
    assert resp.status_code == 302
    redirect_target = resp.get("Location", "") or resp.url
    assert "minutes-editor" in redirect_target or "minutes_editor" in redirect_target


@pytest.mark.django_db
def test_invalid_form_shows_errors(meeting, make_user, client):
    secretary = make_user("sec_ai6", groups=["Minutes Secretary"])
    agenda_item = meeting.agenda_items.first()
    client.force_login(secretary)
    from django.urls import reverse

    url = reverse("meetings:action_item_from_minutes_create", args=[meeting.pk])
    url_with_agenda = f"{url}?agenda_item={agenda_item.pk}"
    post_data = {
        "title": "",
        "description": "",
        "priority": "INVALID_XYZ_12345",
    }
    resp = client.post(url_with_agenda, post_data)
    assert resp.status_code == 200
    assert ActionItem.objects.count() == 0


@pytest.mark.django_db
def test_action_item_link_unique_together(meeting, make_user):
    user = make_user("u_link_unique")
    owner = make_user("owner_unique")
    agenda_item = meeting.agenda_items.first()
    action = ActionItem.objects.create(
        title="Unique Link Test",
        created_by=user,
        owner=owner,
        source_meeting=meeting,
        source_agenda_item=agenda_item,
    )
    ActionItemLink.objects.create(agenda_item=agenda_item, action_item=action, created_by=user)
    with pytest.raises(IntegrityError):
        ActionItemLink.objects.create(agenda_item=agenda_item, action_item=action, created_by=user)


@pytest.mark.django_db
def test_deleting_source_agenda_item_clears_action_item_link_cascade(meeting, make_user):
    user = make_user("u_cascade")
    owner = make_user("owner_cascade")
    agenda_item = meeting.agenda_items.first()
    action = ActionItem.objects.create(
        title="Cascade Delete Test",
        created_by=user,
        owner=owner,
        source_meeting=meeting,
    )
    link = ActionItemLink.objects.create(
        agenda_item=agenda_item, action_item=action, created_by=user
    )
    link_pk = link.pk
    assert ActionItemLink.objects.filter(pk=link_pk).exists()
    agenda_item.delete()
    assert not ActionItemLink.objects.filter(pk=link_pk).exists()
    assert ActionItem.objects.filter(pk=action.pk).exists()
