from django import template
from django.template.defaultfilters import stringfilter

from apps.core.permissions import (
    can_approve_meeting,
    can_archive_meeting,
    can_close_meeting,
    can_complete_actionitem,
    can_create_actionitem,
    can_create_meeting,
    can_create_snapshot,
    can_edit_actionitem,
    can_edit_meeting,
    can_edit_sales_period,
    can_export_reports,
    can_export_sales,
    can_lock_sales_snapshot,
    can_manage_department_assignments,
    can_manage_departments,
    can_manage_positions,
    can_manage_users,
    can_publish_meeting,
    can_reopen_actionitem,
    can_reopen_meeting,
    can_resubmit_minutes,
    can_return_minutes,
    can_submit_minutes,
    can_transition_meeting,
    can_view_actionitem,
    can_view_confidential_items,
    can_view_org,
    can_view_sales_period,
    is_department_contributor,
    is_management_admin,
    is_meeting_chair,
    is_minutes_secretary,
    is_system_admin,
    is_viewer,
)

register = template.Library()


def _user_from_context(context):
    user = context.get("user")
    if user is not None:
        return user
    request = context.get("request")
    return getattr(request, "user", None)


@register.simple_tag(takes_context=True)
def has_role(context, *group_names):
    user = _user_from_context(context)
    if not user or not getattr(user, "is_authenticated", False):
        return False
    return bool(user.has_role(*group_names))


@register.simple_tag(takes_context=True)
def can_manage_users_tag(context):
    user = _user_from_context(context)
    if not user or not getattr(user, "is_authenticated", False):
        return False
    return can_manage_users(user)


@register.simple_tag(takes_context=True)
def can_create_user_tag(context):
    user = _user_from_context(context)
    if not user or not getattr(user, "is_authenticated", False):
        return False
    return can_manage_users(user)


@register.simple_tag(takes_context=True)
def can_manage_department_assignments_tag(context):
    user = _user_from_context(context)
    if not user or not getattr(user, "is_authenticated", False):
        return False
    return can_manage_department_assignments(user)


@register.simple_tag(takes_context=True)
def can_create_meeting_tag(context):
    user = _user_from_context(context)
    if not user or not getattr(user, "is_authenticated", False):
        return False
    return can_create_meeting(user)


@register.simple_tag(takes_context=True)
def can_edit_meeting_tag(context, meeting):
    user = _user_from_context(context)
    if not user or not getattr(user, "is_authenticated", False):
        return False
    return can_edit_meeting(user, meeting)


@register.simple_tag(takes_context=True)
def can_archive_meeting_tag(context, meeting=None):
    user = _user_from_context(context)
    if not user or not getattr(user, "is_authenticated", False):
        return False
    return can_archive_meeting(user, meeting)


@register.simple_tag(takes_context=True)
def can_transition_meeting_tag(context, meeting, target_status=None):
    user = _user_from_context(context)
    if not user or not getattr(user, "is_authenticated", False):
        return False
    return can_transition_meeting(user, meeting, target_status)


@register.simple_tag(takes_context=True)
def can_view_confidential_tag(context, meeting=None, agenda_item=None):
    user = _user_from_context(context)
    if not user or not getattr(user, "is_authenticated", False):
        return False
    return can_view_confidential_items(user, meeting, agenda_item)


@register.simple_tag(takes_context=True)
def can_create_actionitem_tag(context):
    user = _user_from_context(context)
    if not user or not getattr(user, "is_authenticated", False):
        return False
    return can_create_actionitem(user)


@register.simple_tag(takes_context=True)
def can_edit_actionitem_tag(context, action_item):
    user = _user_from_context(context)
    if not user or not getattr(user, "is_authenticated", False):
        return False
    return can_edit_actionitem(user, action_item)


@register.simple_tag(takes_context=True)
def can_complete_actionitem_tag(context, action_item):
    user = _user_from_context(context)
    if not user or not getattr(user, "is_authenticated", False):
        return False
    return can_complete_actionitem(user, action_item)


@register.simple_tag(takes_context=True)
def can_reopen_actionitem_tag(context, action_item=None):
    user = _user_from_context(context)
    if not user or not getattr(user, "is_authenticated", False):
        return False
    return can_reopen_actionitem(user, action_item)


@register.simple_tag(takes_context=True)
def can_view_actionitem_tag(context, action_item):
    user = _user_from_context(context)
    if not user or not getattr(user, "is_authenticated", False):
        return False
    return can_view_actionitem(user, action_item)


@register.simple_tag(takes_context=True)
def can_view_sales_period_tag(context, period=None):
    user = _user_from_context(context)
    if not user or not getattr(user, "is_authenticated", False):
        return False
    return can_view_sales_period(user, period)


