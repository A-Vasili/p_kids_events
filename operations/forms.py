# This file defines the information people may submit through Popadoo forms and the checks applied
# before it is accepted.
# The forms keep browser input separate from trusted database values and return clear errors when
# information is incomplete or unsafe.
# Views use these forms so the same validation applies to normal pages and enhanced interactions.

from __future__ import annotations

from django import forms
from django.contrib.auth import get_user_model, password_validation
from django.contrib.auth.forms import UserCreationForm
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from accounts.models import CustomerProfile, WorkerProfile, phone_validator
from party_builder.models import (
    AddonExperience,
    Category,
    GuestPriceTier,
    PartyBuild,
    PartyPackage,
)

from .models import WorkerAvailability

User = get_user_model()


# This function handles apply form accessibility as part of this module’s workflow.
# It keeps the repeated decision in one place so callers receive the same result and controlled
# failure behaviour.
def apply_form_accessibility(form: forms.BaseForm) -> None:
    """Apply consistent classes and ARIA relationships to every form control."""

    for name, field in form.fields.items():
        widget = field.widget
        if isinstance(widget, forms.CheckboxInput):
            widget.attrs.setdefault("class", "form-check-input")
        elif isinstance(widget, forms.FileInput):
            widget.attrs.setdefault("class", "form-control")
            widget.attrs.setdefault("accept", "image/jpeg,image/png,image/webp")
        elif isinstance(widget, (forms.Select, forms.SelectMultiple)):
            widget.attrs.setdefault("class", "form-select")
        elif not widget.is_hidden:
            widget.attrs.setdefault("class", "form-control")

        element_id = widget.attrs.setdefault("id", f"id_{name}")
        if not widget.is_hidden:
            described_by = []
            if field.help_text:
                described_by.append(f"{element_id}_help")
            described_by.append(f"{element_id}_error")
            widget.attrs["aria-describedby"] = " ".join(described_by)


# This class groups the information and behaviour needed for accessible fields mixin.
# Keeping the related rules together makes the surrounding workflow easier to reuse and test.
class AccessibleFieldsMixin:
    """Add ARIA error state after Django has validated the bound form."""

    # This method handles full clean for the surrounding accessible fields mixin.
    # It keeps that responsibility close to the object while relying on the existing validation
    # and permission boundaries.
    def full_clean(self):
        super().full_clean()
        for name in self.errors:
            if name in self.fields and not self.fields[name].widget.is_hidden:
                self.fields[name].widget.attrs["aria-invalid"] = "true"


# This form collects and validates the information needed for accessible model form.
# It accepts only the fields shown to the person using the page and leaves trusted identities,
# prices, and permissions to the server.
class AccessibleModelForm(AccessibleFieldsMixin, forms.ModelForm):
    # This method handles init for the surrounding accessible model form.
    # It keeps that responsibility close to the object while relying on the existing validation
    # and permission boundaries.
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_form_accessibility(self)


# This form collects and validates the information needed for accessible form.
# It accepts only the fields shown to the person using the page and leaves trusted identities,
# prices, and permissions to the server.
class AccessibleForm(AccessibleFieldsMixin, forms.Form):
    # This method handles init for the surrounding accessible form.
    # It keeps that responsibility close to the object while relying on the existing validation
    # and permission boundaries.
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_form_accessibility(self)


# Worker portal forms -------------------------------------------------------

