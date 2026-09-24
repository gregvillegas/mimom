from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from apps.core.models import TimeStampedModel

PERIOD_DRAFT = "DRAFT"
PERIOD_OPEN = "OPEN"
PERIOD_CLOSED = "CLOSED"

PERIOD_STATUS_CHOICES = [
    (PERIOD_DRAFT, "Draft"),
    (PERIOD_OPEN, "Open"),
    (PERIOD_CLOSED, "Closed"),
]

CURRENCY_PHP = "PHP"
CURRENCY_USD = "USD"
CURRENCY_EUR = "EUR"
CURRENCY_JPY = "JPY"

CURRENCY_CHOICES = [
    (CURRENCY_PHP, "Philippine Peso (₱)"),
    (CURRENCY_USD, "US Dollar ($)"),
    (CURRENCY_EUR, "Euro (€)"),
    (CURRENCY_JPY, "Japanese Yen (¥)"),
]

CURRENCY_SYMBOLS = {
    CURRENCY_PHP: "₱",
    CURRENCY_USD: "$",
    CURRENCY_EUR: "€",
    CURRENCY_JPY: "¥",
}

DEFAULT_CURRENCY = CURRENCY_PHP
DECIMAL_DIGITS = Decimal("0.01")
ZERO_DECIMAL = Decimal("0.00")


class ReportingPeriod(TimeStampedModel):
    name = models.CharField(max_length=120, help_text="e.g. Q3 2026 Week 1-4")
    start_date = models.DateField(db_index=True)
    end_date = models.DateField(db_index=True)
    cut_off_date = models.DateField(help_text="Final submission date for performance figures.")
    weeks_count = models.PositiveSmallIntegerField(
        default=4,
        help_text="Number of reporting weeks in this period (4 or 5).",
    )
    status = models.CharField(
        max_length=8,
        choices=PERIOD_STATUS_CHOICES,
        default=PERIOD_DRAFT,
        db_index=True,
    )
    currency = models.CharField(
        max_length=3,
        choices=CURRENCY_CHOICES,
        default=DEFAULT_CURRENCY,
    )
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sales_periods_created",
    )

    class Meta(TimeStampedModel.Meta):
        ordering = ["-start_date"]
        unique_together = [["start_date", "end_date"]]
        verbose_name_plural = "Reporting periods"

    def __str__(self) -> str:
        return f"{self.name} ({self.start_date:%Y-%m-%d} → {self.end_date:%Y-%m-%d})"

    def clean(self):
        if self.end_date <= self.start_date:
            raise ValidationError("end_date must be after start_date.")
        if self.cut_off_date < self.start_date or self.cut_off_date > self.end_date:
            raise ValidationError("cut_off_date must fall inside the reporting period.")
        if self.weeks_count not in (4, 5):
            raise ValidationError("weeks_count must be 4 or 5.")
        expected = (self.end_date - self.start_date).days + 1
        if expected < self.weeks_count * 7:
            raise ValidationError(
                f"Date span is too short for {self.weeks_count}-week reporting period."
            )

    @property
    def is_open(self) -> bool:
        return self.status == PERIOD_OPEN

    @property
    def is_locked(self) -> bool:
        return self.status == PERIOD_CLOSED

    @property
    def days_until_cutoff(self) -> int:
        today = timezone.now().date()
        return (self.cut_off_date - today).days


class SalesTeam(TimeStampedModel):
    name = models.CharField(max_length=120)
    code = models.CharField(max_length=20, unique=True, db_index=True)
    leader = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="led_sales_teams",
    )
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta(TimeStampedModel.Meta):
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.code})"


class SalesGroup(TimeStampedModel):
    name = models.CharField(max_length=120)
    code = models.CharField(max_length=20, unique=True, db_index=True)
    team = models.ForeignKey(
        SalesTeam,
        on_delete=models.CASCADE,
        related_name="groups",
    )
    manager = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="managed_sales_groups",
    )
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta(TimeStampedModel.Meta):
        ordering = ["team__name", "name"]
        unique_together = [["team", "code"]]

    def __str__(self) -> str:
        return f"{self.team.code} / {self.name} ({self.code})"


def _default_joined_on():
    return timezone.now().date()


class SalesGroupMembership(TimeStampedModel):
    group = models.ForeignKey(
        SalesGroup,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    user = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="sales_group_memberships",
    )
    role = models.CharField(
        max_length=40,
        default="Sales Representative",
        help_text="Role within the sales group (for display only).",
    )
    is_active = models.BooleanField(default=True, db_index=True)
    joined_on = models.DateField(default=_default_joined_on)
    left_on = models.DateField(null=True, blank=True)

    class Meta(TimeStampedModel.Meta):
        ordering = ["group__name", "user__username"]
        unique_together = [["group", "user"]]

    def __str__(self) -> str:
        return f"{self.user.get_display_name()} in {self.group.name}"

    def clean(self):
        if self.left_on and self.joined_on and self.left_on < self.joined_on:
            raise ValidationError("left_on cannot be before joined_on.")
        if not getattr(self.user, "is_active", True):
            raise ValidationError(f"{self.user.get_display_name()} is inactive.")


