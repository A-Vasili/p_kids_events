# This file defines the information people may submit through Popadoo forms and the checks applied
# before it is accepted.
# The forms keep browser input separate from trusted database values and return clear errors when
# information is incomplete or unsafe.
# Views use these forms so the same validation applies to normal pages and enhanced interactions.

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

from django import forms
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.utils import timezone

from .models import AddonExperience, Category, PartyPackage, PartyReview
from .services import SafePaymentResult


# This function handles apply accessible attributes as part of this module’s workflow.
# It keeps the repeated decision in one place so callers receive the same result and controlled
# failure behaviour.
def _apply_accessible_attributes(form: forms.BaseForm) -> None:
    """Connect every control to predictable help and error containers."""

    for field_name, field in form.fields.items():
        element_id = field.widget.attrs.get("id", f"id_{field_name}")
        field.widget.attrs.setdefault("id", element_id)
        if not field.widget.is_hidden:
            field.widget.attrs["aria-describedby"] = (
                f"{element_id}_help {element_id}_error"
            )

    if form.is_bound:
        for field_name in form.errors:
            if field_name in form.fields:
                form.fields[field_name].widget.attrs["aria-invalid"] = "true"


# This helper keeps category choices aligned with the kind of idea a visitor is browsing.
# Categories that contain no active matching records are left out, preventing filters that can
# only lead to an empty result page.
def _public_category_content_filter(idea_type: str) -> Q:
    package_content = Q(packages__is_active=True) | Q(
        children__is_active=True, children__packages__is_active=True
    )
    experience_content = Q(addons__is_active=True) | Q(
        children__is_active=True, children__addons__is_active=True
    )
    if idea_type == "package":
        return package_content
    if idea_type == "experience":
        return experience_content
    return package_content | experience_content