# This form collects and validates the information needed for owner worker creation form.
# It accepts only the fields shown to the person using the page and leaves trusted identities,
# prices, and permissions to the server.
class OwnerWorkerCreationForm(AccessibleFieldsMixin, UserCreationForm):
    """Create a worker through the protected owner workflow."""

    first_name = forms.CharField(max_length=150, required=True)
    last_name = forms.CharField(max_length=150, required=True)
    email = forms.EmailField(required=True)
    phone = forms.CharField(max_length=30, required=False, validators=[phone_validator])

    # This inner configuration tells Django how the surrounding record should be ordered,
    # labelled, indexed, or constrained.
    class Meta(UserCreationForm.Meta):
        model = User
        fields = (
            "username", "first_name", "last_name", "email", "phone",
            "password1", "password2",
        )

    # This method handles init for the surrounding owner worker creation form.
    # It keeps that responsibility close to the object while relying on the existing validation
    # and permission boundaries.
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].help_text = "This is the name the worker will use to sign in."
        self.fields["password1"].help_text = " ".join(
            password_validation.password_validators_help_texts()
        )
        self.fields["email"].widget.attrs["autocomplete"] = "email"
        self.fields["phone"].widget.attrs["autocomplete"] = "tel"
        self.fields["password1"].widget.attrs["autocomplete"] = "new-password"
        self.fields["password2"].widget.attrs["autocomplete"] = "new-password"
        apply_form_accessibility(self)

    # This validation prepares the submitted email and rejects values that would make the form
    # misleading or unsafe.
    def clean_email(self) -> str:
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account already uses this email address.")
        return email

    # This save step preserves the model’s business rules whenever the record is written, not only
    # when it comes from one particular form.
    @transaction.atomic
    def save(self, *, actor, commit=True):
        from .services.users import promote_to_worker

        user = super().save(commit=False)
        user.first_name = self.cleaned_data["first_name"].strip()
        user.last_name = self.cleaned_data["last_name"].strip()
        user.email = self.cleaned_data["email"]
        if not commit:
            return user

        user.save()
        profile, _ = CustomerProfile.objects.get_or_create(user=user)
        profile.phone = self.cleaned_data.get("phone", "").strip()
        profile.save(update_fields=["phone", "updated_at"])
        worker_profile = promote_to_worker(user, actor)
        worker_profile.display_name = user.get_full_name() or user.username
        worker_profile.phone = profile.phone
        worker_profile.save(update_fields=["display_name", "phone", "updated_at"])
        return user


# This form collects and validates the information needed for worker profile form.
# It accepts only the fields shown to the person using the page and leaves trusted identities,
# prices, and permissions to the server.
class WorkerProfileForm(AccessibleModelForm):
    # This inner configuration tells Django how the surrounding record should be ordered,
    # labelled, indexed, or constrained.
    class Meta:
        model = WorkerProfile
        fields = ("display_name", "phone")


# This form collects and validates the information needed for worker availability form.
# It accepts only the fields shown to the person using the page and leaves trusted identities,
# prices, and permissions to the server.
class WorkerAvailabilityForm(AccessibleModelForm):
    # This inner configuration tells Django how the surrounding record should be ordered,
    # labelled, indexed, or constrained.
    class Meta:
        model = WorkerAvailability
        fields = ("start_at", "end_at", "availability_type", "notes")
        widgets = {
            "start_at": forms.DateTimeInput(
                format="%Y-%m-%dT%H:%M",
                attrs={"type": "hidden", "data-datetime-input": ""},
            ),
            "end_at": forms.DateTimeInput(
                format="%Y-%m-%dT%H:%M",
                attrs={"type": "hidden", "data-datetime-input": ""},
            ),
            "notes": forms.TextInput(attrs={"placeholder": "Optional note"}),
        }


# Assignment forms ---------------------------------------------------------

# This form collects and validates the information needed for decline assignment form.
# It accepts only the fields shown to the person using the page and leaves trusted identities,
# prices, and permissions to the server.
class DeclineAssignmentForm(AccessibleForm):
    reason = forms.CharField(
        max_length=500,
        label="Reason for declining",
        help_text="This helps the owner understand availability and contact another worker.",
        widget=forms.Textarea(attrs={"rows": 4}),
    )


# This form collects and validates the information needed for manual assignment form.
# It accepts only the fields shown to the person using the page and leaves trusted identities,
# prices, and permissions to the server.
class ManualAssignmentForm(AccessibleForm):
    worker = forms.ModelChoiceField(queryset=WorkerProfile.objects.none())
    already_agreed = forms.BooleanField(
        required=False,
        label="The worker has already agreed; add directly to the confirmed schedule",
    )
    override_reason = forms.CharField(
        required=False,
        max_length=500,
        label="Conflict override reason",
        help_text="Required only when the chosen worker has a scheduling conflict.",
        widget=forms.Textarea(attrs={"rows": 3}),
    )

    # This method handles init for the surrounding manual assignment form.
    # It keeps that responsibility close to the object while relying on the existing validation
    # and permission boundaries.
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["worker"].queryset = WorkerProfile.objects.filter(
            is_active_worker=True,
            user__is_active=True,
            user__groups__name="Workers",
        ).select_related("user").distinct()


