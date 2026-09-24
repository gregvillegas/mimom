from decimal import Decimal

from django import forms
from django.utils import timezone

from apps.sales_updates.models import (
    DEFAULT_CURRENCY,
    DeliveryPerformance,
    GroupPerformanceSnapshot,
    PerformanceTarget,
    ReportingPeriod,
    SalesGroup,
    SalesGroupMembership,
    SalesOrderPerformance,
    SalesTeam,
    WeeklyCommitment,
)


class CurrencyDecimalField(forms.DecimalField):
    """2dp DecimalField with sensible defaults for money inputs."""

    def __init__(
        self,
        *,
        max_digits=16,
        decimal_places=2,
        min_value=Decimal("-999999999999.99"),
        max_value=Decimal("999999999999.99"),
        initial=Decimal("0.00"),
        **kwargs,
    ):
        super().__init__(
            max_digits=max_digits,
            decimal_places=decimal_places,
            min_value=min_value,
            max_value=max_value,
            initial=initial,
            widget=forms.NumberInput(attrs={"step": "0.01", "class": "form-control"}),
            **kwargs,
        )


class DateLocalInput(forms.DateInput):
    input_type = "date"


class ReportingPeriodForm(forms.ModelForm):
    class Meta:
        model = ReportingPeriod
        fields = [
            "name",
            "start_date",
            "end_date",
            "cut_off_date",
            "weeks_count",
            "status",
            "currency",
            "notes",
        ]
        widgets = {
            "start_date": DateLocalInput(attrs={"class": "form-control"}),
            "end_date": DateLocalInput(attrs={"class": "form-control"}),
            "cut_off_date": DateLocalInput(attrs={"class": "form-control"}),
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "weeks_count": forms.NumberInput(attrs={"class": "form-control", "min": 4, "max": 5}),
            "status": forms.Select(attrs={"class": "form-select"}),
            "currency": forms.Select(attrs={"class": "form-select"}),
            "notes": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        }

    def clean_weeks_count(self):
        val = self.cleaned_data.get("weeks_count")
        if val not in (4, 5):
            raise forms.ValidationError("Must be 4 or 5.")
        return val

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get("start_date")
        end = cleaned.get("end_date")
        cut = cleaned.get("cut_off_date")
        if start and end and end <= start:
            self.add_error("end_date", "end_date must be after start_date.")
        if start and cut and (cut < start or cut > end):
            self.add_error("cut_off_date", "cut_off_date must fall inside the period.")
        return cleaned