# This form collects and validates the information needed for party ideas filter form.
# It accepts only the fields shown to the person using the page and leaves trusted identities,
# prices, and permissions to the server.
class PartyIdeasFilterForm(forms.Form):
    """Validate public catalogue search and filter values from the URL."""

    TYPE_CHOICES = (
        ("all", "All ideas"),
        ("package", "Starting packages"),
        ("experience", "Experiences"),
    )
    DURATION_CHOICES = (
        ("", "Any duration"),
        ("short", "Up to 30 minutes"),
        ("medium", "31–60 minutes"),
        ("long", "More than 60 minutes"),
    )
    RATING_CHOICES = (
        ("", "Any rating"),
        ("3", "3+ stars"),
        ("4", "4+ stars"),
        ("4.5", "4.5+ stars"),
    )
    CAPACITY_CHOICES = (
        ("", "Any size"),
        ("10", "Up to 10 children"),
        ("15", "Up to 15 children"),
        ("20", "Up to 20 children"),
        ("25", "Up to 25 children"),
        ("30", "Up to 30 children"),
        ("35", "Up to 35 children"),
        ("40", "Up to 40 children"),
        ("50", "Up to 50 children"),
    )
    SORT_CHOICES = (
        ("recommended", "Recommended"),
        ("name", "Name A–Z"),
        ("price_asc", "Price: low to high"),
        ("price_desc", "Price: high to low"),
        ("capacity_asc", "Capacity: small to large"),
        ("capacity_desc", "Capacity: large to small"),
        ("rating", "Highest rated"),
        ("reviews", "Most reviewed"),
    )

    q = forms.CharField(
        required=False,
        max_length=120,
        label="Search party ideas",
        widget=forms.SearchInput(
            attrs={
                "class": "form-control",
                "placeholder": "Search by name, activity or category",
                "data-i18n-placeholder": "partyIdeas.search",
                "autocomplete": "off",
            }
        ),
    )
    type = forms.ChoiceField(
        required=False, choices=TYPE_CHOICES, initial="all", label="Idea type"
    )
    min_price = forms.DecimalField(
        required=False,
        min_value=Decimal("0.00"),
        max_digits=8,
        decimal_places=2,
        label="Minimum price",
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
    )
    max_price = forms.DecimalField(
        required=False,
        min_value=Decimal("0.00"),
        max_digits=8,
        decimal_places=2,
        label="Maximum price",
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
    )
    category = forms.ModelChoiceField(
        required=False,
        queryset=Category.objects.none(),
        to_field_name="slug",
        empty_label="All categories",
        label="Category",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    capacity = forms.ChoiceField(
        required=False,
        choices=CAPACITY_CHOICES,
        label="Minimum package capacity",
        help_text="Package results must hold at least this many children.",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    duration = forms.ChoiceField(
        required=False,
        choices=DURATION_CHOICES,
        label="Duration",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    min_rating = forms.ChoiceField(
        required=False,
        choices=RATING_CHOICES,
        label="Minimum rating",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    featured = forms.BooleanField(
        required=False, label="Featured experiences only"
    )
    sort = forms.ChoiceField(
        required=False,
        choices=SORT_CHOICES,
        initial="recommended",
        label="Sort results",
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    # This setup shows only categories that can produce the selected kind of idea. It prevents a
    # visitor from choosing a package-only category while browsing experiences, or an empty
    # category that cannot return anything.
    def __init__(self, *args, idea_type: str | None = None, allowed_types=None, **kwargs):
        super().__init__(*args, **kwargs)
        selected_type = idea_type or (self.data.get("type") if self.is_bound else None) or "all"
        if selected_type not in {value for value, _label in self.TYPE_CHOICES}:
            selected_type = "all"
        if allowed_types is not None:
            allowed_type_values = set(allowed_types)
            self.fields["type"].choices = [
                choice for choice in self.TYPE_CHOICES if choice[0] in allowed_type_values
            ]
        self.fields["category"].queryset = (
            Category.objects.filter(is_active=True)
            .filter(Q(parent__isnull=True) | Q(parent__is_active=True))
            .filter(_public_category_content_filter(selected_type))
            .distinct()
        )
        _apply_accessible_attributes(self)

    # This validation prepares the submitted q and rejects values that would make the form
    # misleading or unsafe.
    def clean_q(self) -> str:
        return self.cleaned_data["q"].strip()

    # This validation checks the record as a whole so combinations of fields cannot describe an
    # impossible or unsafe business state.
    def clean(self):
        cleaned = super().clean()
        minimum = cleaned.get("min_price")
        maximum = cleaned.get("max_price")
        if minimum is not None and maximum is not None and minimum > maximum:
            self.add_error("max_price", "Maximum price must be at least the minimum price.")
        return cleaned


# This form collects and validates the information needed for package options form.
# It accepts only the fields shown to the person using the page and leaves trusted identities,
# prices, and permissions to the server.
class PackageOptionsForm(forms.Form):
    """Validate one capacity-based package and its optional experiences."""

    package = forms.ModelChoiceField(
        queryset=PartyPackage.objects.none(),
        empty_label=None,
        widget=forms.RadioSelect,
        label="Package and party size",
    )
    addons = forms.ModelMultipleChoiceField(
        queryset=AddonExperience.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Optional experiences",
    )

    # This method handles init for the surrounding package options form.
    # It keeps that responsibility close to the object while relying on the existing validation
    # and permission boundaries.
    def __init__(self, *args, package: PartyPackage | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        visible_category = Q(category__parent__isnull=True) | Q(
            category__parent__is_active=True
        )
        self.fields["package"].queryset = (
            PartyPackage.objects.filter(is_active=True, category__is_active=True)
            .filter(visible_category)
            .order_by("display_order", "name")
        )
        self.fields["addons"].queryset = (
            AddonExperience.objects.filter(is_active=True, category__is_active=True)
            .filter(visible_category)
            .select_related("category", "category__parent")
            .order_by("display_order", "name")
        )
        if package and not self.is_bound:
            self.initial.setdefault("package", package.pk)
        _apply_accessible_attributes(self)


# This form collects and validates the information needed for party details form.
# It accepts only the fields shown to the person using the page and leaves trusted identities,
# prices, and permissions to the server.
class PartyDetailsForm(forms.Form):
    """Step two: collect customer and event details without saving yet."""

    contact_name = forms.CharField(
        max_length=120,
        label="Parent or guardian name",
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "autocomplete": "name",
                "placeholder": "Full name",
            }
        ),
    )
    contact_email = forms.EmailField(
        label="Email address",
        widget=forms.EmailInput(
            attrs={
                "class": "form-control",
                "autocomplete": "email",
                "placeholder": "name@example.com",
            }
        ),
    )
    contact_phone = forms.CharField(
        max_length=30,
        label="Phone number",
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "type": "tel",
                "autocomplete": "tel",
                "placeholder": "+30 69…",
            }
        ),
    )
    event_date = forms.DateField(
        label="Preferred event date",
        # The browser submits this hidden ISO value. The visible calendar is a
        # custom div-based control rendered by the template.
        widget=forms.DateInput(
            format="%Y-%m-%d",
            attrs={"type": "hidden", "data-custom-date-input": ""},
        ),
        help_text="Choose today or a future date. Availability is confirmed later.",
    )
    event_time = forms.TimeField(
        required=False,
        label="Preferred start time",
        # Keeping an HH:MM hidden value lets Django perform normal TimeField
        # validation without relying on the browser's visual component.
        widget=forms.TimeInput(
            format="%H:%M",
            attrs={"type": "hidden", "data-custom-time-input": ""},
        ),
    )
    event_address = forms.CharField(
        max_length=240,
        label="Event address",
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "autocomplete": "street-address",
                "placeholder": "Street, number, area",
            }
        ),
    )
    postal_code = forms.CharField(
        max_length=10,
        label="Postal code",
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "autocomplete": "postal-code",
                "inputmode": "numeric",
                "placeholder": "153 42",
            }
        ),
    )
    save_profile = forms.BooleanField(
        required=False,
        label="Save these details to my profile for future bookings",
    )
    notes = forms.CharField(
        required=False,
        max_length=1500,
        label="Extra details",
        help_text="Theme, age range, venue restrictions, or accessibility needs.",
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 5,
                "placeholder": "Tell us what would make the experience feel right.",
            }
        ),
    )

    # This method handles init for the surrounding party details form.
    # It keeps that responsibility close to the object while relying on the existing validation
    # and permission boundaries.
    def __init__(self, *args, show_save_profile=False, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        if not show_save_profile:
            self.fields.pop("save_profile", None)
        self.fields["event_date"].widget.attrs["data-min"] = date.today().isoformat()
        _apply_accessible_attributes(self)

    # This validation prepares the submitted contact phone and rejects values that would make the
    # form misleading or unsafe.
    def clean_contact_phone(self) -> str:
        phone = self.cleaned_data["contact_phone"].strip()
        digits = re.sub(r"\D", "", phone)
        if not re.fullmatch(r"\+?[0-9\s().-]+", phone) or not 7 <= len(digits) <= 15:
            raise forms.ValidationError("Enter a valid phone number.")
        return phone

    # This validation prepares the submitted event date and rejects values that would make the
    # form misleading or unsafe.
    def clean_event_date(self):
        event_date = self.cleaned_data["event_date"]
        if event_date < timezone.localdate():
            raise forms.ValidationError("Choose today or a future date.")
        return event_date


    # This validation prepares the submitted postal code and rejects values that would make the
    # form misleading or unsafe.
    def clean_postal_code(self) -> str:
        postal_code = self.cleaned_data["postal_code"].strip()
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9\s-]{2,9}", postal_code):
            raise forms.ValidationError("Enter a valid postal code.")
        return postal_code

    # This validation checks the record as a whole so combinations of fields cannot describe an
    # impossible or unsafe business state.
    def clean(self):
        cleaned_data = super().clean()
        if (
            self.user
            and getattr(self.user, "is_authenticated", False)
            and cleaned_data.get("save_profile")
            and cleaned_data.get("contact_email")
        ):
            User = get_user_model()
            email = cleaned_data["contact_email"].strip().lower()
            if User.objects.filter(email__iexact=email).exclude(pk=self.user.pk).exists():
                self.add_error(
                    "contact_email",
                    "Another account already uses this email address.",
                )
        return cleaned_data


