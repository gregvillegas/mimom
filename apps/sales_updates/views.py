from __future__ import annotations

from datetime import UTC, datetime
from io import BytesIO

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.http import Http404, HttpResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from apps.audit.models import AuditLog
from apps.audit.services import log_audit_event
from apps.core.permissions import (
    SalesEditRequiredMixin,
    can_edit_sales_period,
    can_export_sales,
    can_view_sales_period,
)
from apps.sales_updates.forms import (
    DeliveryPerformanceForm,
    PerformanceTargetForm,
    ReportingPeriodForm,
    SalesGroupForm,
    SalesOrderPerformanceForm,
    SalesTeamForm,
    SnapshotCreateForm,
    build_membership_formset,
    build_weekly_commitment_formset,
)
from apps.sales_updates.models import (
    DEFAULT_CURRENCY,
    DeliveryPerformance,
    GroupPerformanceSnapshot,
    PerformanceTarget,
    ReportingPeriod,
    SalesGroup,
    SalesOrderPerformance,
    SalesTeam,
)
from apps.sales_updates.services import (
    current_reporting_period,
    group_period_subtotals,
    is_snapshot_locked,
    overall_period_totals,
    sales_dashboard_data,
    take_snapshot,
    team_period_totals,
)

# ---------------------------------------------------------------------------
# Reporting periods
# ---------------------------------------------------------------------------


class SalesQuerysetHelpers:
    """Small mixin: period visibility = all active periods for sales viewers."""

    def get_period_qs(self, request):
        qs = ReportingPeriod.objects.select_related()
        if not getattr(request.user, "is_superuser", False):
            pass
        return qs


class ReportingPeriodListView(LoginRequiredMixin, ListView):
    model = ReportingPeriod
    template_name = "sales_updates/reportingperiod_list.html"
    context_object_name = "periods"

    def dispatch(self, request, *args, **kwargs):
        if not can_view_sales_period(request.user):
            return self.handle_no_permission()
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return ReportingPeriod.objects.all().order_by("-start_date")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["current_period"] = current_reporting_period()
        return ctx


class ReportingPeriodCreateView(LoginRequiredMixin, SalesEditRequiredMixin, CreateView):
    model = ReportingPeriod
    form_class = ReportingPeriodForm
    template_name = "sales_updates/reportingperiod_form.html"

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        with transaction.atomic():
            response = super().form_valid(form)
            log_audit_event(
                record_type="sales_updates.reportingperiod",
                record=self.object,
                action=AuditLog.ACTION_CREATE,
                user=self.request.user,
                reason="Reporting period created",
            )
        return response

    def get_success_url(self):
        return reverse("sales_updates:period_list")


class ReportingPeriodUpdateView(LoginRequiredMixin, SalesEditRequiredMixin, UpdateView):
    model = ReportingPeriod
    form_class = ReportingPeriodForm
    template_name = "sales_updates/reportingperiod_form.html"
    pk_url_kwarg = "pk"

    def dispatch(self, request, *args, **kwargs):
        period = self.get_object()
        if period.is_locked and not getattr(request.user, "is_superuser", False):
            messages.error(request, "This reporting period is CLOSED and locked.")
            return redirect(reverse("sales_updates:period_list"))
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        prior = ReportingPeriod.objects.filter(pk=self.object.pk).first()
        with transaction.atomic():
            response = super().form_valid(form)
            log_audit_event(
                record_type="sales_updates.reportingperiod",
                record=self.object,
                action=AuditLog.ACTION_UPDATE,
                user=self.request.user,
                previous_values={"status": getattr(prior, "status", None)},
                new_values={"status": self.object.status},
            )
        return response

    def get_success_url(self):
        return reverse("sales_updates:period_list")


# ---------------------------------------------------------------------------
# Teams + groups
# ---------------------------------------------------------------------------


class SalesTeamListView(LoginRequiredMixin, ListView):
    model = SalesTeam
    template_name = "sales_updates/salesteam_list.html"
    context_object_name = "teams"

    def dispatch(self, request, *args, **kwargs):
        if not can_view_sales_period(request.user):
            return self.handle_no_permission()
        return super().dispatch(request, *args, **kwargs)


class SalesTeamCreateView(LoginRequiredMixin, SalesEditRequiredMixin, CreateView):
    model = SalesTeam
    form_class = SalesTeamForm
    template_name = "sales_updates/salesteam_form.html"

    def get_success_url(self):
        return reverse("sales_updates:team_list")


