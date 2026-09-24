from django.urls import path

from apps.sales_updates import views

app_name = "sales_updates"

urlpatterns = [
    path("", views.ExportPageView.as_view(), name="exports_page"),
    path("dashboard/", views.GroupDashboardView.as_view(), name="group_dashboard"),
    path(
        "dashboard/<uuid:period_id>/",
        views.GroupDashboardView.as_view(),
        name="group_dashboard_period",
    ),
    # Reporting periods
    path("periods/", views.ReportingPeriodListView.as_view(), name="period_list"),
    path("periods/create/", views.ReportingPeriodCreateView.as_view(), name="period_create"),
    path(
        "periods/<uuid:pk>/edit/", views.ReportingPeriodUpdateView.as_view(), name="period_update"
    ),
    # Teams
    path("teams/", views.SalesTeamListView.as_view(), name="team_list"),
    path("teams/create/", views.SalesTeamCreateView.as_view(), name="team_create"),
    # Groups
    path("groups/", views.SalesGroupListView.as_view(), name="group_list"),
    path("groups/create/", views.SalesGroupCreateView.as_view(), name="group_create"),
    path("groups/<uuid:pk>/edit/", views.SalesGroupUpdateView.as_view(), name="group_update"),
    # Combined group-period detail
    path(
        "groups/<uuid:group_id>/period/<uuid:period_id>/",
        views.GroupPeriodDetailView.as_view(),
        name="group_period_detail",
    ),
    # Performance upserts
    path(
        "groups/<uuid:group_id>/period/<uuid:period_id>/targets/save/",
        views.PerformanceTargetUpsertView.as_view(),
        name="target_upsert",
    ),
    path(
        "groups/<uuid:group_id>/period/<uuid:period_id>/deliveries/save/",
        views.DeliveryPerformanceUpsertView.as_view(),
        name="delivery_upsert",
    ),
    path(
        "groups/<uuid:group_id>/period/<uuid:period_id>/actuals/save/",
        views.SalesOrderPerformanceUpsertView.as_view(),
        name="actuals_upsert",
    ),
    # Snapshots + weekly commitments
    path("snapshots/create/", views.SnapshotCreateView.as_view(), name="snapshot_create"),
    path("snapshots/<uuid:pk>/", views.SnapshotDetailView.as_view(), name="snapshot_detail"),
    path(
        "snapshots/<uuid:pk>/weekly/save/",
        views.SnapshotWeeklySaveView.as_view(),
        name="snapshot_weekly_save",
    ),
    path(
        "snapshots/<uuid:pk>/printable/",
        views.SnapshotPrintableView.as_view(),
        name="snapshot_printable",
    ),
    # Excel exports
    path("exports/excel/", views.ExcelPeriodExportView.as_view(), name="export_excel"),
    path(
        "exports/excel/<uuid:period_id>/",
        views.ExcelPeriodExportView.as_view(),
        name="export_excel_period",
    ),
]