class SalesTeamForm(forms.ModelForm):
    class Meta:
        model = SalesTeam
        fields = ["name", "code", "leader", "description", "is_active"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "code": forms.TextInput(attrs={"class": "form-control"}),
            "leader": forms.Select(attrs={"class": "form-select"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


class SalesGroupForm(forms.ModelForm):
    class Meta:
        model = SalesGroup
        fields = ["name", "code", "team", "manager", "description", "is_active"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "code": forms.TextInput(attrs={"class": "form-control"}),
            "team": forms.Select(attrs={"class": "form-select"}),
            "manager": forms.Select(attrs={"class": "form-select"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


class SalesGroupMembershipForm(forms.ModelForm):
    class Meta:
        model = SalesGroupMembership
        fields = ["user", "role", "is_active", "joined_on", "left_on"]
        widgets = {
            "user": forms.Select(attrs={"class": "form-select"}),
            "role": forms.TextInput(attrs={"class": "form-control"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "joined_on": DateLocalInput(attrs={"class": "form-control"}),
            "left_on": DateLocalInput(attrs={"class": "form-control"}),
        }


def build_membership_formset(group: SalesGroup, data=None, **kwargs):
    fs = forms.inlineformset_factory(
        SalesGroup,
        SalesGroupMembership,
        form=SalesGroupMembershipForm,
        extra=1,
        can_delete=True,
        fk_name="group",
    )
    return fs(data, instance=group, **kwargs)


class PerformanceTargetForm(forms.ModelForm):
    revenue_target = CurrencyDecimalField(label="Revenue Target")
    profit_target = CurrencyDecimalField(label="Profit Target")

    class Meta:
        model = PerformanceTarget
        fields = [
            "group",
            "period",
            "revenue_target",
            "profit_target",
            "orders_target",
            "deliveries_target",
            "currency",
        ]
        widgets = {
            "group": forms.Select(attrs={"class": "form-select"}),
            "period": forms.Select(attrs={"class": "form-select"}),
            "orders_target": forms.NumberInput(attrs={"class": "form-control", "min": 0}),
            "deliveries_target": forms.NumberInput(attrs={"class": "form-control", "min": 0}),
            "currency": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from django.contrib.auth import get_user_model

        get_user_model()
        if "currency" in self.fields and not self.fields["currency"].initial:
            self.fields["currency"].initial = DEFAULT_CURRENCY


class DeliveryPerformanceForm(forms.ModelForm):
    class Meta:
        model = DeliveryPerformance
        fields = [
            "group",
            "period",
            "deliveries_planned",
            "deliveries_achieved",
            "deliveries_on_time",
            "notes",
        ]
        widgets = {
            "group": forms.Select(attrs={"class": "form-select"}),
            "period": forms.Select(attrs={"class": "form-select"}),
            "deliveries_planned": forms.NumberInput(attrs={"class": "form-control", "min": 0}),
            "deliveries_achieved": forms.NumberInput(attrs={"class": "form-control", "min": 0}),
            "deliveries_on_time": forms.NumberInput(attrs={"class": "form-control", "min": 0}),
            "notes": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        }

    def clean(self):
        cleaned = super().clean()
        planned = cleaned.get("deliveries_planned") or 0
        achieved = cleaned.get("deliveries_achieved") or 0
        ot = cleaned.get("deliveries_on_time") or 0
        if planned and achieved > planned:
            self.add_error("deliveries_achieved", "Cannot exceed deliveries_planned.")
        if ot > achieved:
            self.add_error("deliveries_on_time", "Cannot exceed deliveries_achieved.")
        return cleaned


class SalesOrderPerformanceForm(forms.ModelForm):
    revenue_actual = CurrencyDecimalField(label="Revenue Actual")
    profit_actual = CurrencyDecimalField(label="Profit Actual")

    class Meta:
        model = SalesOrderPerformance
        fields = [
            "group",
            "period",
            "revenue_actual",
            "profit_actual",
            "orders_actual",
            "currency",
            "notes",
        ]
        widgets = {
            "group": forms.Select(attrs={"class": "form-select"}),
            "period": forms.Select(attrs={"class": "form-select"}),
            "orders_actual": forms.NumberInput(attrs={"class": "form-control", "min": 0}),
            "currency": forms.Select(attrs={"class": "form-select"}),
            "notes": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        }


class WeeklyCommitmentForm(forms.ModelForm):
    committed_revenue = CurrencyDecimalField(label="Committed Revenue")
    committed_profit = CurrencyDecimalField(label="Committed Profit")
    actual_revenue = CurrencyDecimalField(label="Actual Revenue", required=False)
    actual_profit = CurrencyDecimalField(label="Actual Profit", required=False)

    class Meta:
        model = WeeklyCommitment
        fields = [
            "week_number",
            "committed_revenue",
            "committed_profit",
            "actual_revenue",
            "actual_profit",
            "notes",
        ]
        widgets = {
            "week_number": forms.NumberInput(attrs={"class": "form-control", "min": 1}),
            "notes": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
        }


def build_weekly_commitment_formset(snapshot: GroupPerformanceSnapshot, data=None, **kwargs):
    """Build a formset tailored to the number of weeks in snapshot.period."""
    extra = max(0, snapshot.period.weeks_count - snapshot.weekly_commitments.count())
    fs = forms.inlineformset_factory(
        GroupPerformanceSnapshot,
        WeeklyCommitment,
        form=WeeklyCommitmentForm,
        extra=extra,
        can_delete=False,
        fk_name="snapshot",
    )
    formset = fs(data, instance=snapshot, **kwargs)

    def _construct_form(i, **form_kwargs):
        form = formset.original_construct(i, **form_kwargs)
        if snapshot.period_id:
            form.fields["week_number"].widget.attrs["max"] = snapshot.period.weeks_count
        return form

    formset.original_construct = formset._construct_form
    formset._construct_form = _construct_form
    return formset


class SnapshotCreateForm(forms.Form):
    group = forms.ModelChoiceField(
        queryset=SalesGroup.objects.filter(is_active=True),
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    period = forms.ModelChoiceField(
        queryset=ReportingPeriod.objects.all(),
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    meeting = forms.ModelChoiceField(
        queryset=None,
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    reason = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 2}),
        help_text="Optional reason stored in the audit log.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.meetings.models import Meeting

        self.fields["meeting"].queryset = Meeting.objects.order_by("-start_at").all()
        today = timezone.now().date()
        current_period = ReportingPeriod.objects.filter(
            status="OPEN", start_date__lte=today, end_date__gte=today
        ).first()
        if current_period and not self.initial.get("period"):
            self.initial["period"] = current_period.pk
