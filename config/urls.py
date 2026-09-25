from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from apps.core import views as core_views


def custom_page_not_found(request, exception):
    from django.shortcuts import render

    return render(request, "errors/404.html", status=404)


def custom_permission_denied(request, exception):
    from django.shortcuts import render

    return render(request, "errors/403.html", status=403)


def custom_server_error(request):
    from django.shortcuts import render

    return render(request, "errors/500.html", status=500)


handler404 = "config.urls.custom_page_not_found"
handler403 = "config.urls.custom_permission_denied"
handler500 = "config.urls.custom_server_error"

urlpatterns = [
    path("admin/", admin.site.urls),
    path(
        "login/",
        auth_views.LoginView.as_view(template_name="registration/login.html"),
        name="login",
    ),
    path(
        "logout/",
        auth_views.LogoutView.as_view(template_name="registration/logged_out.html"),
        name="logout",
    ),
    path("", core_views.home, name="home"),
    path("health/", core_views.health_check, name="health_check"),
    path("", include("apps.core.urls")),
    path("accounts/", include("apps.accounts.urls")),
    path("meetings/", include("apps.meetings.urls")),
    path("actions/", include("apps.action_items.urls")),
    path("sales/", include("apps.sales_updates.urls")),
    path("notifications/", include("apps.notifications.urls")),
    path("reports/", include("apps.reports.urls", namespace="reports")),
    path("audit/", include("apps.audit.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