class SalesGroupListView(LoginRequiredMixin, ListView):
    model = SalesGroup
    template_name = "sales_updates/salesgroup_list.html"
    context_object_name = "groups"

    def dispatch(self, request, *args, **kwargs):
        if not can_view_sales_period(request.user):
            return self.handle_no_permission()
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return SalesGroup.objects.select_related("team").all()


class SalesGroupCreateView(LoginRequiredMixin, SalesEditRequiredMixin, CreateView):
    model = SalesGroup
    form_class = SalesGroupForm
    template_name = "sales_updates/salesgroup_form.html"

    def get_success_url(self):
        return reverse("sales_updates:group_list")


class SalesGroupUpdateView(LoginRequiredMixin, SalesEditRequiredMixin, UpdateView):
    model = SalesGroup
    form_class = SalesGroupForm
    template_name = "sales_updates/salesgroup_form.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        if self.request.POST:
            ctx["membership_formset"] = build_membership_formset(self.object, self.request.POST)
        else:
            ctx["membership_formset"] = build_membership_formset(self.object)
        return ctx

    def form_valid(self, form):
        ctx = self.get_context_data()
        formset = ctx["membership_formset"]
        if not formset.is_valid():
            return self.render_to_response(self.get_context_data(form=form))
        with transaction.atomic():
            self.object = form.save()
            formset.instance = self.object
            formset.save()
        return redirect(self.get_success_url())

    def get_success_url(self):
        return reverse("sales_updates:group_list")


# ---------------------------------------------------------------------------
# Main group-period dashboard (targets + deliveries + sales orders + charts)
# ---------------------------------------------------------------------------


class GroupPeriodDetailView(LoginRequiredMixin, DetailView):
    """Combined view: targets / deliveries / sales / weekly commitments tabs + charts."""

    template_name = "sales_updates/group_period_detail.html"
    context_object_name = "group"

    def dispatch(self, request, *args, **kwargs):
        if not can_view_sales_period(request.user):
            return self.handle_no_permission()
        return super().dispatch(request, *args, **kwargs)

    def get_object(self, queryset=None):
        return get_object_or_404(SalesGroup, pk=self.kwargs["group_id"])

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        group = self.object
        period = get_object_or_404(ReportingPeriod, pk=self.kwargs["period_id"])
        ctx["period"] = period
        ctx["subtotals"] = group_period_subtotals(group, period)
        ctx["target"] = PerformanceTarget.objects.filter(group=group, period=period).first()
        ctx["delivery"] = DeliveryPerformance.objects.filter(group=group, period=period).first()
        ctx["actual"] = SalesOrderPerformance.objects.filter(group=group, period=period).first()
        ctx["snapshots"] = (
            GroupPerformanceSnapshot.objects.filter(group=group, period=period)
            .select_related("meeting")
            .order_by("-created_at")
        )
        ctx["can_edit"] = can_edit_sales_period(self.request.user, period)
        return ctx


class GroupDashboardView(LoginRequiredMixin, View):
    """Overall group dashboard — pickable current period + team subtotal rows."""

    def get(self, request, period_id=None):
        if not can_view_sales_period(request.user):
            return redirect(reverse("home"))
        if period_id:
            period = get_object_or_404(ReportingPeriod, pk=period_id)
        else:
            period = (
                current_reporting_period()
                or ReportingPeriod.objects.order_by("-start_date").first()
            )
        teams_summary = []
        for team in SalesTeam.objects.filter(is_active=True).prefetch_related("groups"):
            teams_summary.append(team_period_totals(team, period))
        overall = overall_period_totals(period) if period else None
        return render(
            request,
            "sales_updates/group_dashboard.html",
            {
                "period": period,
                "periods": ReportingPeriod.objects.order_by("-start_date"),
                "teams_summary": teams_summary,
                "overall": overall,
                "can_export": can_export_sales(request.user),
            },
        )


# ---------------------------------------------------------------------------
# Targets + performance entry views (POST)
# ---------------------------------------------------------------------------