# Catalogue management forms ---------------------------------------------

# This class groups the information and behaviour needed for catalogue image mixin.
# Keeping the related rules together makes the surrounding workflow easier to reuse and test.
class CatalogueImageMixin:
    remove_image = forms.BooleanField(
        required=False,
        label="Remove the current image",
        help_text="The existing file is removed only after the record saves successfully.",
    )

    # This validation checks the record as a whole so combinations of fields cannot describe an
    # impossible or unsafe business state.
    def clean(self):
        cleaned = super().clean()
        image = cleaned.get("image") or getattr(self.instance, "image", None)
        alt_text = (cleaned.get("image_alt_text") or "").strip()
        if cleaned.get("remove_image"):
            image = None
            cleaned["image_alt_text"] = ""
        if image and not alt_text:
            self.add_error("image_alt_text", "Describe the image for visitors who cannot see it.")
        return cleaned


# This form collects and validates the information needed for category form.
# It accepts only the fields shown to the person using the page and leaves trusted identities,
# prices, and permissions to the server.
class CategoryForm(CatalogueImageMixin, AccessibleModelForm):
    # This inner configuration tells Django how the surrounding record should be ordered,
    # labelled, indexed, or constrained.
    class Meta:
        model = Category
        fields = (
            "name", "slug", "description", "parent", "image",
            "image_alt_text", "display_order", "is_active",
        )
        widgets = {"description": forms.Textarea(attrs={"rows": 4})}

    # This method handles init for the surrounding category form.
    # It keeps that responsibility close to the object while relying on the existing validation
    # and permission boundaries.
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        queryset = Category.objects.order_by("display_order", "name")
        if self.instance.pk:
            excluded_ids = {self.instance.pk}
            queue = list(self.instance.children.values_list("pk", flat=True))
            while queue:
                child_id = queue.pop()
                if child_id in excluded_ids:
                    continue
                excluded_ids.add(child_id)
                queue.extend(
                    Category.objects.filter(parent_id=child_id).values_list("pk", flat=True)
                )
            queryset = queryset.exclude(pk__in=excluded_ids)
            # When a submitted value is invalid because it creates a cycle, keep
            # that one choice in the bound queryset so the model can return the
            # clearer business-rule message instead of a generic invalid-choice error.
            submitted_parent = self.data.get("parent") if self.is_bound else None
            if submitted_parent and str(submitted_parent).isdigit():
                queryset = queryset | Category.objects.filter(pk=submitted_parent)
        self.fields["parent"].queryset = queryset.distinct()
        self.fields["parent"].empty_label = "Main category (no parent)"

    # This validation prepares the submitted name and rejects values that would make the form
    # misleading or unsafe.
    def clean_name(self) -> str:
        name = self.cleaned_data["name"].strip()
        if not name:
            raise forms.ValidationError("Enter a category name.")
        return name


# This form collects and validates the information needed for package form.
# It accepts only the fields shown to the person using the page and leaves trusted identities,
# prices, and permissions to the server.
class PackageForm(CatalogueImageMixin, AccessibleModelForm):
    # This inner configuration tells Django how the surrounding record should be ordered,
    # labelled, indexed, or constrained.
    class Meta:
        model = PartyPackage
        fields = (
            "name", "slug", "category", "short_description", "base_price",
            "duration_minutes", "included_guest_count", "included_experiences",
            "is_default", "is_active", "display_order", "image", "image_alt_text",
        )
        widgets = {"included_experiences": forms.Textarea(attrs={"rows": 6})}

    # This method handles init for the surrounding package form.
    # It keeps that responsibility close to the object while relying on the existing validation
    # and permission boundaries.
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        category_filter = Q(is_active=True)
        if self.instance.category_id:
            category_filter |= Q(pk=self.instance.category_id)
        self.fields["category"].required = True
        self.fields["category"].queryset = Category.objects.filter(
            category_filter
        ).order_by("display_order", "name")
        self.fields["category"].help_text = (
            "Choose the category or subcategory where customers will find this package."
        )
        self.fields["base_price"].label = "Fixed package price"
        self.fields["base_price"].help_text = (
            "This trusted server-side price includes the package capacity."
        )
        self.fields["included_guest_count"].label = "Package capacity"
        self.fields["included_guest_count"].help_text = (
            "Maximum number of children covered by this package."
        )
        self.fields["duration_minutes"].help_text = "Total package duration in minutes."
        self.fields["included_experiences"].help_text = (
            "List the experiences already included in the fixed package price."
        )


