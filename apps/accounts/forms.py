from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import (
    PasswordChangeForm as DjangoPasswordChangeForm,
)
from django.contrib.auth.forms import (
    UserChangeForm as DjangoUserChangeForm,
)
from django.contrib.auth.forms import (
    UserCreationForm as DjangoUserCreationForm,
)
from django.core.exceptions import ValidationError

from .models import Department, DepartmentMembership, Position

User = get_user_model()


class UserCreateForm(DjangoUserCreationForm):
    first_name = forms.CharField(max_length=150, required=False)
    last_name = forms.CharField(max_length=150, required=False)
    email = forms.EmailField(required=True)
    groups = forms.ModelMultipleChoiceField(
        queryset=None,
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Roles (Groups)",
    )

    class Meta:
        model = User
        fields = [
            "username",
            "email",
            "first_name",
            "last_name",
            "display_name",
            "initials",
            "phone",
            "signature_text",
            "is_active",
            "groups",
            "theme",
            "bio",
        ]

    def __init__(self, *args, **kwargs):
        from django.contrib.auth.models import Group

        super().__init__(*args, **kwargs)
        self.fields["groups"].queryset = Group.objects.order_by("name")
        for name in ["username", "email", "password1", "password2"]:
            if name in self.fields:
                self.fields[name].widget.attrs["class"] = "form-control"
        for fname, f in self.fields.items():
            if fname in {"groups"}:
                continue
            if isinstance(f.widget, forms.CheckboxInput):
                continue
            f.widget.attrs.setdefault("class", "form-control")


class UserUpdateForm(DjangoUserChangeForm):
    password = None  # hide auto-generated password widget; use dedicated password change view

    class Meta:
        model = User
        fields = [
            "username",
            "email",
            "first_name",
            "last_name",
            "display_name",
            "initials",
            "phone",
            "signature_text",
            "is_active",
            "is_staff",
            "groups",
            "theme",
            "bio",
        ]
        widgets = {
            "groups": forms.CheckboxSelectMultiple,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for fname, f in self.fields.items():
            if fname in {"groups"}:
                continue
            if isinstance(f.widget, (forms.CheckboxInput, forms.SelectMultiple)):
                continue
            f.widget.attrs.setdefault("class", "form-control")


class ProfileUpdateForm(forms.ModelForm):
    class Meta:
        model = User
        fields = [
            "display_name",
            "initials",
            "first_name",
            "last_name",
            "phone",
            "signature_text",
            "theme",
            "bio",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in self.fields.values():
            if isinstance(f.widget, forms.CheckboxInput):
                continue
            f.widget.attrs.setdefault("class", "form-control")


class PasswordChangeForm(DjangoPasswordChangeForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in self.fields.values():
            f.widget.attrs.setdefault("class", "form-control")


class DepartmentMembershipForm(forms.ModelForm):
    class Meta:
        model = DepartmentMembership
        fields = [
            "department",
            "position",
            "is_primary",
            "is_contributor",
            "is_active",
            "date_joined",
            "notes",
        ]

    def __init__(self, *args, **kwargs):
        self.for_user = kwargs.pop("for_user", None)
        super().__init__(*args, **kwargs)
        for fname, f in self.fields.items():
            if fname in {"is_primary", "is_contributor", "is_active"}:
                continue
            f.widget.attrs.setdefault("class", "form-control")
        self.fields["department"].queryset = Department.objects.filter(is_active=True).order_by(
            "name"
        )
        self.fields["position"].queryset = Position.objects.filter(is_active=True).order_by(
            "level", "name"
        )

    def clean(self):
        cleaned_data = super().clean()
        user = self.for_user or (self.instance and self.instance.user)
        if user and not getattr(user, "is_active", True) and cleaned_data.get("is_active"):
            raise ValidationError(
                "Cannot create or activate a departmental assignment for an inactive user. "
                "First re-activate the user account."
            )
        return cleaned_data


DepartmentMembershipFormSet = forms.inlineformset_factory(
    User,
    DepartmentMembership,
    form=DepartmentMembershipForm,
    extra=1,
    can_delete=True,
    fields=DepartmentMembershipForm.Meta.fields,
    fk_name="user",
)


def build_membership_formset(instance, data=None, **kwargs):
    """Build an inline formset that validates no new assignments on inactive users."""

    FormsetCls = forms.inlineformset_factory(
        User,
        DepartmentMembership,
        form=DepartmentMembershipForm,
        extra=1,
        can_delete=True,
        fields=DepartmentMembershipForm.Meta.fields,
        fk_name="user",
    )

    def _construct_form(formset, i, **form_kwargs):
        form_kwargs.setdefault("for_user", instance)
        return super(FormsetCls, formset)._construct_form(i, **form_kwargs)  # type: ignore[arg-type]

    FormsetCls._construct_form = _construct_form  # type: ignore[attr-defined]
    return FormsetCls(data, instance=instance, **kwargs)