class PerformanceTargetUpsertView(LoginRequiredMixin, SalesEditRequiredMixin, View):
    """Create or update PerformanceTarget for (group, period) pair."""

    def post(self, request, group_id, period_id):
        group = get_object_or_404(SalesGroup, pk=group_id)
        period = get_object_or_404(ReportingPeriod, pk=period_id)
        if period.is_locked:
            messages.error(request, "Period locked — cannot change targets.")
            return redirect(
                reverse(
                    "sales_updates:group_period_detail",
                    args=[group.pk, period.pk],
                )
                + "#targets"
            )
        instance = PerformanceTarget.objects.filter(group=group, period=period).first()
        form = PerformanceTargetForm(request.POST, instance=instance)
        if not form.is_valid():
            for _, errs in form.errors.items():
                for err in errs:
                    messages.error(request, err)
            return redirect(
                reverse("sales_updates:group_period_detail", args=[group.pk, period.pk])
                + "#targets"
            )
        with transaction.atomic():
            target = form.save(commit=False)
            target.group = group
            target.period = period
            target.last_modified_by = request.user
            target.save()
            log_audit_event(
                record_type="sales_updates.performancetarget",
                record=target,
                action=AuditLog.ACTION_UPDATE if instance else AuditLog.ACTION_CREATE,
                user=request.user,
            )
        messages.success(request, "Performance targets saved.")
        return redirect(
            reverse("sales_updates:group_period_detail", args=[group.pk, period.pk]) + "#targets"
        )


class DeliveryPerformanceUpsertView(LoginRequiredMixin, SalesEditRequiredMixin, View):
    def post(self, request, group_id, period_id):
        group = get_object_or_404(SalesGroup, pk=group_id)
        period = get_object_or_404(ReportingPeriod, pk=period_id)
        if period.is_locked:
            messages.error(request, "Period locked.")
            return redirect(
                reverse("sales_updates:group_period_detail", args=[group.pk, period.pk])
                + "#deliveries"
            )
        instance = DeliveryPerformance.objects.filter(group=group, period=period).first()
        form = DeliveryPerformanceForm(request.POST, instance=instance)
        if not form.is_valid():
            for _, errs in form.errors.items():
                for err in errs:
                    messages.error(request, err)
            return redirect(
                reverse("sales_updates:group_period_detail", args=[group.pk, period.pk])
                + "#deliveries"
            )
        with transaction.atomic():
            rec = form.save(commit=False)
            rec.group = group
            rec.period = period
            rec.last_modified_by = request.user
            rec.save()
            log_audit_event(
                record_type="sales_updates.deliveryperformance",
                record=rec,
                action=AuditLog.ACTION_UPDATE if instance else AuditLog.ACTION_CREATE,
                user=request.user,
            )
        messages.success(request, "Delivery performance saved.")
        return redirect(
            reverse("sales_updates:group_period_detail", args=[group.pk, period.pk]) + "#deliveries"
        )


class SalesOrderPerformanceUpsertView(LoginRequiredMixin, SalesEditRequiredMixin, View):
    def post(self, request, group_id, period_id):
        group = get_object_or_404(SalesGroup, pk=group_id)
        period = get_object_or_404(ReportingPeriod, pk=period_id)
        if period.is_locked:
            messages.error(request, "Period locked.")
            return redirect(
                reverse("sales_updates:group_period_detail", args=[group.pk, period.pk])
                + "#actuals"
            )
        instance = SalesOrderPerformance.objects.filter(group=group, period=period).first()
        form = SalesOrderPerformanceForm(request.POST, instance=instance)
        if not form.is_valid():
            for _, errs in form.errors.items():
                for err in errs:
                    messages.error(request, err)
            return redirect(
                reverse("sales_updates:group_period_detail", args=[group.pk, period.pk])
                + "#actuals"
            )
        with transaction.atomic():
            rec = form.save(commit=False)
            rec.group = group
            rec.period = period
            rec.last_modified_by = request.user
            rec.save()
            log_audit_event(
                record_type="sales_updates.salesorderperformance",
                record=rec,
                action=AuditLog.ACTION_UPDATE if instance else AuditLog.ACTION_CREATE,
                user=request.user,
            )
        messages.success(request, "Sales order performance saved.")
        return redirect(
            reverse("sales_updates:group_period_detail", args=[group.pk, period.pk]) + "#actuals"
        )


# ---------------------------------------------------------------------------
# Snapshots + weekly commitments
# ---------------------------------------------------------------------------


