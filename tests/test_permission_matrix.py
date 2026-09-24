import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import RequestFactory

from apps.accounts.models import Department, DepartmentMembership
from apps.core.permissions import (
    DepartmentContributorRequiredMixin,
    ManagementRoleRequiredMixin,
    RoleRequiredMixin,
    UserManagementRequiredMixin,
    _active_authenticated,
    can_manage_department_assignments,
    can_manage_users,
    group_required,
    is_department_contributor,
    is_management_admin,
    is_meeting_chair,
    is_minutes_secretary,
    is_system_admin,
    is_viewer,
    user_in_department_contributors,
)

User = get_user_model()


def _make_user(username, *, groups=None, is_active=True, is_superuser=False, **extra):
    email = extra.pop("email", None) or f"{username}@example.com"
    user = User.objects.create_user(
        username=username,
        email=email,
        password="pw-1234!",
        is_active=is_active,
        is_superuser=is_superuser,
        **extra,
    )
    if groups:
        user.groups.set(Group.objects.filter(name__in=groups))
    return user


@pytest.fixture
def six_roles(db):
    for name in [
        "System Administrator",
        "Management Administrator",
        "Meeting Chairperson",
        "Minutes Secretary",
        "Department Contributor",
        "Viewer",
    ]:
        Group.objects.get_or_create(name=name)
    return Group.objects.all()


@pytest.mark.django_db
def test_active_authenticated_predicate(rf: RequestFactory):
    user = User.objects.create_user(
        username="anonish", email="a@b.com", password="pw", is_active=True
    )
    req = rf.get("/")
    req.user = user
    assert _active_authenticated(user) is True

    user.is_active = False
    user.save()
    user.refresh_from_db()
    assert _active_authenticated(user) is False

    from django.contrib.auth.models import AnonymousUser

    assert _active_authenticated(AnonymousUser()) is False


@pytest.mark.django_db
def test_is_system_admin_and_shortcircuit_superuser(six_roles):
    sa = _make_user("sa", groups=["System Administrator"])
    mgmt = _make_user("mgmt", groups=["Management Administrator"])
    su = _make_user("su", is_superuser=True)

    assert is_system_admin(sa) is True
    assert is_system_admin(mgmt) is False
    assert is_system_admin(su) is True  # superuser short-circuit


@pytest.mark.django_db
def test_role_helpers_match_each_group(six_roles):
    roles = [
        (is_management_admin, "Management Administrator", "Meeting Chairperson"),
        (is_meeting_chair, "Meeting Chairperson", "Management Administrator"),
        (is_minutes_secretary, "Minutes Secretary", "Management Administrator"),
        (is_department_contributor, "Department Contributor", "Management Administrator"),
    ]
    for predicate, pass_group, fail_group in roles:
        u = _make_user(
            f"u-{pass_group.lower().replace(' ', '-')}",
            groups=[pass_group],
            email=f"u-{pass_group.lower().replace(' ', '-')}@ex.com",
        )
        assert predicate(u) is True, pass_group
        wrong = _make_user(
            f"w-{pass_group.lower().replace(' ', '-')}",
            groups=[fail_group],
            email=f"w-{pass_group.lower().replace(' ', '-')}@ex.com",
        )
        assert predicate(wrong) is False, pass_group


@pytest.mark.django_db
def test_is_viewer(six_roles):
    v = _make_user("viewer1", groups=["Viewer"])
    other = _make_user("chair1", groups=["Meeting Chairperson"])
    assert is_viewer(v) is True
    assert is_viewer(other) is False


@pytest.mark.django_db
def test_has_role_inactive_user_returns_false_even_with_group(six_roles):
    u = _make_user("zombie", groups=["Management Administrator"], is_active=False)
    assert u.groups.count() == 1
    assert u.has_role("Management Administrator") is False
    assert is_management_admin(u) is False
    assert can_manage_users(u) is False


@pytest.mark.django_db
def test_has_role_union_of_multiple_groups(six_roles):
    u = _make_user("multi", groups=["Meeting Chairperson", "Viewer"])
    assert u.has_role("Viewer") is True
    assert u.has_role("Meeting Chairperson") is True
    assert u.has_role("System Administrator") is False
    assert u.has_role("System Administrator", "Viewer") is True  # union: any match


@pytest.mark.django_db
def test_has_role_empty_args(six_roles):
    u = _make_user("x", groups=["Viewer"])
    assert u.has_role() is False
    assert u.has_role("", None) is False


@pytest.mark.django_db
def test_can_manage_users_and_assignments(six_roles):
    sa = _make_user("sa", groups=["System Administrator"])
    mgmt = _make_user("mgmt", groups=["Management Administrator"])
    chair = _make_user("chair", groups=["Meeting Chairperson"])
    viewer = _make_user("v", groups=["Viewer"])
    su = _make_user("su", is_superuser=True)

    assert can_manage_users(sa) is True
    assert can_manage_users(mgmt) is True
    assert can_manage_users(chair) is False
    assert can_manage_users(viewer) is False
    assert can_manage_users(su) is True

    assert can_manage_department_assignments(sa) is True
    assert can_manage_department_assignments(mgmt) is True
    assert can_manage_department_assignments(chair) is True
    assert can_manage_department_assignments(viewer) is False


