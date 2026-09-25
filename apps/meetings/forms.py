from django import forms
from django.core.exceptions import ValidationError

from apps.accounts.models import Department
from apps.action_items.models import ActionItem
from apps.meetings.models import (
    ITEM_STATUS_CHOICES,
    NON_EDITABLE_STATUSES,
    SECTION_TYPE_CHOICES,
    STATUS_CHOICES,
    AgendaCategory,
    AgendaItem,
    AgendaItemAttachment,
    Meeting,
    MeetingAttachment,
    MeetingAttendance,
    MeetingType,
)
from apps.meetings.services import REQUIRE_REASON_TRANSITIONS, VALID_TRANSITIONS


class DateInput(forms.DateInput):
    input_type = "date"


class DateTimeLocalInput(forms.DateTimeInput):
    input_type = "datetime-local"

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("format", "%Y-%m-%dT%H:%M")
        super().__init__(*args, **kwargs)


class MeetingForm(forms.ModelForm):
    class Meta:
        model = Meeting
        fields = [
            "type",
            "title",
            "description",
            "start_at",
            "end_at",
            "location",
            "department",
            "chair",
            "notes",
            "is_locked",
        ]
        widgets = {
            "start_at": DateTimeLocalInput(attrs={"class": "form-control"}),
            "end_at": DateTimeLocalInput(attrs={"class": "form-control"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "notes": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "title": forms.TextInput(attrs={"class": "form-control"}),
            "location": forms.TextInput(attrs={"class": "form-control"}),
            "type": forms.Select(attrs={"class": "form-select"}),
            "department": forms.Select(attrs={"class": "form-select"}),
            "chair": forms.Select(attrs={"class": "form-select"}),
        }
        labels = {
            "start_at": "Start (local)",
            "end_at": "End (local)",
            "is_locked": "Lock draft (only admins may edit or transition)",
        }

    def __init__(self, *args, **kwargs):
        kwargs.pop("by_user", None)
        super().__init__(*args, **kwargs)
        from django.contrib.auth import get_user_model

        User = get_user_model()
        user_qs = User.objects.filter(is_active=True).order_by("username")
        if "chair" in self.fields:
            self.fields["chair"].queryset = user_qs
        if "department" in self.fields:
            self.fields["department"].queryset = Department.objects.filter(is_active=True).order_by(
                "name"
            )
        if "type" in self.fields:
            self.fields["type"].queryset = MeetingType.objects.filter(is_active=True).order_by(
                "name"
            )
        if self.instance and self.instance.pk and self.instance.status in NON_EDITABLE_STATUSES:
            locked_notice = (
                f"This meeting is {self.instance.get_status_display()} and cannot be edited directly. "
                "Use archive or request a correction via transition."
            )
            for field_name in list(self.fields.keys()):
                if field_name == "is_locked":
                    self.fields[field_name].disabled = True
                    self.fields[field_name].help_text = locked_notice
                    continue
                self.fields[field_name].disabled = True
                self.fields[field_name].help_text = locked_notice

    def clean(self):
        cleaned_data = super().clean()
        if self.instance and self.instance.pk and self.instance.status in NON_EDITABLE_STATUSES:
            raise ValidationError(
                "This meeting is locked. Changes are not allowed for Approved, Published, "
                "Closed or Archived meetings."
            )
        start = cleaned_data.get("start_at")
        end = cleaned_data.get("end_at")
        if start and end and end <= start:
            raise ValidationError("End time must be after start time.")
        return cleaned_data


class TransitionForm(forms.Form):
    target_status = forms.ChoiceField(
        choices=STATUS_CHOICES,
        label="Change meeting status to",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    reason = forms.CharField(
        required=False,
        label="Reason (required for corrections / returns)",
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 2}),
    )

    def __init__(self, *args, meeting: Meeting, by_user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.meeting = meeting
        self.by_user = by_user
        allowed = VALID_TRANSITIONS.get(meeting.status, set())
        from apps.core.permissions import REOPEN_AUTHORIZED_ROLES

        is_admin = bool(
            by_user
            and (
                getattr(by_user, "is_superuser", False)
                or by_user.has_role(*REOPEN_AUTHORIZED_ROLES)
            )
        )
        if not is_admin:
            allowed = {s for s in allowed if s not in {"ARCHIVED", "RETURNED"}}
        choices = [(val, label) for val, label in STATUS_CHOICES if val in allowed]
        self.fields["target_status"].choices = choices

    def clean(self):
        cleaned_data = super().clean()
        target = cleaned_data.get("target_status")
        reason = (cleaned_data.get("reason") or "").strip()
        current = self.meeting.status
        if (current, target) in REQUIRE_REASON_TRANSITIONS and not reason:
            raise ValidationError(
                "A clear reason is required to return this meeting for correction."
            )
        return cleaned_data


class MeetingAttendanceForm(forms.ModelForm):
    class Meta:
        model = MeetingAttendance
        fields = [
            "user",
            "is_invited",
            "is_attended",
            "rsvp_status",
            "arrived_at",
            "departed_at",
            "role_at_meeting",
            "notes",
        ]
        widgets = {
            "user": forms.Select(attrs={"class": "form-select"}),
            "arrived_at": DateTimeLocalInput(attrs={"class": "form-control"}),
            "departed_at": DateTimeLocalInput(attrs={"class": "form-control"}),
            "role_at_meeting": forms.TextInput(attrs={"class": "form-control"}),
            "notes": forms.Textarea(attrs={"class": "form-control", "rows": 1}),
        }

    def __init__(self, *args, **kwargs):
        self.for_user = kwargs.pop("for_user", None)
        super().__init__(*args, **kwargs)
        from django.contrib.auth import get_user_model

        self.fields["user"].queryset = (
            get_user_model().objects.filter(is_active=True).order_by("username")
        )

    def clean(self):
        cleaned_data = super().clean()
        arrived = cleaned_data.get("arrived_at")
        departed = cleaned_data.get("departed_at")
        if arrived and departed and departed < arrived:
            raise ValidationError("Departure must be at or after arrival time.")
        row_user = cleaned_data.get("user") or getattr(self.instance, "user", None)
        if (
            row_user
            and not getattr(row_user, "is_active", True)
            and (cleaned_data.get("is_attended") or cleaned_data.get("is_invited"))
        ):
            raise ValidationError(
                f"Cannot mark {row_user} as invited or attended because the user is inactive."
            )
        return cleaned_data


def build_attendance_formset(meeting: Meeting, data=None, **kwargs):
    formset_class = forms.inlineformset_factory(
        Meeting,
        MeetingAttendance,
        form=MeetingAttendanceForm,
        extra=1,
        can_delete=True,
        fields=MeetingAttendanceForm.Meta.fields,
        fk_name="meeting",
    )
    formset = formset_class(data, instance=meeting, **kwargs)
    original_construct = formset._construct_form

    def _construct(i, **form_kwargs):
        form_kwargs.setdefault("for_user", None)
        return original_construct(i, **form_kwargs)

    formset._construct_form = _construct
    return formset


class AgendaCategoryForm(forms.ModelForm):
    class Meta:
        model = AgendaCategory
        fields = ["name", "order", "scope_department", "description", "is_active"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "order": forms.NumberInput(attrs={"class": "form-control"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "scope_department": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["scope_department"].queryset = Department.objects.filter(
            is_active=True
        ).order_by("name")


class AgendaItemForm(forms.ModelForm):
    class Meta:
        model = AgendaItem
        fields = [
            "category",
            "order",
            "title",
            "discussion",
            "decision",
            "item_status",
            "owner",
            "department",
            "is_confidential",
            "parent_item",
            "time_allocated_minutes",
            "notes",
        ]
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control"}),
            "discussion": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "decision": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "notes": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "order": forms.NumberInput(attrs={"class": "form-control"}),
            "time_allocated_minutes": forms.NumberInput(attrs={"class": "form-control"}),
            "category": forms.Select(attrs={"class": "form-select"}),
            "owner": forms.Select(attrs={"class": "form-select"}),
            "department": forms.Select(attrs={"class": "form-select"}),
            "parent_item": forms.Select(attrs={"class": "form-select"}),
            "item_status": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, meeting=None, by_user=None, **kwargs):
        super().__init__(*args, **kwargs)
        from django.contrib.auth import get_user_model

        User = get_user_model()
        self.fields["owner"].queryset = User.objects.filter(is_active=True).order_by("username")
        self.fields["department"].queryset = Department.objects.filter(is_active=True).order_by(
            "name"
        )
        self.by_user = by_user
        if meeting is None and self.instance and self.instance.pk:
            meeting = getattr(self.instance, "meeting", None)
        if meeting is not None:
            self.fields["category"].queryset = AgendaCategory.objects.filter(
                is_active=True
            ).order_by("order", "name")
            self.fields["parent_item"].queryset = AgendaItem.objects.filter(
                meeting=meeting
            ).order_by("order")
        self.fields["item_status"].choices = ITEM_STATUS_CHOICES

    def clean(self):
        cleaned_data = super().clean()
        parent = cleaned_data.get("parent_item")
        if self.instance.pk and parent and parent.pk == self.instance.pk:
            raise ValidationError("An agenda item cannot be parent of itself.")
        return cleaned_data


class AgendaOrderForm(forms.Form):
    item_order = forms.CharField(
        widget=forms.HiddenInput,
        required=False,
        help_text="Comma-separated list of agenda item PKs in desired display order.",
    )

    def clean_item_order(self):
        raw = (self.cleaned_data.get("item_order") or "").strip()
        if not raw:
            return []
        parts = [p.strip() for p in raw.split(",") if p.strip()]
        import uuid

        parsed = []
        for p in parts:
            try:
                parsed.append(uuid.UUID(p))
            except ValueError as exc:
                raise ValidationError(f"Invalid agenda item reference: {p}") from exc
        return parsed


class MeetingAttachmentForm(forms.ModelForm):
    class Meta:
        model = MeetingAttachment
        fields = ["file", "display_name", "description", "is_confidential"]
        widgets = {
            "display_name": forms.TextInput(attrs={"class": "form-control"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "file": forms.FileInput(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, by_user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.by_user = by_user


class AgendaItemAttachmentForm(forms.ModelForm):
    class Meta:
        model = AgendaItemAttachment
        fields = ["file", "display_name", "description", "is_confidential"]
        widgets = {
            "display_name": forms.TextInput(attrs={"class": "form-control"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "file": forms.FileInput(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, by_user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.by_user = by_user


class MinutesEditorForm(forms.ModelForm):
    class Meta:
        model = Meeting
        fields = ["notes"]
        widgets = {
            "notes": forms.Textarea(attrs={"class": "form-control", "rows": 8}),
        }
        labels = {
            "notes": "Meeting Minutes / General Notes",
        }


class DiscussionDecisionInlineForm(forms.ModelForm):
    class Meta:
        model = AgendaItem
        fields = [
            "discussion",
            "decision",
            "item_status",
            "owner",
            "department",
            "is_confidential",
            "notes",
        ]
        widgets = {
            "discussion": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "decision": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "notes": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "owner": forms.Select(attrs={"class": "form-select"}),
            "department": forms.Select(attrs={"class": "form-select"}),
            "item_status": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from django.contrib.auth import get_user_model

        User = get_user_model()
        self.fields["owner"].queryset = User.objects.filter(is_active=True).order_by("username")
        self.fields["department"].queryset = Department.objects.filter(is_active=True).order_by(
            "name"
        )
        self.fields["item_status"].choices = ITEM_STATUS_CHOICES


class ReturnForCorrectionForm(forms.Form):
    reason = forms.CharField(
        required=True,
        label="Return Reason (required)",
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 3}),
    )
    section_types = forms.MultipleChoiceField(
        choices=SECTION_TYPE_CHOICES,
        required=False,
        label="Affected Sections (optional)",
        widget=forms.SelectMultiple(attrs={"class": "form-select", "size": 7}),
    )
    management_remarks = forms.CharField(
        required=False,
        label="Management Remarks",
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 2}),
    )


class DateLocalInputMinutes(forms.DateInput):
    input_type = "date"

    def __init__(self, attrs=None):
        default = {"class": "form-control", "placeholder": "YYYY-MM-DD"}
        if attrs:
            default.update(attrs)
        super().__init__(attrs=default)


class ActionItemCreateFromMinutesForm(forms.ModelForm):
    class Meta:
        model = ActionItem
        fields = [
            "title",
            "description",
            "owner",
            "priority",
            "due_date",
        ]
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "owner": forms.Select(attrs={"class": "form-select"}),
            "priority": forms.Select(attrs={"class": "form-select"}),
            "due_date": DateLocalInputMinutes(),
        }

    def __init__(self, *args, source_meeting=None, source_agenda_item=None, **kwargs):
        super().__init__(*args, **kwargs)
        from django.contrib.auth import get_user_model

        User = get_user_model()
        self.fields["owner"].queryset = User.objects.filter(is_active=True).order_by("username")
        self._source_meeting = source_meeting
        self._source_agenda_item = source_agenda_item
        if source_meeting is not None:
            self.instance.source_meeting = source_meeting
        if source_agenda_item is not None:
            self.instance.source_agenda_item = source_agenda_item
            if source_agenda_item.department_id and not self.instance.department_id:
                self.instance.department_id = source_agenda_item.department_id
            if source_agenda_item.owner_id and not self.instance.owner_id:
                self.initial.setdefault("owner", source_agenda_item.owner_id)
