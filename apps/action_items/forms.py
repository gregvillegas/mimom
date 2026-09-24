from __future__ import annotations

from datetime import timedelta

from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.accounts.models import Department
from apps.action_items.models import (
    NON_EDITABLE_STATUSES,
    PRIORITY_CHOICES,
    STATUS_CHOICES,
    STATUS_COMPLETED,
    STATUS_IN_PROGRESS,
    STATUS_OPEN,
    ActionItem,
    ActionItemAssignee,
    ActionItemAttachment,
    ActionItemUpdate,
)
from apps.action_items.services import (
    REQUIRE_ADMIN_TRANSITIONS,
    REQUIRE_REASON_TRANSITIONS,
    VALID_TRANSITIONS,
)
from apps.meetings.models import Meeting


class DateLocalInput(forms.DateInput):
    input_type = "date"

    def __init__(self, attrs=None):
        default = {"class": "form-control", "placeholder": "YYYY-MM-DD"}
        if attrs:
            default.update(attrs)
        super().__init__(attrs=default)


class ActionItemFormMixin:
    def _apply_lock(self, locked_notice: str):
        for field_name in list(self.fields.keys()):
            self.fields[field_name].disabled = True
            self.fields[field_name].help_text = locked_notice


class ActionItemCreateForm(forms.ModelForm, ActionItemFormMixin):
    class Meta:
        model = ActionItem
        fields = [
            "title",
            "description",
            "priority",
            "status",
            "progress_pct",
            "due_date",
            "department",
            "owner",
            "blockers",
            "next_steps",
        ]
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "priority": forms.Select(attrs={"class": "form-select"}),
            "status": forms.Select(attrs={"class": "form-select"}),
            "progress_pct": forms.NumberInput(
                attrs={"class": "form-control", "min": 0, "max": 100}
            ),
            "due_date": DateLocalInput(),
            "department": forms.Select(attrs={"class": "form-select"}),
            "owner": forms.Select(attrs={"class": "form-select"}),
            "blockers": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "next_steps": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
        }

    def __init__(self, *args, by_user=None, **kwargs):
        kwargs.pop("by_user", None)
        super().__init__(*args, **kwargs)
        from django.contrib.auth import get_user_model

        User = get_user_model()
        users = User.objects.filter(is_active=True).order_by("username")
        self.fields["owner"].queryset = users
        self.fields["department"].queryset = Department.objects.filter(is_active=True).order_by(
            "name"
        )
        if "status" in self.fields:
            allowed = [
                (s, label) for s, label in STATUS_CHOICES if s in {STATUS_OPEN, STATUS_IN_PROGRESS}
            ]
            self.fields["status"].choices = allowed
            self.initial.setdefault("status", STATUS_OPEN)
            self.initial.setdefault("due_date", (timezone.now() + timedelta(days=14)).date())

    def clean_progress_pct(self):
        val = self.cleaned_data.get("progress_pct", 0)
        if val < 0 or val > 100:
            raise ValidationError("Progress must be 0-100.")
        return val

    def clean(self):
        cleaned_data = super().clean()
        if (
            cleaned_data.get("status") == STATUS_COMPLETED
            and cleaned_data.get("progress_pct", 0) < 100
        ):
            self.add_error("progress_pct", "Progress must be 100% before marking complete.")
        blockers = (cleaned_data.get("blockers") or "").strip()
        if cleaned_data.get("status") == STATUS_COMPLETED and blockers:
            self.add_error("blockers", "Clear blockers before marking complete.")
        return cleaned_data


class ActionItemUpdateForm(ActionItemCreateForm):
    class Meta(ActionItemCreateForm.Meta):
        pass

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk and self.instance.status in NON_EDITABLE_STATUSES:
            self._apply_lock(
                f"This action item is {self.instance.get_status_display()} and is "
                "locked. Request an admin to reopen it to make changes."
            )


def build_assignees_formset(action_item: ActionItem, data=None, **kwargs):
    formset_class = forms.inlineformset_factory(
        ActionItem,
        ActionItemAssignee,
        fields=["user", "is_primary", "is_supporting", "notes"],
        extra=1,
        can_delete=True,
        fk_name="action_item",
    )
    formset = formset_class(data, instance=action_item, **kwargs)
    original_construct = formset._construct_form

    def _construct(i, **form_kwargs):
        form_kwargs.pop("for_user", None)
        form = original_construct(i, **form_kwargs)
        from django.contrib.auth import get_user_model

        User = get_user_model()
        form.fields["user"].queryset = User.objects.filter(is_active=True).order_by("username")
        form.fields["notes"].widget = forms.TextInput(attrs={"class": "form-control"})
        form.fields["is_primary"].widget.attrs.setdefault("class", "form-check-input")
        form.fields["is_supporting"].widget.attrs.setdefault("class", "form-check-input")
        return form

    formset._construct_form = _construct
    return formset


