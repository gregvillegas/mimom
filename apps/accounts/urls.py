from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("users/", views.UserListView.as_view(), name="user_list"),
    path("users/create/", views.UserCreateView.as_view(), name="user_create"),
    path("users/<int:pk>/edit/", views.UserUpdateView.as_view(), name="user_edit"),
    path(
        "users/<int:user_pk>/departments/",
        views.DepartmentAssignmentsView.as_view(),
        name="department_assignments",
    ),
    path("departments/", views.DepartmentListView.as_view(), name="department_list"),
    path("departments/create/", views.DepartmentCreateView.as_view(), name="department_create"),
    path("departments/<uuid:pk>/", views.DepartmentDetailView.as_view(), name="department_detail"),
    path(
        "departments/<uuid:pk>/edit/",
        views.DepartmentUpdateView.as_view(),
        name="department_edit",
    ),
    path("positions/", views.PositionListView.as_view(), name="position_list"),
    path("positions/create/", views.PositionCreateView.as_view(), name="position_create"),
    path("positions/<uuid:pk>/", views.PositionDetailView.as_view(), name="position_detail"),
    path(
        "positions/<uuid:pk>/edit/",
        views.PositionUpdateView.as_view(),
        name="position_edit",
    ),
    path("teams/", views.OrgTeamsListView.as_view(), name="team_list"),
    path("profile/", views.ProfileView.as_view(), name="profile_me"),
    path("profile/edit/", views.ProfileEditView.as_view(), name="profile_edit"),
    path("profile/<int:pk>/", views.ProfileView.as_view(), name="profile_detail"),
    path("password/change/", views.password_change_view, name="password_change"),
    path("password/change/done/", views.password_change_done_view, name="password_change_done"),
]