class SnapshotCreateView(LoginRequiredMixin, SalesEditRequiredMixin, View):
    def post(self, request):
        form = SnapshotCreateForm(request.POST)
        if not form.is_valid():
            for _, errs in form.errors.items():
                for err in errs:
                    messages.error(request, err)
            return redirect(reverse("sales_updates:exports_page"))
        group = form.cleaned_data["group"]
        period = form.cleaned_data["period"]
        meeting = form.cleaned_data.get("meeting")
        with transaction.atomic():
            snap = take_snapshot(
                group,
                period,
                meeting=meeting,
                by_user=request.user,
                reason=form.cleaned_data.get("reason") or "",
            )
        messages.success(request, f"Snapshot {snap.pk} created.")
        return redirect(reverse("sales_updates:snapshot_detail", args=[snap.pk]))


class SnapshotDetailView(LoginRequiredMixin, DetailView):
    model = GroupPerformanceSnapshot
    template_name = "sales_updates/snapshot_detail.html"
    context_object_name = "snapshot"

    def dispatch(self, request, *args, **kwargs):
        if not can_view_sales_period(request.user):
            return self.handle_no_permission()
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return super().get_queryset().select_related("group", "period", "meeting")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        snap = self.object
        ctx["locked"] = is_snapshot_locked(snap)
        ctx["can_edit"] = (
            can_edit_sales_period(self.request.user, snap.period) and not ctx["locked"]
        )
        from apps.sales_updates.services import weekly_commitment_totals

        ctx["weekly_totals"] = weekly_commitment_totals(snap)
        ctx["currency"] = snap.currency or snap.period.currency or DEFAULT_CURRENCY
        if self.request.POST and ctx["can_edit"]:
            ctx["weekly_formset"] = build_weekly_commitment_formset(snap, self.request.POST)
        else:
            ctx["weekly_formset"] = build_weekly_commitment_formset(snap)
        return ctx


class SnapshotWeeklySaveView(LoginRequiredMixin, SalesEditRequiredMixin, View):
    def post(self, request, pk):
        snap = get_object_or_404(GroupPerformanceSnapshot, pk=pk)
        if is_snapshot_locked(snap) or snap.period.is_locked:
            messages.error(request, "Snapshot is locked.")
            return redirect(reverse("sales_updates:snapshot_detail", args=[snap.pk]) + "#weekly")
        formset = build_weekly_commitment_formset(snap, request.POST)
        if not formset.is_valid():
            for fs in formset:
                for _, errs in fs.errors.items():
                    for err in errs:
                        messages.error(request, err)
            return redirect(reverse("sales_updates:snapshot_detail", args=[snap.pk]) + "#weekly")
        with transaction.atomic():
            formset.save()
            log_audit_event(
                record_type="sales_updates.groupperformancesnapshot",
                record=snap,
                action=AuditLog.ACTION_UPDATE,
                user=request.user,
                reason="Weekly commitments updated.",
            )
        messages.success(request, "Weekly commitments saved.")
        return redirect(reverse("sales_updates:snapshot_detail", args=[snap.pk]) + "#weekly")


# ---------------------------------------------------------------------------
# Export page + Excel + printable HTML
# ---------------------------------------------------------------------------


class ExportPageView(LoginRequiredMixin, View):
    def get(self, request):
        if not can_view_sales_period(request.user):
            return redirect(reverse("home"))
        period = (
            current_reporting_period() or ReportingPeriod.objects.order_by("-start_date").first()
        )
        snapshot_form = SnapshotCreateForm()
        return render(
            request,
            "sales_updates/export_page.html",
            {
                "period": period,
                "overall": overall_period_totals(period) if period else None,
                "can_export": can_export_sales(request.user),
                "snapshot_form": snapshot_form,
            },
        )