@pytest.mark.django_db
def test_user_in_department_contributors_scoped(rf: RequestFactory):
    Group.objects.get_or_create(name="Department Contributor")
    sales = Department.objects.create(name="Sales", code="SAL")
    ops = Department.objects.create(name="Ops", code="OPS")
    u = _make_user("contrib", groups=["Department Contributor"])
    DepartmentMembership.objects.create(
        user=u, department=sales, is_active=True, is_contributor=True
    )
    DepartmentMembership.objects.create(
        user=u, department=ops, is_active=True, is_contributor=False
    )

    assert user_in_department_contributors(u, sales) is True
    assert user_in_department_contributors(u, ops) is False

    u.is_active = False
    u.save()
    assert user_in_department_contributors(u, sales) is False


@pytest.mark.django_db
def test_role_required_mixin(rf: RequestFactory, six_roles):
    class _V(RoleRequiredMixin):
        required_roles = ("Management Administrator",)
        request = None

    mgmt = _make_user("m1", groups=["Management Administrator"])
    viewer = _make_user("v1", groups=["Viewer"])
    req = rf.get("/")
    req.user = mgmt
    v = _V()
    v.request = req
    assert v.test_func() is True

    req.user = viewer
    assert v.test_func() is False


@pytest.mark.django_db
def test_role_required_mixin_superuser(rf: RequestFactory, six_roles):
    class _V(RoleRequiredMixin):
        required_roles = ("Management Administrator",)
        request = None

    su = _make_user("su", is_superuser=True)
    req = rf.get("/")
    req.user = su
    v = _V()
    v.request = req
    assert v.test_func() is True


@pytest.mark.django_db
def test_user_management_mixin(rf: RequestFactory, six_roles):
    for gname in {"System Administrator", "Management Administrator"}:
        u = _make_user(
            f"umm-{gname.lower().replace(' ', '')}",
            groups=[gname],
            email=f"umm-{gname.lower().replace(' ', '')}@ex.com",
        )
        req = rf.get("/")
        req.user = u
        m = UserManagementRequiredMixin()
        m.request = req
        assert m.test_func() is True, gname

    viewer = _make_user("v-umm", groups=["Viewer"])
    req = rf.get("/")
    req.user = viewer
    m = UserManagementRequiredMixin()
    m.request = req
    assert m.test_func() is False


@pytest.mark.django_db
def test_management_role_mixin(rf: RequestFactory, six_roles):
    for gname in {
        "System Administrator",
        "Management Administrator",
        "Meeting Chairperson",
    }:
        u = _make_user(
            f"mrm-{gname.lower().replace(' ', '')}",
            groups=[gname],
            email=f"mrm-{gname.lower().replace(' ', '')}@ex.com",
        )
        req = rf.get("/")
        req.user = u
        m = ManagementRoleRequiredMixin()
        m.request = req
        assert m.test_func() is True, gname

    viewer = _make_user("v-mrm", groups=["Viewer"])
    req = rf.get("/")
    req.user = viewer
    m = ManagementRoleRequiredMixin()
    m.request = req
    assert m.test_func() is False


@pytest.mark.django_db
def test_group_required_decorator(rf: RequestFactory, six_roles):
    @group_required("Management Administrator")
    def my_view(request):
        return "allowed"

    mgmt = _make_user("m2", groups=["Management Administrator"])
    req = rf.get("/")
    req.user = mgmt
    assert my_view(req) == "allowed"

    viewer = _make_user("v2", groups=["Viewer"])
    from django.core.exceptions import PermissionDenied

    req.user = viewer
    with pytest.raises(PermissionDenied):
        my_view(req)

    from django.contrib.auth.models import AnonymousUser

    req.user = AnonymousUser()
    resp = my_view(req)
    assert resp.status_code == 302


@pytest.mark.django_db
def test_department_contributor_required_mixin(rf: RequestFactory, six_roles):
    class _FakeView(DepartmentContributorRequiredMixin):
        def __init__(self, dept_pk):
            self.kwargs = {"department_pk": dept_pk}

        def _actual_view(self, request):
            return "allowed"

        def dispatch(self, request, *args, **kwargs):
            from django.core.exceptions import PermissionDenied as _PD

            user = request.user
            if not (user and user.is_authenticated and getattr(user, "is_active", False)):
                return self.handle_no_permission()
            if getattr(user, "is_superuser", False):
                return self._actual_view(request)
            dept = self.get_department()
            from apps.core.permissions import user_in_department_contributors

            if not user_in_department_contributors(user, dept):
                raise _PD()
            return self._actual_view(request)

    sales = Department.objects.create(name="Sales", code="SAL")
    ops = Department.objects.create(name="Ops", code="OPS")
    contrib = _make_user("c2", groups=["Department Contributor"])
    DepartmentMembership.objects.create(
        user=contrib, department=sales, is_active=True, is_contributor=True
    )

    req = rf.get("/")
    req.user = contrib
    assert _FakeView(sales.pk).dispatch(req) == "allowed"

    from django.core.exceptions import PermissionDenied

    with pytest.raises(PermissionDenied):
        _FakeView(ops.pk).dispatch(req)