# This form collects and validates the information needed for guest price tier form.
# It accepts only the fields shown to the person using the page and leaves trusted identities,
# prices, and permissions to the server.
class GuestPriceTierForm(AccessibleModelForm):
    # This inner configuration tells Django how the surrounding record should be ordered,
    # labelled, indexed, or constrained.
    class Meta:
        model = GuestPriceTier
        fields = (
            "package", "label", "min_guests", "max_guests", "total_price",
            "is_default", "is_active", "display_order",
        )

    # This method handles init for the surrounding guest price tier form.
    # It keeps that responsibility close to the object while relying on the existing validation
    # and permission boundaries.
    def __init__(self, *args, package=None, **kwargs):
        super().__init__(*args, **kwargs)
        package_filter = Q(is_active=True)
        if self.instance.package_id:
            package_filter |= Q(pk=self.instance.package_id)
        self.fields["package"].queryset = PartyPackage.objects.filter(
            package_filter
        ).order_by("display_order", "name")
        if package is not None:
            self.fields["package"].initial = package
            self.fields["package"].disabled = True
            self.instance.package = package

    # This validation checks the record as a whole so combinations of fields cannot describe an
    # impossible or unsafe business state.
    def clean(self):
        cleaned = super().clean()
        package = cleaned.get("package") or self.instance.package
        minimum = cleaned.get("min_guests")
        maximum = cleaned.get("max_guests")
        active = cleaned.get("is_active")
        if minimum is not None and maximum is not None and maximum < minimum:
            self.add_error("max_guests", "Maximum guests must be at least the minimum.")
        if cleaned.get("is_default") and not active:
            self.add_error("is_active", "The default tier must remain active.")
        if package and active and minimum is not None and maximum is not None:
            overlaps = GuestPriceTier.objects.filter(
                package=package,
                is_active=True,
                min_guests__lte=maximum,
                max_guests__gte=minimum,
            )
            if self.instance.pk:
                overlaps = overlaps.exclude(pk=self.instance.pk)
            if overlaps.exists():
                raise forms.ValidationError(
                    "This guest range overlaps another active tier for the selected package."
                )
        return cleaned


# This form collects and validates the information needed for addon form.
# It accepts only the fields shown to the person using the page and leaves trusted identities,
# prices, and permissions to the server.
class AddonForm(CatalogueImageMixin, AccessibleModelForm):
    # This inner configuration tells Django how the surrounding record should be ordered,
    # labelled, indexed, or constrained.
    class Meta:
        model = AddonExperience
        fields = (
            "name", "slug", "category", "short_description", "price",
            "duration_minutes", "icon", "is_featured", "is_active",
            "display_order", "image", "image_alt_text",
        )

    # This method handles init for the surrounding addon form.
    # It keeps that responsibility close to the object while relying on the existing validation
    # and permission boundaries.
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        category_filter = Q(is_active=True)
        if self.instance.category_id:
            category_filter |= Q(pk=self.instance.category_id)
        self.fields["category"].required = True
        self.fields["category"].queryset = Category.objects.filter(
            category_filter
        ).order_by("display_order", "name")
        self.fields["category"].help_text = (
            "Choose the category or subcategory where customers will find this add-on."
        )


# User management forms ----------------------------------------------------

