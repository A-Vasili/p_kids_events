
# This file defines the information people may submit through Popadoo forms and the checks applied
# before it is accepted.
# The forms keep browser input separate from trusted database values and return clear errors when
# information is incomplete or unsafe.
# Views use these forms so the same validation applies to normal pages and enhanced interactions.

from __future__ import annotations

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.db import transaction

from .models import CustomerProfile


User = get_user_model()


# Apply consistent classes and accessible error/help relationships. Checkbox and standard widgets
# receive consistent classes, help/error references, and invalid-state markup.
def apply_form_control_classes(form: forms.BaseForm) -> None:
    """Apply consistent classes and accessible error/help relationships."""

    for name, field in form.fields.items():
        if isinstance(field.widget, forms.CheckboxInput):
            field.widget.attrs.setdefault("class", "form-check-input")
        else:
            field.widget.attrs.setdefault("class", "form-control")
        element_id = field.widget.attrs.get("id", f"id_{name}")
        field.widget.attrs.setdefault("id", element_id)
        field.widget.attrs["aria-describedby"] = f"{element_id}_help {element_id}_error"
        if form.is_bound and name in form.errors:
            field.widget.attrs["aria-invalid"] = "true"


# Public registration form; every new account starts as a normal customer. It binds only the
# declared fields to User, validates email, applies the shared accessible widget setup.
class SignUpForm(UserCreationForm):
    """Public registration form; every new account starts as a normal customer."""

    first_name = forms.CharField(max_length=150, required=True)
    last_name = forms.CharField(max_length=150, required=True)
    email = forms.EmailField(required=True)
    phone = forms.CharField(max_length=30, required=False)
    # This consent wording identifies the hosted company while keeping the same privacy choice and validation.
    privacy_consent = forms.BooleanField(
        required=True,
        label="I agree that P Kids Events may store these details for account and booking use.",
    )

    # Bind SignUpForm to User; expose 8 explicitly listed fields, beginning with username, first
    # name, last name, and email. These options are enforced by Django rather than by template
    # input.
    class Meta(UserCreationForm.Meta):
        model = User
        fields = (
            "username",
            "first_name",
            "last_name",
            "email",
            "phone",
            "password1",
            "password2",
            "privacy_consent",
        )

    # Configure SignUpForm at construction time: username, email, and phone receive browser
    # autocomplete hints, field guidance, widget attributes, and shared accessible styling. This
    # setup runs before validation and keeps dynamic choices or permissions tied to the current
    # instance.
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].help_text = "Used to sign in. It must be unique."
        self.fields["email"].widget.attrs["autocomplete"] = "email"
        self.fields["phone"].widget.attrs["autocomplete"] = "tel"
        apply_form_control_classes(self)

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
    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        user.first_name = self.cleaned_data["first_name"].strip()
        user.last_name = self.cleaned_data["last_name"].strip()
        if commit:
            user.save()
            profile, _ = CustomerProfile.objects.get_or_create(user=user)
            profile.phone = self.cleaned_data.get("phone", "").strip()
            profile.save(update_fields=["phone", "updated_at"])
        return user


# Django authentication with project styling and safe generic errors. It applies the shared
# accessible widget setup.
class PopadooAuthenticationForm(AuthenticationForm):
    """Django authentication with project styling and safe generic errors."""

    # Configure PopadooAuthenticationForm at construction time: username and password receive
    # browser autocomplete hints, widget attributes, and shared accessible styling. This setup runs
    # before validation and keeps dynamic choices or permissions tied to the current instance.
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].widget.attrs["autocomplete"] = "username"
        self.fields["password"].widget.attrs["autocomplete"] = "current-password"
        apply_form_control_classes(self)


# Edit the account identity and saved booking-autofill fields together. It binds only the declared
# fields to CustomerProfile, validates email, applies the shared accessible widget setup.
class ProfileForm(forms.ModelForm):
    """Edit the account identity and saved booking-autofill fields together."""

    first_name = forms.CharField(max_length=150, required=True)
    last_name = forms.CharField(max_length=150, required=True)
    email = forms.EmailField(required=True)

    # Bind ProfileForm to CustomerProfile; expose 7 explicitly listed fields, beginning with first
    # name, last name, email, and phone. These options are enforced by Django rather than by
    # template input.
    class Meta:
        model = CustomerProfile
        fields = (
            "first_name",
            "last_name",
            "email",
            "phone",
            "default_address",
            "default_postal_code",
            "preferred_language",
        )
        widgets = {
            "default_address": forms.TextInput(attrs={"autocomplete": "street-address"}),
            "default_postal_code": forms.TextInput(attrs={"autocomplete": "postal-code"}),
        }

    # Configure ProfileForm at construction time: first name, last name, and email receive shared
    # accessible styling. This setup runs before validation and keeps dynamic choices or permissions
    # tied to the current instance.
    def __init__(self, *args, user, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        if not self.is_bound:
            self.fields["first_name"].initial = user.first_name
            self.fields["last_name"].initial = user.last_name
            self.fields["email"].initial = user.email
        apply_form_control_classes(self)

    # This validation prepares the submitted email and rejects values that would make the form
    # misleading or unsafe.
    def clean_email(self) -> str:
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exclude(pk=self.user.pk).exists():
            raise forms.ValidationError("Another account already uses this email address.")
        return email

    # This save step preserves the model’s business rules whenever the record is written, not only
    # when it comes from one particular form.
    @transaction.atomic
    def save(self, commit=True):
        profile = super().save(commit=False)
        self.user.first_name = self.cleaned_data["first_name"].strip()
        self.user.last_name = self.cleaned_data["last_name"].strip()
        self.user.email = self.cleaned_data["email"]
        if commit:
            self.user.save(update_fields=["first_name", "last_name", "email"])
            profile.save()
        return profile
