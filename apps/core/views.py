from django.contrib.auth.decorators import login_required
from django.db import connection
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone


def health_check(request):
    payload = {
        "status": "ok",
        "timestamp": timezone.now().isoformat(),
        "service": "intranet",
    }
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        payload["database"] = "ok"
    except Exception as exc:
        payload["status"] = "degraded"
        payload["database"] = f"error: {exc}"
    return JsonResponse(payload)


@login_required
def home(request):
    context = {
        "page_title": "Dashboard",
        "now": timezone.now(),
    }
    try:
        from apps.meetings.views import dashboard_summary_counts

        context.update(dashboard_summary_counts(request))
    except Exception:
        context.setdefault("meeting_counts", {})
        context.setdefault("upcoming_meetings", [])
        context.setdefault("meeting_total", 0)
    try:
        from apps.action_items.views import dashboard_action_data

        counts, overdue = dashboard_action_data(request.user)
        context["action_counts"] = counts
        context["action_overdue"] = overdue
    except Exception:
        context.setdefault(
            "action_counts",
            {
                "total_open": 0,
                "assigned_me": 0,
                "overdue": 0,
                "due_this_week": 0,
                "completed_this_week": 0,
            },
        )
        context.setdefault("action_overdue", [])
    try:
        from apps.sales_updates.services import sales_dashboard_data

        sales_summary, sales_groups = sales_dashboard_data(request.user)
        context["sales_summary"] = sales_summary
        context["sales_groups"] = sales_groups
    except Exception:
        context.setdefault(
            "sales_summary",
            {
                "period_name": "",
                "revenue_actual": 0,
                "revenue_pct": 0,
                "revenue_deficit": 0,
                "margin_pct_actual": 0,
                "days_left": None,
                "weeks_left": 0,
                "currency": "PHP",
                "cut_off_date": None,
            },
        )
        context.setdefault("sales_groups", [])
    try:
        from apps.meetings.services import meetings_prep_dashboard_data

        prep_data = meetings_prep_dashboard_data(request.user)
        if isinstance(prep_data, tuple) and len(prep_data) >= 2:
            context["meetings_prep_dashboard_data"] = prep_data[0]
        elif isinstance(prep_data, dict):
            context["meetings_prep_dashboard_data"] = prep_data
        else:
            context["meetings_prep_dashboard_data"] = {}
    except Exception:
        context.setdefault(
            "meetings_prep_dashboard_data",
            {
                "pending_review": 0,
                "returned": 0,
                "approved_this_month": 0,
                "ready_to_publish": 0,
            },
        )
    try:
        from apps.reports.services import reports_index_data

        rd = reports_index_data(request.user)
    except Exception:
        rd = {
            "generated_today": 0,
            "exports_week": 0,
            "snapshots_reports": 0,
            "open_action_items": 0,
        }
    context["reports"] = rd
    return render(request, "dashboard/home.html", context)