# This form collects and validates the information needed for simulated payment form.
# It accepts only the fields shown to the person using the page and leaves trusted identities,
# prices, and permissions to the server.
class SimulatedPaymentForm(forms.Form):
    """Step three: validate test card details and discard sensitive values."""

    cardholder_name = forms.CharField(
        max_length=120,
        label="Name on test card",
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "autocomplete": "off",
            }
        ),
    )
    card_number = forms.CharField(
        min_length=13,
        max_length=23,
        label="Test card number",
        help_text="Simulation only. You may use 4242 4242 4242 4242.",
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "autocomplete": "off",
                "inputmode": "numeric",
                "data-card-number": "",
                "placeholder": "4242 4242 4242 4242",
            }
        ),
    )
    expiry_month = forms.ChoiceField(
        label="Expiry month",
        choices=[(f"{month:02d}", f"{month:02d}") for month in range(1, 13)],
        widget=forms.Select(attrs={"class": "form-control", "autocomplete": "cc-exp-month"}),
    )
    expiry_year = forms.ChoiceField(
        label="Expiry year",
        choices=(),
        widget=forms.Select(attrs={"class": "form-control", "autocomplete": "cc-exp-year"}),
    )
    security_code = forms.CharField(
        min_length=3,
        max_length=4,
        label="Security code",
        widget=forms.PasswordInput(
            render_value=False,
            attrs={
                "class": "form-control",
                "autocomplete": "off",
                "inputmode": "numeric",
                "placeholder": "123",
            },
        ),
    )
    billing_postal_code = forms.CharField(
        max_length=10,
        label="Billing postal code",
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "autocomplete": "postal-code",
                "inputmode": "numeric",
            }
        ),
    )
    simulation_consent = forms.BooleanField(
        required=True,
        label=(
            "I understand this is a simulated checkout and no payment or "
            "financial transaction will take place."
        ),
    )

    # This method handles init for the surrounding simulated payment form.
    # It keeps that responsibility close to the object while relying on the existing validation
    # and permission boundaries.
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        current_year = timezone.localdate().year
        self.fields["expiry_year"].choices = [
            (str(year), str(year)) for year in range(current_year, current_year + 11)
        ]
        _apply_accessible_attributes(self)

    # This method handles passes luhn for the surrounding simulated payment form.
    # It keeps that responsibility close to the object while relying on the existing validation
    # and permission boundaries.
    @staticmethod
    def _passes_luhn(number: str) -> bool:
        digits = [int(character) for character in number]
        checksum = 0
        parity = len(digits) % 2
        for index, digit in enumerate(digits):
            if index % 2 == parity:
                digit *= 2
                if digit > 9:
                    digit -= 9
            checksum += digit
        return checksum % 10 == 0

    # This method handles detect brand for the surrounding simulated payment form.
    # It keeps that responsibility close to the object while relying on the existing validation
    # and permission boundaries.
    @staticmethod
    def _detect_brand(number: str) -> str:
        if number.startswith("4"):
            return "Visa"
        if len(number) >= 2 and 51 <= int(number[:2]) <= 55:
            return "Mastercard"
        if number.startswith(("34", "37")):
            return "American Express"
        return "Test card"

    # This validation prepares the submitted card number and rejects values that would make the
    # form misleading or unsafe.
    def clean_card_number(self) -> str:
        number = re.sub(r"\D", "", self.cleaned_data["card_number"])
        approved_test_numbers = {
            "4242424242424242",
            "5555555555554444",
            "378282246310005",
        }
        if number not in approved_test_numbers or not self._passes_luhn(number):
            raise forms.ValidationError(
                "Use an approved demo number such as 4242 4242 4242 4242."
            )
        return number

    # This validation prepares the submitted security code and rejects values that would make the
    # form misleading or unsafe.
    def clean_security_code(self) -> str:
        code = self.cleaned_data["security_code"].strip()
        if not re.fullmatch(r"\d{3,4}", code):
            raise forms.ValidationError("Enter a 3 or 4 digit security code.")
        return code

    # This validation prepares the submitted billing postal code and rejects values that would
    # make the form misleading or unsafe.
    def clean_billing_postal_code(self) -> str:
        postal_code = self.cleaned_data["billing_postal_code"].strip()
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9\s-]{2,9}", postal_code):
            raise forms.ValidationError("Enter a valid billing postal code.")
        return postal_code

    # This validation checks the record as a whole so combinations of fields cannot describe an
    # impossible or unsafe business state.
    def clean(self):
        cleaned_data = super().clean()
        month = cleaned_data.get("expiry_month")
        year = cleaned_data.get("expiry_year")
        if month and year:
            today = timezone.localdate()
            if (int(year), int(month)) < (today.year, today.month):
                self.add_error("expiry_month", "Choose a future expiry date.")
        return cleaned_data

    # This method handles safe payment result for the surrounding simulated payment form.
    # It keeps that responsibility close to the object while relying on the existing validation
    # and permission boundaries.
    def safe_payment_result(self) -> SafePaymentResult:
        """Return only metadata safe to store after the form is valid."""

        number = self.cleaned_data["card_number"]
        return SafePaymentResult(
            card_brand=self._detect_brand(number),
            card_last_four=number[-4:],
        )