class ActionItemTransitionForm(forms.Form):
    target_status = forms.ChoiceField(
        choices=STATUS_CHOICES,
        widget=forms.Select(attrs={"class": "form-select"}),
        label="New status",
    )
    reason = forms.CharField(
        required=False,
        max_length=1000,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        help_text="Required only for reopening or cancelling Under Review items.",
    )

    def __init__(self, *args, action_item: ActionItem, by_user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.action_item = action_item
        current = action_item.status
        allowed_targets = VALID_TRANSITIONS.get(current, set())
        allowed_choices = [(s, label) for s, label in STATUS_CHOICES if s in allowed_targets]
        self.fields["target_status"].choices = allowed_choices
        from apps.core.permissions import ACTION_REOPEN_ROLES

        admin = bool(
            getattr(by_user, "is_superuser", False)
            or (by_user and by_user.has_role(*ACTION_REOPEN_ROLES))
        )
        if not admin:
            filtered = [
                (s, lbl) for s, lbl in allowed_choices if s not in REQUIRE_ADMIN_TRANSITIONS
            ]
            self.fields["target_status"].choices = filtered

    def clean(self):
        cleaned_data = super().clean()
        current = self.action_item.status
        target = cleaned_data.get("target_status")
        if not target:
            return cleaned_data
        if (current, target) in REQUIRE_REASON_TRANSITIONS and not (
            cleaned_data.get("reason") or ""
        ).strip():
            self.add_error(
                "reason",
                "A reason is required for this status change.",
            )
        from apps.core.permissions import ACTION_REOPEN_ROLES

        by_user = getattr(self, "by_user", None)
        if (
            target in REQUIRE_ADMIN_TRANSITIONS
            and not getattr(by_user, "is_superuser", False)
            and not (by_user and by_user.has_role(*ACTION_REOPEN_ROLES))
        ):
            self.add_error(
                "target_status",
                "Only System Administrator or Management Administrator may reopen items.",
            )
        return cleaned_data


class ActionItemCompleteForm(forms.Form):
    progress_pct = forms.IntegerField(
        initial=100,
        min_value=100,
        max_value=100,
        widget=forms.NumberInput(attrs={"class": "form-control-plaintext", "readonly": "readonly"}),
        label="Progress",
    )
    completion_summary = forms.CharField(
        required=True,
        max_length=2000,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 4}),
        label="Completion summary (added as an update)",
    )
    blockers_clear = forms.BooleanField(
        initial=False,
        required=True,
        label="I confirm the Blockers field has been cleared.",
    )


class ActionItemReopenForm(forms.Form):
    reason = forms.CharField(
        required=True,
        max_length=1000,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 4}),
        label="Reason for reopening",
    )
    new_priority = forms.ChoiceField(
        choices=PRIORITY_CHOICES,
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
        help_text="Optional. Leave as-is to keep the existing priority.",
    )
    new_due_date = forms.DateField(
        required=False,
        widget=DateLocalInput(),
        help_text="Optional. Pick a new deadline if the original no longer applies.",
    )


class ActionItemUpdateFormCreate(forms.ModelForm):
    class Meta:
        model = ActionItemUpdate
        fields = ["body", "attachment"]
        widgets = {
            "body": forms.Textarea(attrs={"class": "form-control", "rows": 4, "required": "true"}),
            "attachment": forms.ClearableFileInput(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, by_user=None, **kwargs):
        kwargs.pop("by_user", None)
        super().__init__(*args, **kwargs)
        self.fields["body"].required = True


class ActionItemAttachmentForm(forms.ModelForm):
    class Meta:
        model = ActionItemAttachment
        fields = ["file", "caption"]
        widgets = {
            "file": forms.ClearableFileInput(attrs={"class": "form-control", "required": "true"}),
            "caption": forms.TextInput(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, by_user=None, **kwargs):
        kwargs.pop("by_user", None)
        super().__init__(*args, **kwargs)
        self.fields["file"].required = True


class CarryForwardActionItemsForm(forms.Form):
    source_meeting = forms.ModelChoiceField(
        queryset=Meeting.objects.none(),
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
        label="Source meeting (optional)",
    )
    include_completed = forms.BooleanField(
        required=False,
        initial=False,
        label="Also carry COMPLETED items (by default they are skipped).",
    )
    include_cancelled = forms.BooleanField(
        required=False,
        initial=False,
        label="Also carry CANCELLED items (by default they are skipped).",
    )
    item_ids = forms.CharField(
        required=True,
        widget=forms.HiddenInput,
        help_text="Comma-separated list of action item UUIDs.",
    )
    reason = forms.CharField(
        required=False,
        max_length=1000,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 3}),
    )
    target_meeting = forms.ModelChoiceField(
        queryset=Meeting.objects.none(),
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
        label="Target meeting (optional)",
    )

    def __init__(self, *args, by_user=None, **kwargs):
        kwargs.pop("by_user", None)
        super().__init__(*args, **kwargs)
        meetings = (
            Meeting.objects.exclude(status__in={"ARCHIVED"})
            .select_related("type")
            .order_by("-start_at")
        )
        self.fields["source_meeting"].queryset = meetings
        self.fields["target_meeting"].queryset = meetings

    def clean_item_ids(self):
        raw = self.cleaned_data.get("item_ids") or ""
        cleaned_parts: list[str] = []
        for part in raw.split(","):
            part = part.strip()
            if part:
                cleaned_parts.append(part)
        if not cleaned_parts:
            raise ValidationError("Select at least one action item to carry forward.")
        return ",".join(cleaned_parts)
