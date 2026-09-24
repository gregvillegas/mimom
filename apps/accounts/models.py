from django.contrib.auth.models import (
    AbstractUser,
    BaseUserManager,
)
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import BaseNamedModel, TimeStampedModel


class UserManager(BaseUserManager):
    def _create_user(self, username, email, password, **extra_fields):
        if not username:
            raise ValueError("The username must be set")
        email = self.normalize_email(email) if email else ""
        user = self.model(username=username, email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(username, email, password, **extra_fields)

    def create_superuser(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)
        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")
        return self._create_user(username, email, password, **extra_fields)


class User(AbstractUser):
    email = models.EmailField(_("email address"), unique=True, blank=False)
    display_name = models.CharField(max_length=255, blank=True)
    initials = models.CharField(max_length=10, blank=True)
    is_active = models.BooleanField(default=True)
    phone = models.CharField(max_length=50, blank=True)
    signature_text = models.CharField(max_length=255, blank=True)
    theme = models.CharField(
        max_length=20,
        choices=[("auto", "Auto"), ("light", "Light"), ("dark", "Dark")],
        default="auto",
    )
    bio = models.TextField(blank=True)

    objects = UserManager()

    USERNAME_FIELD = "username"
    REQUIRED_FIELDS = ["email"]

    class Meta:
        ordering = ["username"]
        verbose_name = "User"
        verbose_name_plural = "Users"

    def __str__(self) -> str:
        return self.get_display_name()

    def get_display_name(self) -> str:
        if self.display_name:
            return self.display_name
        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}".strip()
        return self.username

    def get_initials(self) -> str:
        if self.initials:
            return self.initials.upper()
        parts = []
        if self.first_name:
            parts.append(self.first_name[0].upper())
        if self.last_name:
            parts.append(self.last_name[0].upper())
        if not parts:
            parts.append(self.username[:2].upper())
        return "".join(parts)

    def has_role(self, *group_names: str) -> bool:
        if self.is_superuser:
            return True
        if not self.is_active:
            return False
        normalized = {str(name).strip() for name in group_names if name}
        if not normalized:
            return False
        if not hasattr(self, "_role_group_cache"):
            self._role_group_cache = set(
                self.groups.values_list("name", flat=True).distinct().iterator()
            )
        return any(name in self._role_group_cache for name in normalized)

    def get_assigned_departments(self, *, active_only: bool = True):

        qs = Department.objects.filter(memberships__user=self)
        if active_only:
            qs = qs.filter(memberships__is_active=True, is_active=True)
        return qs.distinct()

    def get_primary_department(self):
        membership = (
            self.department_memberships.filter(is_primary=True, is_active=True)
            .select_related("department")
            .first()
        )
        return membership.department if membership else None

    def get_contributor_departments(self):
        if not self.is_active:
            return Department.objects.none()
        return (
            Department.objects.filter(
                memberships__user=self,
                memberships__is_active=True,
                memberships__is_contributor=True,
                is_active=True,
            )
            .distinct()
            .order_by("name")
        )

    def can_manage_users(self) -> bool:
        return self.has_role(
            "System Administrator",
            "Management Administrator",
        )

    def save(self, *args, **kwargs):
        if not self.display_name and (self.first_name or self.last_name):
            self.display_name = f"{self.first_name} {self.last_name}".strip()
        if hasattr(self, "_role_group_cache"):
            del self._role_group_cache
        super().save(*args, **kwargs)


class Department(BaseNamedModel):
    code = models.CharField(max_length=50, unique=True, blank=True)
    description = models.TextField(blank=True)
    head = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="departments_led",
    )
    parent = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="subdepartments",
    )

    class Meta(BaseNamedModel.Meta):
        verbose_name_plural = "Departments"


class Position(BaseNamedModel):
    code = models.CharField(max_length=50, unique=True, blank=True)
    description = models.TextField(blank=True)
    level = models.PositiveIntegerField(default=10, help_text="Lower = higher rank")

    class Meta(BaseNamedModel.Meta):
        verbose_name_plural = "Positions"
        ordering = ["level", "name"]


class ManagementTeam(BaseNamedModel):
    description = models.TextField(blank=True)
    members = models.ManyToManyField(
        User,
        through="ManagementTeamMembership",
        related_name="management_teams",
        blank=True,
    )

    class Meta(BaseNamedModel.Meta):
        verbose_name_plural = "Management Teams"


class ManagementTeamMembership(TimeStampedModel):
    team = models.ForeignKey(ManagementTeam, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="team_memberships")
    role = models.CharField(max_length=100, blank=True)
    date_joined = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        unique_together = [["team", "user"]]
        ordering = ["team", "user__username"]

    def __str__(self) -> str:
        status = "" if self.is_active else " (inactive)"
        return f"{self.user} @ {self.team}{status}"


class DepartmentMembership(TimeStampedModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="department_memberships")
    department = models.ForeignKey(Department, on_delete=models.CASCADE, related_name="memberships")
    position = models.ForeignKey(
        Position,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="department_memberships",
    )
    is_primary = models.BooleanField(default=False)
    is_contributor = models.BooleanField(
        default=False,
        help_text="User can submit department updates for meetings",
    )
    date_joined = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        unique_together = [["user", "department"]]
        ordering = ["department", "-is_primary", "user__username"]

    def __str__(self) -> str:
        status = "" if self.is_active else " (inactive)"
        return f"{self.user} in {self.department}{status}"