class ExcelPeriodExportView(LoginRequiredMixin, View):
    """Export an overall-period performance workbook via openpyxl (rule 15).

    Returns a StreamingHttpResponse (memory-safe) even for small data — matches
    openpyxl.save_virtual_workbook() BytesIO pattern wrapped in streaming body.
    """

    def get(self, request, period_id=None):
        if not can_export_sales(request.user):
            return self.handle_no_permission()
        period = (
            get_object_or_404(ReportingPeriod, pk=period_id)
            if period_id
            else current_reporting_period()
        )
        if period is None:
            raise Http404("No reporting period available.")
        try:
            from openpyxl import Workbook
            from openpyxl.styles import Font, PatternFill
        except Exception as exc:
            return HttpResponse(f"openpyxl missing: {exc}", status=500)
        wb = Workbook()
        ws = wb.active
        ws.title = f"{period.name[:28]} Summary"
        headers = [
            "Group Code",
            "Group Name",
            "Team",
            "Revenue Target",
            "Revenue Actual",
            "Revenue %",
            "Revenue Deficit",
            "Profit Target",
            "Profit Actual",
            "Profit %",
            "Profit Deficit",
            "Margin Target %",
            "Margin Actual %",
            "Orders Target",
            "Orders Actual",
            "Orders %",
            "Deliveries Target",
            "Deliveries Achieved",
            "On-Time %",
        ]
        ws.append(headers)
        header_font = Font(bold=True, color="FFFFFF")
        header_fill = PatternFill("solid", fgColor="1F4E78")
        for col in range(1, len(headers) + 1):
            ws.cell(row=1, column=col).font = header_font
            ws.cell(row=1, column=col).fill = header_fill
        overall = overall_period_totals(period)
        currency = period.currency or DEFAULT_CURRENCY
        for row in overall["rows"]:
            ws.append(
                [
                    row["group"].code,
                    row["group"].name,
                    row["group"].team.name,
                    float(row["revenue_target"]),
                    float(row["revenue_actual"]),
                    float(row["revenue_pct"]),
                    float(row["revenue_deficit"]),
                    float(row["profit_target"]),
                    float(row["profit_actual"]),
                    float(row["profit_pct"]),
                    float(row["profit_deficit"]),
                    float(row["margin_pct_target"]),
                    float(row["margin_pct_actual"]),
                    row["orders_target"],
                    row["orders_actual"],
                    float(row["orders_pct"]),
                    row["deliveries_target"],
                    row["deliveries_achieved"],
                    float(row["on_time_pct"]),
                ]
            )
        # Totals row
        ws.append([])
        ws.append(
            [
                "OVERALL",
                "",
                period.name,
                float(overall["revenue_target"]),
                float(overall["revenue_actual"]),
                float(overall["revenue_pct"]),
                float(overall["revenue_deficit"]),
                float(overall["profit_target"]),
                float(overall["profit_actual"]),
                float(overall["profit_pct"]),
                float(overall["profit_deficit"]),
                "",
                "",
                overall["orders_target"],
                overall["orders_actual"],
                float(overall["orders_pct"]),
                overall["deliveries_target"],
                overall["deliveries_achieved"],
                float(overall["on_time_pct"]),
            ]
        )
        ws2 = wb.create_sheet("Notes")
        ws2.append(
            [
                "Reporting period",
                str(period),
            ]
        )
        ws2.append(["Cut-off date", period.cut_off_date.isoformat()])
        ws2.append(["Currency", currency])
        ws2.append(["Generated at (UTC)", datetime.now(UTC).isoformat()])
        ws2.append(["Exported by", request.user.get_display_name()])
        log_audit_event(
            record_type="sales_updates.reportingperiod",
            record=period,
            action=AuditLog.ACTION_EXPORT,
            user=request.user,
            reason=f"Excel export of {period.name}.",
        )
        buffer = BytesIO()
        wb.save(buffer)
        buffer.seek(0)
        filename = f"sales_{period.start_date.isoformat()}_{period.end_date.isoformat()}.xlsx"
        return StreamingHttpResponse(
            iter([buffer.read()]),
            content_type=("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )


class SnapshotPrintableView(LoginRequiredMixin, DetailView):
    """HTML fragment suitable for inclusion in meeting minutes (rule 16).

    Renders snapshot.totals + weekly commitments with a print-friendly layout
    — no sidebar navigation, plain tables, A4 width constrained in CSS.
    """

    model = GroupPerformanceSnapshot
    template_name = "sales_updates/snapshot_printable.html"
    context_object_name = "snapshot"

    def dispatch(self, request, *args, **kwargs):
        if not can_view_sales_period(request.user):
            return self.handle_no_permission()
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return super().get_queryset().select_related("group", "period", "meeting")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        from apps.sales_updates.services import weekly_commitment_totals

        ctx["weekly_totals"] = weekly_commitment_totals(self.object)
        ctx["currency"] = self.object.currency or self.object.period.currency or DEFAULT_CURRENCY
        return ctx


# ---------------------------------------------------------------------------
# Expose dashboard helper (lazy import from core.views.home)
# ---------------------------------------------------------------------------

__all__ = ["sales_dashboard_data"]
