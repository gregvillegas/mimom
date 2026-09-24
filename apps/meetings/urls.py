from django.urls import path

from apps.meetings import views

app_name = "meetings"

urlpatterns = [
    path("", views.MeetingListView.as_view(), name="meeting_list"),
    path("<uuid:pk>/", views.MeetingDetailView.as_view(), name="meeting_detail"),
    path("new/", views.MeetingCreateView.as_view(), name="meeting_create"),
    path("<uuid:pk>/edit/", views.MeetingUpdateView.as_view(), name="meeting_update"),
    path("<uuid:pk>/archive/", views.MeetingArchiveView.as_view(), name="meeting_archive"),
    path(
        "<uuid:pk>/transition/",
        views.MeetingTransitionView.as_view(),
        name="meeting_transition",
    ),
    path(
        "<uuid:pk>/attendance/",
        views.MeetingAttendanceView.as_view(),
        name="meeting_attendance",
    ),
    path(
        "<uuid:pk>/carry-forward/",
        views.MeetingCarryForwardView.as_view(),
        name="meeting_carry_forward",
    ),
    path(
        "agenda-categories/",
        views.AgendaCategoryListView.as_view(),
        name="agenda_category_list",
    ),
    path(
        "agenda-categories/new/",
        views.AgendaCategoryCreateView.as_view(),
        name="agenda_category_create",
    ),
    path(
        "agenda-categories/<uuid:pk>/edit/",
        views.AgendaCategoryUpdateView.as_view(),
        name="agenda_category_update",
    ),
    path(
        "<uuid:meeting_pk>/agenda/new/",
        views.AgendaItemCreateView.as_view(),
        name="agenda_item_create",
    ),
    path(
        "agenda/<uuid:pk>/edit/",
        views.AgendaItemUpdateView.as_view(),
        name="agenda_item_update",
    ),
    path(
        "agenda/<uuid:pk>/delete/",
        views.AgendaItemDeleteView.as_view(),
        name="agenda_item_delete",
    ),
    path(
        "<uuid:meeting_pk>/agenda/order/",
        views.AgendaOrderSaveView.as_view(),
        name="agenda_item_order",
    ),
    path(
        "<uuid:meeting_pk>/attachments/upload/",
        views.MeetingAttachmentUploadView.as_view(),
        name="meeting_attachment_upload",
    ),
    path(
        "attachments/<uuid:pk>/delete/",
        views.MeetingAttachmentDeleteView.as_view(),
        name="meeting_attachment_delete",
    ),
    path(
        "agenda-attachments/<uuid:item_pk>/upload/",
        views.AgendaItemAttachmentUploadView.as_view(),
        name="agenda_item_attachment_upload",
    ),
    path(
        "agenda-attachments/<uuid:pk>/delete/",
        views.AgendaItemAttachmentDeleteView.as_view(),
        name="agenda_item_attachment_delete",
    ),
]
