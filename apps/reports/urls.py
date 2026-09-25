from django.urls import path

from apps.reports import views

app_name = "reports"

urlpatterns = [
    path("", views.ReportsIndexView.as_view(), name="index"),
    path("<slug:report>/html/", views.PrintableHtmlView.as_view(), name="report_html"),
    path(
        "<slug:report>/excel/<uuid:pk>/",
        views.ExcelExportView.as_view(),
        name="report_excel_pk",
    ),
    path("<slug:report>/excel/", views.ExcelExportView.as_view(), name="report_excel"),
    path(
        "<slug:report>/word/<uuid:pk>/",
        views.WordExportView.as_view(),
        name="report_word_pk",
    ),
    path("<slug:report>/word/", views.WordExportView.as_view(), name="report_word"),
    path(
        "<slug:report>/pdf/<uuid:pk>/",
        views.PdfExportView.as_view(),
        name="report_pdf_pk",
    ),
    path("<slug:report>/pdf/", views.PdfExportView.as_view(), name="report_pdf"),
    path(
        "<slug:report>/<uuid:pk>/html/",
        views.PrintableHtmlView.as_view(),
        name="report_snapshot_html",
    ),
]