# This form collects and validates the information needed for review code form.
# It accepts only the fields shown to the person using the page and leaves trusted identities,
# prices, and permissions to the server.
class ReviewCodeForm(forms.Form):
    """Collect a private party code before opening the verified review form."""

    review_code = forms.CharField(
        max_length=32,
        label="Party review code",
        help_text="Enter the code shown in your completed booking details.",
        widget=forms.TextInput(
            attrs={
                "class": "form-control review-code-input",
                "autocomplete": "off",
                "autocapitalize": "characters",
                "spellcheck": "false",
                "placeholder": "POP-7K4M-9Q2X",
            }
        ),
    )

    # This method handles init for the surrounding review code form.
    # It keeps that responsibility close to the object while relying on the existing validation
    # and permission boundaries.
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _apply_accessible_attributes(self)


# This form collects and validates the information needed for party review form.
# It accepts only the fields shown to the person using the page and leaves trusted identities,
# prices, and permissions to the server.
class PartyReviewForm(forms.Form):
    """Rate the package and exactly the add-ons recorded in one booking."""

    SCORE_CHOICES = [(number, f"{number} star" if number == 1 else f"{number} stars") for number in range(1, 6)]

    package_score = forms.TypedChoiceField(
        label="Package rating",
        choices=SCORE_CHOICES,
        coerce=int,
        widget=forms.RadioSelect(attrs={"class": "review-star-input"}),
    )
    # These review labels use the hosted company name while preserving the same privacy and publication choices.
    comment = forms.CharField(
        required=False,
        max_length=1500,
        label="Overall comments",
        help_text="Optional for private feedback. A written comment is required for a public testimonial.",
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 6,
                "placeholder": "Tell P Kids Events about the overall party experience.",
            }
        ),
    )
    visibility = forms.ChoiceField(
        label="Who may see your written feedback?",
        choices=PartyReview.Visibility.choices,
        initial=PartyReview.Visibility.PRIVATE,
        widget=forms.RadioSelect(attrs={"class": "review-visibility-input"}),
        help_text=(
            "Private feedback is visible only to P Kids Events. A public testimonial "
            "is published immediately with your explicit permission."
        ),
    )
    testimonial_name_display = forms.ChoiceField(
        label="How should your name appear?",
        choices=PartyReview.TestimonialNameDisplay.choices,
        initial=PartyReview.TestimonialNameDisplay.ANONYMOUS,
        widget=forms.RadioSelect(attrs={"class": "review-name-display-input"}),
        help_text="Only your first name can be shown. Your surname and account details stay private.",
    )

    # This method handles init for the surrounding party review form.
    # It keeps that responsibility close to the object while relying on the existing validation
    # and permission boundaries.
    def __init__(self, *args, booking, **kwargs):
        self.booking = booking
        self.build_addons = list(booking.addon_items.all())
        if args and args[0] is not None:
            # Older clients may not submit the new visibility controls. Falling
            # back to private is safe and prevents an update from publishing by
            # accident while current browsers still present a required choice.
            submitted = args[0].copy()
            submitted.setdefault("visibility", PartyReview.Visibility.PRIVATE)
            submitted.setdefault(
                "testimonial_name_display",
                PartyReview.TestimonialNameDisplay.ANONYMOUS,
            )
            args = (submitted, *args[1:])
        super().__init__(*args, **kwargs)

        review = getattr(booking, "review", None)
        existing_ratings = (
            {rating.build_addon_id: rating for rating in review.addon_ratings.all()}
            if review
            else {}
        )
        if review and not self.is_bound:
            self.initial.setdefault("package_score", review.package_score)
            self.initial.setdefault("comment", review.comment)
            self.initial.setdefault("visibility", review.visibility)
            self.initial.setdefault(
                "testimonial_name_display",
                review.testimonial_name_display,
            )
        elif not self.is_bound:
            self.initial.setdefault("visibility", PartyReview.Visibility.PRIVATE)
            self.initial.setdefault(
                "testimonial_name_display",
                PartyReview.TestimonialNameDisplay.ANONYMOUS,
            )

        for build_addon in self.build_addons:
            score_name = f"addon_score_{build_addon.pk}"
            self.fields[score_name] = forms.TypedChoiceField(
                label=f"Rate {build_addon.addon.name}",
                choices=self.SCORE_CHOICES,
                coerce=int,
                widget=forms.RadioSelect(attrs={"class": "review-star-input"}),
            )
            if not self.is_bound and build_addon.pk in existing_ratings:
                self.initial[score_name] = existing_ratings[build_addon.pk].score

        _apply_accessible_attributes(self)

    # This validation checks the record as a whole so combinations of fields cannot describe an
    # impossible or unsafe business state.
    def clean(self):
        cleaned = super().clean()
        comment = (cleaned.get("comment") or "").strip()
        visibility = cleaned.get("visibility")
        name_display = cleaned.get("testimonial_name_display")
        cleaned["comment"] = comment

        if visibility == PartyReview.Visibility.TESTIMONIAL and not comment:
            self.add_error(
                "comment",
                "Write a comment before publishing a public testimonial.",
            )
        if visibility == PartyReview.Visibility.PRIVATE:
            # The public-name choice has no meaning for private feedback. Resetting
            # it here avoids carrying stale publication settings into the service.
            cleaned["testimonial_name_display"] = (
                PartyReview.TestimonialNameDisplay.ANONYMOUS
            )
        elif visibility == PartyReview.Visibility.TESTIMONIAL and name_display not in {
            choice[0] for choice in PartyReview.TestimonialNameDisplay.choices
        }:
            self.add_error(
                "testimonial_name_display",
                "Choose how your name may appear with the testimonial.",
            )

        allowed_names = {
            f"addon_score_{build_addon.pk}" for build_addon in self.build_addons
        }
        submitted_names = {
            key for key in self.data.keys() if key.startswith("addon_score_")
        }
        if submitted_names - allowed_names:
            raise forms.ValidationError(
                "The submitted add-on ratings do not match this booking."
            )
        return cleaned

    # This method handles addon rating rows for the surrounding party review form.
    # It keeps that responsibility close to the object while relying on the existing validation
    # and permission boundaries.
    def addon_rating_rows(self):
        """Pair each selected add-on with its bound star field for the template."""

        return [
            (build_addon, self[f"addon_score_{build_addon.pk}"])
            for build_addon in self.build_addons
        ]

    # This method handles addon scores for the surrounding party review form.
    # It keeps that responsibility close to the object while relying on the existing validation
    # and permission boundaries.
    def addon_scores(self) -> dict[int, int]:
        """Return validated scores keyed by the selected booking-add-on row."""

        return {
            build_addon.pk: self.cleaned_data[f"addon_score_{build_addon.pk}"]
            for build_addon in self.build_addons
        }