# This form collects and validates the information needed for owner creation form.
# It accepts only the fields shown to the person using the page and leaves trusted identities,
# prices, and permissions to the server.
class OwnerCreationForm(AccessibleFieldsMixin, UserCreationForm):
    """Collect a new Owner's sign-in details for the Administrator-only flow."""

    first_name = forms.CharField(max_length=150, required=True)
    last_name = forms.CharField(max_length=150, required=True)
    email = forms.EmailField(required=True)

    # This inner configuration tells Django how the surrounding record should be ordered,
    # labelled, indexed, or constrained.
    class Meta(UserCreationForm.Meta):
        model = User
        fields = (
            "username", "first_name", "last_name", "email",
            "password1", "password2",
        )

    # This method handles init for the surrounding owner creation form.
    # It keeps that responsibility close to the object while relying on the existing validation
    # and permission boundaries.
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].help_text = "This is the name the Owner will use to sign in."
        self.fields["password1"].help_text = " ".join(
            password_validation.password_validators_help_texts()
        )
        self.fields["email"].widget.attrs["autocomplete"] = "email"
        self.fields["password1"].widget.attrs["autocomplete"] = "new-password"
        self.fields["password2"].widget.attrs["autocomplete"] = "new-password"
        apply_form_accessibility(self)

    # This validation prepares the submitted email and rejects values that would make the form
    # misleading or unsafe.
    def clean_email(self) -> str:
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account already uses this email address.")
        return email

    # This save step preserves the model’s business rules whenever the record is written, not only
    # when it comes from one particular form.
    def save(self, *, actor, commit=True):
        if not commit:
            raise ValueError("Owner accounts must be saved in one protected transaction.")
        from .services.users import create_owner_account

        return create_owner_account(
            actor=actor,
            username=self.cleaned_data["username"],
            first_name=self.cleaned_data["first_name"],
            last_name=self.cleaned_data["last_name"],
            email=self.cleaned_data["email"],
            password=self.cleaned_data["password1"],
        )


# This form collects and validates the information needed for managed worker form.
# It accepts only the fields shown to the person using the page and leaves trusted identities,
# prices, and permissions to the server.
class ManagedWorkerForm(AccessibleModelForm):
    """Edit operational worker settings without touching customer profile data."""

    # This inner configuration tells Django how the surrounding record should be ordered,
    # labelled, indexed, or constrained.
    class Meta:
        model = WorkerProfile
        fields = ("display_name", "phone", "max_daily_parties", "notes_for_owner")
        widgets = {"notes_for_owner": forms.Textarea(attrs={"rows": 4})}


# Booking management forms -------------------------------------------------

# This form collects and validates the information needed for booking status form.
# It accepts only the fields shown to the person using the page and leaves trusted identities,
# prices, and permissions to the server.
class BookingStatusForm(AccessibleForm):
    status = forms.ChoiceField(choices=PartyBuild.Status.choices)
    note = forms.CharField(
        required=False,
        max_length=500,
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text="Optional internal reason recorded in the audit history.",
    )

    # This method handles init for the surrounding booking status form.
    # It keeps that responsibility close to the object while relying on the existing validation
    # and permission boundaries.
    def __init__(self, *args, booking: PartyBuild, **kwargs):
        self.booking = booking
        super().__init__(*args, **kwargs)
        allowed = {
            PartyBuild.Status.SUBMITTED: {PartyBuild.Status.CONTACTED, PartyBuild.Status.CANCELLED},
            PartyBuild.Status.CONTACTED: {PartyBuild.Status.CONFIRMED, PartyBuild.Status.CANCELLED},
            PartyBuild.Status.CONFIRMED: {PartyBuild.Status.COMPLETED, PartyBuild.Status.CANCELLED},
            PartyBuild.Status.COMPLETED: set(),
            PartyBuild.Status.CANCELLED: set(),
        }[booking.status]
        if booking.event_date > timezone.localdate():
            allowed.discard(PartyBuild.Status.COMPLETED)
        self.fields["status"].choices = [
            choice for choice in PartyBuild.Status.choices if choice[0] in allowed
        ]
        apply_form_accessibility(self)

    # This validation prepares the submitted status and rejects values that would make the form
    # misleading or unsafe.
    def clean_status(self) -> str:
        status = self.cleaned_data["status"]
        valid_values = {value for value, _label in self.fields["status"].choices}
        if status not in valid_values:
            raise forms.ValidationError("Choose a valid next booking status.")
        return status


# This form collects and validates the information needed for manual review form.
# It accepts only the fields shown to the person using the page and leaves trusted identities,
# prices, and permissions to the server.
class ManualReviewForm(AccessibleForm):
    reason = forms.CharField(
        max_length=500,
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text="Explain why this booking needs owner follow-up.",
    )


# Confirmation forms -------------------------------------------------------

# This form collects and validates the information needed for action confirmation form.
# It accepts only the fields shown to the person using the page and leaves trusted identities,
# prices, and permissions to the server.
class ActionConfirmationForm(AccessibleForm):
    confirmation = forms.BooleanField(
        required=True,
        label="I understand and want to continue",
    )
