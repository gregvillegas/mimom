from django.urls import path

from apps.action_items import views

app_name = "action_items"

urlpatterns = [
    path("", views.ActionItemListView.as_view(), name="actionitem_list"),
    path("my/", views.ActionItemMyView.as_view(), name="actionitem_my"),
    path("department/", views.ActionItemDepartmentView.as_view(), name="actionitem_department"),
    path("overdue/", views.ActionItemOverdueView.as_view(), name="actionitem_overdue"),
    path("create/", views.ActionItemCreateView.as_view(), name="actionitem_create"),
    path(
        "from-agenda/<uuid:agenda_pk>/",
        views.ActionItemFromAgendaItemView.as_view(),
        name="actionitem_from_agenda",
    ),
    path(
        "carry-forward/",
        views.ActionItemCarryForwardView.as_view(),
        name="actionitem_carry_forward",
    ),
    path("<uuid:pk>/", views.ActionItemDetailView.as_view(), name="actionitem_detail"),
    path(
        "<uuid:pk>/edit/",
        views.ActionItemUpdateView.as_view(),
        name="actionitem_update",
    ),
    path(
        "<uuid:pk>/delete/",
        views.ActionItemDeleteView.as_view(),
        name="actionitem_delete",
    ),
    path(
        "<uuid:pk>/assignees/save/",
        views.ActionItemAssigneeSaveView.as_view(),
        name="actionitem_assignees_save",
    ),
    path(
        "<uuid:pk>/transition/",
        views.ActionItemTransitionView.as_view(),
        name="actionitem_transition",
    ),
    path(
        "<uuid:pk>/complete/",
        views.ActionItemCompleteView.as_view(),
        name="actionitem_complete",
    ),
    path(
        "<uuid:pk>/reopen/",
        views.ActionItemReopenView.as_view(),
        name="actionitem_reopen",
    ),
    path(
        "<uuid:pk>/update/add/",
        views.ActionItemAddUpdateView.as_view(),
        name="actionitem_add_update",
    ),
    path(
        "<uuid:pk>/attach/",
        views.ActionItemAttachmentUploadView.as_view(),
        name="actionitem_attach",
    ),
    path(
        "attachments/<uuid:pk>/delete/",
        views.ActionItemAttachmentDeleteView.as_view(),
        name="attachment_delete",
    ),
]
