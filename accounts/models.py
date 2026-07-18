# This file describes the business records stored by this part of Popadoo and the relationships
# between them.
# The models preserve important history and enforce rules that must remain true no matter which
# page changes the data.
# Views, forms, and services build on these records rather than keeping important information only
# in the browser.

from __future__ import annotations

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models


phone_validator = RegexValidator(
    regex=r"^\+?[0-9\s().-]{7,30}$",
    message="Enter a valid phone number.",
)
postal_code_validator = RegexValidator(
    regex=r"^[A-Za-z0-9][A-Za-z0-9\s-]{2,9}$",
    message="Enter a valid postal code.",
)


# This model represents customer profile as a stored Popadoo business record.
# Its relationships and validation keep the record meaningful when it is used by customer, worker,
# and management pages.
class CustomerProfile(models.Model):
    """Saved customer details used to prefill future party bookings."""

    # These named choices keep the allowed preferred language values consistent in the database,
    # forms, and page labels.
    class PreferredLanguage(models.TextChoices):
        ENGLISH = "en", "English"
        GREEK = "el", "Greek"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="customer_profile",
    )
    phone = models.CharField(max_length=30, blank=True, validators=[phone_validator])
    default_address = models.CharField(max_length=240, blank=True)
    default_postal_code = models.CharField(
        max_length=10,
        blank=True,
        validators=[postal_code_validator],
    )
    preferred_language = models.CharField(
        max_length=2,
        choices=PreferredLanguage.choices,
        default=PreferredLanguage.ENGLISH,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Order records by ('user__last_name', 'user__first_name', 'user__username'). These options are
    # enforced by Django rather than by template input.
    class Meta:
        ordering = ("user__last_name", "user__first_name", "user__username")

    # This method handles str for the surrounding customer profile.
    # It keeps that responsibility close to the object while relying on the existing validation
    # and permission boundaries.
    def __str__(self) -> str:
        return f"Customer profile: {self.user.get_full_name() or self.user.username}"


# This model represents worker profile as a stored Popadoo business record.
# Its relationships and validation keep the record meaningful when it is used by customer, worker,
# and management pages.
class WorkerProfile(models.Model):
    """Operational settings for users who can receive party assignments."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="worker_profile",
    )
    display_name = models.CharField(max_length=120, blank=True)
    phone = models.CharField(max_length=30, blank=True, validators=[phone_validator])
    is_active_worker = models.BooleanField(
        default=True,
        help_text="Inactive workers remain in history but receive no new assignments.",
    )
    max_daily_parties = models.PositiveSmallIntegerField(
        default=2,
        validators=[MinValueValidator(1), MaxValueValidator(10)],
    )
    notes_for_owner = models.TextField(
        blank=True,
        max_length=1000,
        help_text="Private operational notes visible only to owners and administrators.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Order records by ('display_name', 'user__username'). These options are enforced by Django
    # rather than by template input.
    class Meta:
        ordering = ("display_name", "user__username")
        permissions = [
            ("manage_worker_roles", "Can promote, demote, and activate workers"),
            ("manage_pricing_rights", "Can grant or revoke pricing-management rights"),
            ("view_all_worker_schedules", "Can view all worker schedules"),
        ]

    # This method handles str for the surrounding worker profile.
    # It keeps that responsibility close to the object while relying on the existing validation
    # and permission boundaries.
    def __str__(self) -> str:
        return self.display_name or self.user.get_full_name() or self.user.username
