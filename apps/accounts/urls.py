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
    path("profile/", views.ProfileView.as_view(), name="profile_me"),
    path("profile/edit/", views.ProfileEditView.as_view(), name="profile_edit"),
    path("profile/<int:pk>/", views.ProfileView.as_view(), name="profile_detail"),
    path("password/change/", views.password_change_view, name="password_change"),
    path("password/change/done/", views.password_change_done_view, name="password_change_done"),
]