@register.simple_tag(takes_context=True)
def can_edit_sales_period_tag(context, period=None):
    user = _user_from_context(context)
    if not user or not getattr(user, "is_authenticated", False):
        return False
    return can_edit_sales_period(user, period)


@register.simple_tag(takes_context=True)
def can_export_sales_tag(context):
    user = _user_from_context(context)
    if not user or not getattr(user, "is_authenticated", False):
        return False
    return can_export_sales(user)


@register.simple_tag(takes_context=True)
def can_lock_sales_snapshot_tag(context, snapshot=None):
    user = _user_from_context(context)
    if not user or not getattr(user, "is_authenticated", False):
        return False
    return can_lock_sales_snapshot(user, snapshot)


@register.simple_tag(takes_context=True)
def can_submit_minutes_tag(context, meeting=None):
    user = _user_from_context(context)
    if not user or not getattr(user, "is_authenticated", False):
        return False
    return can_submit_minutes(user, meeting)


@register.simple_tag(takes_context=True)
def can_return_minutes_tag(context, meeting=None):
    user = _user_from_context(context)
    if not user or not getattr(user, "is_authenticated", False):
        return False
    return can_return_minutes(user, meeting)


@register.simple_tag(takes_context=True)
def can_resubmit_minutes_tag(context, meeting=None):
    user = _user_from_context(context)
    if not user or not getattr(user, "is_authenticated", False):
        return False
    return can_resubmit_minutes(user, meeting)


@register.simple_tag(takes_context=True)
def can_approve_meeting_tag(context, meeting=None):
    user = _user_from_context(context)
    if not user or not getattr(user, "is_authenticated", False):
        return False
    return can_approve_meeting(user, meeting)


@register.simple_tag(takes_context=True)
def can_publish_meeting_tag(context, meeting=None):
    user = _user_from_context(context)
    if not user or not getattr(user, "is_authenticated", False):
        return False
    return can_publish_meeting(user, meeting)


@register.simple_tag(takes_context=True)
def can_close_meeting_tag(context, meeting=None):
    user = _user_from_context(context)
    if not user or not getattr(user, "is_authenticated", False):
        return False
    return can_close_meeting(user, meeting)


@register.simple_tag(takes_context=True)
def can_reopen_meeting_tag(context, meeting=None):
    user = _user_from_context(context)
    if not user or not getattr(user, "is_authenticated", False):
        return False
    return can_reopen_meeting(user, meeting)


@register.simple_tag(takes_context=True)
def can_create_snapshot_tag(context, meeting=None):
    user = _user_from_context(context)
    if not user or not getattr(user, "is_authenticated", False):
        return False
    return can_create_snapshot(user, meeting)


@register.filter(name="in_assigned_departments")
def in_assigned_departments(user, department):
    if not user or not getattr(user, "is_authenticated", False):
        return False
    dept_pk = getattr(department, "pk", department)
    return user.get_assigned_departments().filter(pk=dept_pk).exists()


@register.filter(name="in_contributor_departments")
def in_contributor_departments(user, department):
    if not user or not getattr(user, "is_authenticated", False):
        return False
    dept_pk = getattr(department, "pk", department)
    return user.get_contributor_departments().filter(pk=dept_pk).exists()


@register.filter
@stringfilter
def role_label(value):
    return value


@register.simple_tag(takes_context=True)
def can_export_reports_tag(context):
    user = _user_from_context(context)
    if not user or not getattr(user, "is_authenticated", False):
        return False
    return can_export_reports(user)


@register.simple_tag(takes_context=True)
def can_manage_departments_tag(context):
    user = _user_from_context(context)
    if not user or not getattr(user, "is_authenticated", False):
        return False
    return can_manage_departments(user)


@register.simple_tag(takes_context=True)
def can_manage_positions_tag(context):
    user = _user_from_context(context)
    if not user or not getattr(user, "is_authenticated", False):
        return False
    return can_manage_positions(user)


@register.simple_tag(takes_context=True)
def can_view_org_tag(context):
    user = _user_from_context(context)
    if not user or not getattr(user, "is_authenticated", False):
        return False
    return can_view_org(user)


register.simple_tag(func=is_system_admin, name="is_system_admin")
register.simple_tag(func=is_management_admin, name="is_management_admin")
register.simple_tag(func=is_meeting_chair, name="is_meeting_chair")
register.simple_tag(func=is_minutes_secretary, name="is_minutes_secretary")
register.simple_tag(func=is_department_contributor, name="is_department_contributor")
register.simple_tag(func=is_viewer, name="is_viewer")


@register.filter(name="startswith")
@stringfilter
def startswith(value, arg):
    try:
        return value.startswith(arg)
    except AttributeError:
        return False