class PerformanceTarget(TimeStampedModel):
    group = models.ForeignKey(
        SalesGroup,
        on_delete=models.CASCADE,
        related_name="performance_targets",
    )
    period = models.ForeignKey(
        ReportingPeriod,
        on_delete=models.CASCADE,
        related_name="performance_targets",
    )
    revenue_target = models.DecimalField(max_digits=16, decimal_places=2, default=ZERO_DECIMAL)
    profit_target = models.DecimalField(max_digits=16, decimal_places=2, default=ZERO_DECIMAL)
    orders_target = models.PositiveIntegerField(default=0)
    deliveries_target = models.PositiveIntegerField(default=0)
    currency = models.CharField(
        max_length=3,
        choices=CURRENCY_CHOICES,
        default=DEFAULT_CURRENCY,
    )
    last_modified_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sales_targets_modified",
    )

    class Meta(TimeStampedModel.Meta):
        ordering = ["period__start_date", "group__name"]
        unique_together = [["group", "period"]]

    def __str__(self) -> str:
        return f"Targets {self.group.code} / {self.period.name}"

    @property
    def margin_pct_target(self) -> Decimal:
        if self.revenue_target <= 0:
            return ZERO_DECIMAL
        ratio = (self.profit_target / self.revenue_target) * Decimal("100")
        return ratio.quantize(DECIMAL_DIGITS)


class DeliveryPerformance(TimeStampedModel):
    group = models.ForeignKey(
        SalesGroup,
        on_delete=models.CASCADE,
        related_name="delivery_performances",
    )
    period = models.ForeignKey(
        ReportingPeriod,
        on_delete=models.CASCADE,
        related_name="delivery_performances",
    )
    deliveries_planned = models.PositiveIntegerField(default=0)
    deliveries_achieved = models.PositiveIntegerField(default=0)
    deliveries_on_time = models.PositiveIntegerField(default=0)
    notes = models.TextField(blank=True)
    last_modified_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="delivery_performances_modified",
    )

    class Meta(TimeStampedModel.Meta):
        ordering = ["period__start_date", "group__name"]
        unique_together = [["group", "period"]]

    def __str__(self) -> str:
        return f"Deliveries {self.group.code} / {self.period.name}"

    def clean(self):
        if self.deliveries_achieved > self.deliveries_planned and self.deliveries_planned:
            raise ValidationError("deliveries_achieved cannot exceed deliveries_planned.")
        if self.deliveries_on_time > self.deliveries_achieved:
            raise ValidationError("deliveries_on_time cannot exceed deliveries_achieved.")

    @property
    def on_time_pct(self) -> Decimal:
        if self.deliveries_achieved <= 0:
            return ZERO_DECIMAL
        ratio = (Decimal(self.deliveries_on_time) / Decimal(self.deliveries_achieved)) * Decimal(
            "100"
        )
        return ratio.quantize(DECIMAL_DIGITS)

    @property
    def delivery_achievement_pct(self) -> Decimal:
        if self.deliveries_planned <= 0:
            return ZERO_DECIMAL
        ratio = (Decimal(self.deliveries_achieved) / Decimal(self.deliveries_planned)) * Decimal(
            "100"
        )
        return ratio.quantize(DECIMAL_DIGITS)


class SalesOrderPerformance(TimeStampedModel):
    group = models.ForeignKey(
        SalesGroup,
        on_delete=models.CASCADE,
        related_name="sales_order_performances",
    )
    period = models.ForeignKey(
        ReportingPeriod,
        on_delete=models.CASCADE,
        related_name="sales_order_performances",
    )
    revenue_actual = models.DecimalField(max_digits=16, decimal_places=2, default=ZERO_DECIMAL)
    profit_actual = models.DecimalField(max_digits=16, decimal_places=2, default=ZERO_DECIMAL)
    orders_actual = models.PositiveIntegerField(default=0)
    currency = models.CharField(
        max_length=3,
        choices=CURRENCY_CHOICES,
        default=DEFAULT_CURRENCY,
    )
    notes = models.TextField(blank=True)
    last_modified_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sales_orders_modified",
    )

    class Meta(TimeStampedModel.Meta):
        ordering = ["period__start_date", "group__name"]
        unique_together = [["group", "period"]]

    def __str__(self) -> str:
        return f"Actuals {self.group.code} / {self.period.name}"

    @property
    def margin_pct_actual(self) -> Decimal:
        if self.revenue_actual <= 0:
            return ZERO_DECIMAL
        ratio = (self.profit_actual / self.revenue_actual) * Decimal("100")
        return ratio.quantize(DECIMAL_DIGITS)


class WeeklyCommitment(TimeStampedModel):
    """One row per week inside a snapshot — never hard-code 4 columns (Rule 44)."""

    snapshot = models.ForeignKey(
        "GroupPerformanceSnapshot",
        on_delete=models.CASCADE,
        related_name="weekly_commitments",
    )
    week_number = models.PositiveSmallIntegerField(
        help_text="1-indexed week inside the reporting period."
    )
    committed_revenue = models.DecimalField(max_digits=16, decimal_places=2, default=ZERO_DECIMAL)
    committed_profit = models.DecimalField(max_digits=16, decimal_places=2, default=ZERO_DECIMAL)
    actual_revenue = models.DecimalField(
        max_digits=16,
        decimal_places=2,
        default=ZERO_DECIMAL,
        blank=True,
        help_text="Optional, filled after week completes.",
    )
    actual_profit = models.DecimalField(
        max_digits=16,
        decimal_places=2,
        default=ZERO_DECIMAL,
        blank=True,
    )
    notes = models.TextField(blank=True)

    class Meta(TimeStampedModel.Meta):
        ordering = ["snapshot__period__start_date", "week_number"]
        unique_together = [["snapshot", "week_number"]]

    def __str__(self) -> str:
        return (
            f"{self.snapshot.group.code} W{self.week_number} (period {self.snapshot.period.name})"
        )

    def clean(self):
        try:
            weeks = self.snapshot.period.weeks_count
        except Exception:
            weeks = 5
        if self.week_number < 1 or self.week_number > weeks:
            raise ValidationError(f"week_number must be between 1 and {weeks} for this period.")


class GroupPerformanceSnapshot(TimeStampedModel):
    """Justified persisted snapshot (Rule 46) — freezes numbers for meeting minutes.

    Values here are copied at snapshot creation from the target/delivery/sales-order
    + WeeklyCommitment rows, so subsequent edits to source records do NOT change
    the approved snapshot printed in meeting minutes.
    """

    group = models.ForeignKey(
        SalesGroup,
        on_delete=models.CASCADE,
        related_name="snapshots",
    )
    period = models.ForeignKey(
        ReportingPeriod,
        on_delete=models.CASCADE,
        related_name="snapshots",
    )
    meeting = models.ForeignKey(
        "meetings.Meeting",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sales_snapshots",
        help_text="Meeting whose minutes embed this snapshot.",
    )
    revenue_target = models.DecimalField(max_digits=16, decimal_places=2, default=ZERO_DECIMAL)
    revenue_actual = models.DecimalField(max_digits=16, decimal_places=2, default=ZERO_DECIMAL)
    profit_target = models.DecimalField(max_digits=16, decimal_places=2, default=ZERO_DECIMAL)
    profit_actual = models.DecimalField(max_digits=16, decimal_places=2, default=ZERO_DECIMAL)
    orders_target = models.PositiveIntegerField(default=0)
    orders_actual = models.PositiveIntegerField(default=0)
    deliveries_target = models.PositiveIntegerField(default=0)
    deliveries_achieved = models.PositiveIntegerField(default=0)
    deliveries_on_time = models.PositiveIntegerField(default=0)
    currency = models.CharField(
        max_length=3,
        choices=CURRENCY_CHOICES,
        default=DEFAULT_CURRENCY,
    )
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sales_snapshots_created",
    )

    class Meta(TimeStampedModel.Meta):
        ordering = ["period__start_date", "group__name", "-created_at"]
        unique_together = [["group", "period", "meeting"]]

    def __str__(self) -> str:
        suffix = f" @ {self.meeting.reference}" if self.meeting_id else ""
        return f"Snapshot {self.group.code} / {self.period.name}{suffix}"

    @property
    def is_locked(self) -> bool:
        if not self.meeting_id:
            return False
        try:
            from apps.meetings.models import NON_EDITABLE_STATUSES
        except Exception:
            NON_EDITABLE_STATUSES = set()
        return getattr(self.meeting, "status", None) in NON_EDITABLE_STATUSES

    @property
    def revenue_deficit(self) -> Decimal:
        return (self.revenue_actual - self.revenue_target).quantize(DECIMAL_DIGITS)

    @property
    def profit_deficit(self) -> Decimal:
        return (self.profit_actual - self.profit_target).quantize(DECIMAL_DIGITS)

    @property
    def revenue_pct_achieved(self) -> Decimal:
        if self.revenue_target <= 0:
            return ZERO_DECIMAL
        ratio = (self.revenue_actual / self.revenue_target) * Decimal("100")
        return ratio.quantize(DECIMAL_DIGITS)

    @property
    def profit_pct_achieved(self) -> Decimal:
        if self.profit_target <= 0:
            return ZERO_DECIMAL
        ratio = (self.profit_actual / self.profit_target) * Decimal("100")
        return ratio.quantize(DECIMAL_DIGITS)

    @property
    def margin_pct_actual(self) -> Decimal:
        if self.revenue_actual <= 0:
            return ZERO_DECIMAL
        ratio = (self.profit_actual / self.revenue_actual) * Decimal("100")
        return ratio.quantize(DECIMAL_DIGITS)
