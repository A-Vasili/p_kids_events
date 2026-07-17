# This file describes the business records stored by this part of Popadoo and the relationships
# between them.
# The models preserve important history and enforce rules that must remain true no matter which
# page changes the data.
# Views, forms, and services build on these records rather than keeping important information only
# in the browser.

from __future__ import annotations

import secrets
import uuid
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models, router
from django.db.models import Q
from django.urls import reverse

from .validators import (
    addon_image_upload_to,
    category_image_upload_to,
    package_image_upload_to,
    validate_catalogue_image,
)


# These slug lists identify the seeded catalogue records that have matching artwork bundled with
# the website. Custom records are deliberately excluded so a missing upload still uses the existing
# placeholder instead of pointing visitors to a file that does not exist.
DEFAULT_PACKAGE_STATIC_IMAGE_SLUGS = frozenset(
    {
        "basic-popadoo-party",
        "popadoo-plus-party",
        "popadoo-classic-party",
        "popadoo-big-party",
        "popadoo-xl-party",
        "popadoo-mega-party",
        "popadoo-super-party",
        "popadoo-festival-party",
    }
)
DEFAULT_ADDON_STATIC_IMAGE_SLUGS = frozenset(
    {
        "face-painting",
        "balloon-modelling",
        "treasure-hunt",
        "creative-craft-workshop",
        "mini-magic-show",
        "themed-balloon-decoration",
        "extra-entertainer",
        "party-favour-pack",
        "bubble-show",
        "kids-disco-dance-games",
        "slime-laboratory",
        "junior-science-experiments",
        "character-visit",
        "superhero-training",
        "puppet-show",
        "karaoke-party",
        "party-photo-booth",
        "glitter-tattoos",
        "cupcake-decorating",
        "pinata-game",
    }
)


# This safeguard verifies constraints except before the surrounding workflow continues.
# When the rule is not met, it stops the action with a controlled error rather than allowing an
# inconsistent record.
def _validate_constraints_except(instance, excluded_names: set[str], exclude=None) -> None:
    """Validate model constraints except defaults switched by a transaction.

    Conditional unique constraints correctly protect the database, but Django's
    ModelForm validation runs before the service can clear the old default row.
    Skipping only those two checks here allows an atomic default switch while
    every other model and database constraint remains active.
    """

    errors = {}
    using = router.db_for_write(instance.__class__, instance=instance)
    for model_class, model_constraints in instance.get_constraints():
        for constraint in model_constraints:
            if constraint.name in excluded_names:
                continue
            try:
                constraint.validate(
                    model_class,
                    instance,
                    exclude=exclude,
                    using=using,
                )
            except ValidationError as error:
                if (
                    getattr(error, "code", None) == "unique"
                    and len(constraint.fields) == 1
                ):
                    errors.setdefault(constraint.fields[0], []).append(error)
                else:
                    errors = error.update_error_dict(errors)
    if errors:
        raise ValidationError(errors)


# These named choices keep the allowed category values consistent in the database, forms, and page
# labels.
class Category(models.Model):
    """A catalogue category; assigning a parent creates a subcategory."""

    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140, unique=True)
    description = models.TextField(blank=True, max_length=1000)
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="children",
    )
    image = models.ImageField(
        upload_to=category_image_upload_to,
        validators=[validate_catalogue_image],
        blank=True,
    )
    image_alt_text = models.CharField(
        max_length=180,
        blank=True,
        help_text="Describe the image for visitors who cannot see it.",
    )
    display_order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # This inner configuration tells Django how the surrounding record should be ordered,
    # labelled, indexed, or constrained.
    class Meta:
        ordering = ("display_order", "name")
        verbose_name_plural = "categories"
        indexes = [
            models.Index(fields=("is_active", "display_order", "name")),
            models.Index(fields=("parent", "is_active")),
        ]

    # This method handles str for the surrounding category.
    # It keeps that responsibility close to the object while relying on the existing validation
    # and permission boundaries.
    def __str__(self) -> str:
        return self.name if self.parent_id is None else f"{self.parent.name} / {self.name}"

    # This validation checks the record as a whole so combinations of fields cannot describe an
    # impossible or unsafe business state.
    def clean(self) -> None:
        """Reject self-parenting and parent choices underneath this category."""

        super().clean()
        self.name = (self.name or "").strip()
        self.description = (self.description or "").strip()
        self.image_alt_text = (self.image_alt_text or "").strip()
        if not self.name:
            raise ValidationError({"name": "Enter a category name."})
        if self.pk and self.parent_id == self.pk:
            raise ValidationError({"parent": "A category cannot be its own parent."})

        parent = self.parent
        visited = set()
        while parent is not None:
            if parent.pk in visited:
                raise ValidationError({"parent": "The selected category hierarchy is circular."})
            visited.add(parent.pk)
            if self.pk and parent.pk == self.pk:
                raise ValidationError(
                    {"parent": "A category cannot be placed underneath one of its subcategories."}
                )
            parent = parent.parent

        if self.image and not self.image_alt_text:
            raise ValidationError({"image_alt_text": "Add meaningful alternative text for this image."})


# This model represents party package as a stored Popadoo business record.
# Its relationships and validation keep the record meaningful when it is used by customer, worker,
# and management pages.
class PartyPackage(models.Model):
    """The essential Popadoo experience used as the checkout foundation."""

    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140, unique=True)
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name="packages",
    )
    short_description = models.CharField(max_length=240)
    base_price = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text="Reference price for the smallest active guest bracket.",
    )
    duration_minutes = models.PositiveIntegerField(
        default=120,
        validators=[MinValueValidator(30), MaxValueValidator(600)],
    )
    included_guest_count = models.PositiveIntegerField(
        default=10,
        validators=[MinValueValidator(1), MaxValueValidator(200)],
    )
    included_experiences = models.TextField(
        help_text="Enter one included experience per line."
    )
    is_default = models.BooleanField(
        default=False,
        help_text="The package used when the multi-step checkout opens.",
    )
    is_active = models.BooleanField(default=True)
    display_order = models.PositiveSmallIntegerField(default=0)
    image = models.ImageField(
        upload_to=package_image_upload_to,
        validators=[validate_catalogue_image],
        blank=True,
    )
    image_alt_text = models.CharField(max_length=180, blank=True)

    # This inner configuration tells Django how the surrounding record should be ordered,
    # labelled, indexed, or constrained.
    class Meta:
        ordering = ("display_order", "name")
        indexes = [models.Index(fields=("is_active", "display_order", "name"))]
        constraints = [
            models.CheckConstraint(
                condition=Q(base_price__gte=0),
                name="party_package_base_price_non_negative",
            ),
            # The database also enforces the single-default rule so imports,
            # scripts, and future code cannot accidentally create two defaults.
            models.UniqueConstraint(
                fields=("is_default",),
                condition=Q(is_default=True),
                name="party_builder_single_default_package",
            ),
        ]

    # This validation checks the record as a whole so combinations of fields cannot describe an
    # impossible or unsafe business state.
    def clean(self) -> None:
        """Keep text tidy and ensure default records remain selectable."""

        super().clean()
        self.name = (self.name or "").strip()
        self.short_description = (self.short_description or "").strip()
        self.included_experiences = (self.included_experiences or "").strip()
        self.image_alt_text = (self.image_alt_text or "").strip()
        if self.is_default and not self.is_active:
            raise ValidationError({"is_active": "The default package must remain active."})
        if self.image and not self.image_alt_text:
            raise ValidationError({"image_alt_text": "Add meaningful alternative text for this image."})

    # This safeguard verifies constraints before the surrounding workflow continues.
    # When the rule is not met, it stops the action with a controlled error rather than allowing
    # an inconsistent record.
    def validate_constraints(self, exclude=None) -> None:
        _validate_constraints_except(
            self,
            {"party_builder_single_default_package"},
            exclude=exclude,
        )

    # This method handles str for the surrounding party package.
    # It keeps that responsibility close to the object while relying on the existing validation
    # and permission boundaries.
    def __str__(self) -> str:
        return self.name

    # This method handles included experiences list for the surrounding party package.
    # It keeps that responsibility close to the object while relying on the existing validation
    # and permission boundaries.
    @property
    def included_experiences_list(self) -> list[str]:
        """Return clean list items for semantic template rendering."""

        return [
            item.strip()
            for item in self.included_experiences.splitlines()
            if item.strip()
        ]

    # This property distinguishes an Owner's uploaded replacement from the earlier seeded media
    # link. It lets the new static artwork take over without hiding a genuine custom image.
    @property
    def has_custom_image(self) -> bool:
        if not self.image:
            return False
        if self.slug not in DEFAULT_PACKAGE_STATIC_IMAGE_SLUGS:
            return True
        return self.image.name != f"catalogue/packages/{self.slug}.png"

    # This property gives seeded packages a reliable image that travels with the website while
    # leaving manager-uploaded images in the media library as the first choice on every page.
    @property
    def default_static_image_path(self) -> str:
        if self.slug not in DEFAULT_PACKAGE_STATIC_IMAGE_SLUGS:
            return ""
        return f"assets/catalogue/packages/{self.slug}.png"

    # This property keeps every displayed package image understandable to visitors who use screen
    # readers, including the bundled defaults that do not store separate database descriptions.
    @property
    def display_image_alt_text(self) -> str:
        return self.image_alt_text or f"Illustration for {self.name}"

    # This helper retrieves absolute url for the page or service that called it.
    # It returns a consistent, permission-aware result so callers do not need to repeat the same
    # selection rules.
    def get_absolute_url(self) -> str:
        return reverse("party_ideas:package_detail", kwargs={"slug": self.slug})


# This model represents guest price tier as a stored Popadoo business record.
# Its relationships and validation keep the record meaningful when it is used by customer, worker,
# and management pages.
class GuestPriceTier(models.Model):
    """A fixed package price for a clearly defined children-count bracket."""

    package = models.ForeignKey(
        PartyPackage,
        on_delete=models.CASCADE,
        related_name="guest_price_tiers",
    )
    label = models.CharField(max_length=60)
    min_guests = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(200)]
    )
    max_guests = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(200)]
    )
    total_price = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    is_default = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    display_order = models.PositiveSmallIntegerField(default=0)

    # This inner configuration tells Django how the surrounding record should be ordered,
    # labelled, indexed, or constrained.
    class Meta:
        ordering = ("display_order", "min_guests")
        constraints = [
            models.CheckConstraint(
                condition=Q(total_price__gte=0),
                name="guest_tier_price_non_negative",
            ),
            models.CheckConstraint(
                condition=Q(max_guests__gte=models.F("min_guests")),
                name="guest_tier_valid_range",
            ),
            models.UniqueConstraint(
                fields=("package", "min_guests", "max_guests"),
                name="guest_tier_unique_range_per_package",
            ),
            models.UniqueConstraint(
                fields=("package",),
                condition=Q(is_default=True),
                name="guest_tier_single_default_per_package",
            ),
        ]

    # This validation checks the record as a whole so combinations of fields cannot describe an
    # impossible or unsafe business state.
    def clean(self) -> None:
        """Validate active ranges before they reach checkout pricing."""

        super().clean()
        self.label = (self.label or "").strip()
        if self.min_guests and self.max_guests and self.max_guests < self.min_guests:
            raise ValidationError({"max_guests": "Maximum guests must be at least the minimum."})
        if self.is_default and not self.is_active:
            raise ValidationError({"is_active": "The default price tier must remain active."})
        if self.package_id and self.is_active and self.min_guests and self.max_guests:
            overlapping = GuestPriceTier.objects.filter(
                package_id=self.package_id,
                is_active=True,
                min_guests__lte=self.max_guests,
                max_guests__gte=self.min_guests,
            )
            if self.pk:
                overlapping = overlapping.exclude(pk=self.pk)
            if overlapping.exists():
                raise ValidationError(
                    "This active guest range overlaps another active tier for the package."
                )

    # This safeguard verifies constraints before the surrounding workflow continues.
    # When the rule is not met, it stops the action with a controlled error rather than allowing
    # an inconsistent record.
    def validate_constraints(self, exclude=None) -> None:
        _validate_constraints_except(
            self,
            {"guest_tier_single_default_per_package"},
            exclude=exclude,
        )

    # This method handles str for the surrounding guest price tier.
    # It keeps that responsibility close to the object while relying on the existing validation
    # and permission boundaries.
    def __str__(self) -> str:
        return f"{self.package.name}: {self.label}"

    # This method handles price per child at capacity for the surrounding guest price tier.
    # It keeps that responsibility close to the object while relying on the existing validation
    # and permission boundaries.
    @property
    def price_per_child_at_capacity(self) -> Decimal:
        """Show the effective rate when the bracket is filled to capacity."""

        if not self.max_guests:
            return Decimal("0.00")
        return (self.total_price / Decimal(self.max_guests)).quantize(
            Decimal("0.01")
        )

    # This method handles contains guest count for the surrounding guest price tier.
    # It keeps that responsibility close to the object while relying on the existing validation
    # and permission boundaries.
    def contains_guest_count(self, guest_count: int) -> bool:
        return self.min_guests <= guest_count <= self.max_guests


# This model represents addon experience as a stored Popadoo business record.
# Its relationships and validation keep the record meaningful when it is used by customer, worker,
# and management pages.
class AddonExperience(models.Model):
    """An optional paid experience that can be added to the base package."""

    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140, unique=True)
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name="addons",
    )
    short_description = models.CharField(max_length=260)
    price = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    duration_minutes = models.PositiveIntegerField(
        default=0,
        help_text="Additional event duration. Use 0 when the addon runs in parallel.",
        validators=[MaxValueValidator(600)],
    )
    icon = models.CharField(
        max_length=8,
        default="✦",
        help_text="A short decorative symbol hidden from assistive technology.",
    )
    is_featured = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    display_order = models.PositiveSmallIntegerField(default=0)
    image = models.ImageField(
        upload_to=addon_image_upload_to,
        validators=[validate_catalogue_image],
        blank=True,
    )
    image_alt_text = models.CharField(max_length=180, blank=True)

    # This inner configuration tells Django how the surrounding record should be ordered,
    # labelled, indexed, or constrained.
    class Meta:
        ordering = ("display_order", "name")
        indexes = [models.Index(fields=("is_active", "is_featured", "display_order"))]
        constraints = [
            models.CheckConstraint(
                condition=Q(price__gte=0),
                name="party_addon_price_non_negative",
            )
        ]

    # This validation checks the record as a whole so combinations of fields cannot describe an
    # impossible or unsafe business state.
    def clean(self) -> None:
        super().clean()
        self.name = (self.name or "").strip()
        self.short_description = (self.short_description or "").strip()
        self.image_alt_text = (self.image_alt_text or "").strip()
        if self.image and not self.image_alt_text:
            raise ValidationError({"image_alt_text": "Add meaningful alternative text for this image."})

    # This method handles str for the surrounding addon experience.
    # It keeps that responsibility close to the object while relying on the existing validation
    # and permission boundaries.
    def __str__(self) -> str:
        return self.name

    # This property distinguishes an Owner's uploaded replacement from the earlier seeded media
    # link. It lets the new static artwork take over without hiding a genuine custom image.
    @property
    def has_custom_image(self) -> bool:
        if not self.image:
            return False
        if self.slug not in DEFAULT_ADDON_STATIC_IMAGE_SLUGS:
            return True
        return self.image.name != f"catalogue/addons/{self.slug}.png"

    # This property gives seeded add-ons a reliable image that travels with the website while
    # leaving manager-uploaded images in the media library as the first choice on every page.
    @property
    def default_static_image_path(self) -> str:
        if self.slug not in DEFAULT_ADDON_STATIC_IMAGE_SLUGS:
            return ""
        return f"assets/catalogue/addons/{self.slug}.png"

    # This property keeps every displayed add-on image understandable to visitors who use screen
    # readers, including the bundled defaults that do not store separate database descriptions.
    @property
    def display_image_alt_text(self) -> str:
        return self.image_alt_text or f"Illustration for {self.name}"

    # This helper retrieves absolute url for the page or service that called it.
    # It returns a consistent, permission-aware result so callers do not need to repeat the same
    # selection rules.
    def get_absolute_url(self) -> str:
        return reverse("party_ideas:addon_detail", kwargs={"slug": self.slug})


REVIEW_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


# This function handles format review code as part of this module’s workflow.
# It keeps the repeated decision in one place so callers receive the same result and controlled
# failure behaviour.
def format_review_code(raw: str) -> str:
    """Return a normalized human-readable code without ambiguous characters."""

    compact = "".join(character for character in (raw or "").upper() if character.isalnum())
    if compact.startswith("POP"):
        compact = compact[3:]
    if len(compact) != 8 or any(character not in REVIEW_CODE_ALPHABET for character in compact):
        return ""
    return f"POP-{compact[:4]}-{compact[4:]}"


# This function handles generate review code candidate as part of this module’s workflow.
# It keeps the repeated decision in one place so callers receive the same result and controlled
# failure behaviour.
def generate_review_code_candidate() -> str:
    """Create one readable candidate; database uniqueness is checked separately."""

    body = "".join(secrets.choice(REVIEW_CODE_ALPHABET) for _ in range(8))
    return f"POP-{body[:4]}-{body[4:]}"


# This function handles generate unique review code as part of this module’s workflow.
# It keeps the repeated decision in one place so callers receive the same result and controlled
# failure behaviour.
def generate_unique_review_code() -> str:
    """Return a code not currently stored in the booking table."""

    for _attempt in range(32):
        candidate = generate_review_code_candidate()
        # This lookup keeps normal model creation safe. The unique database
        # constraint remains the final protection if two requests race.
        if not PartyBuild.objects.filter(review_code=candidate).exists():
            return candidate
    raise RuntimeError("Unable to allocate a unique party review code.")


# This model represents party build as a stored Popadoo business record.
# Its relationships and validation keep the record meaningful when it is used by customer, worker,
# and management pages.
class PartyBuild(models.Model):
    """A completed simulated order with trusted server-side price snapshots."""

    # These named choices keep the allowed status values consistent in the database, forms, and
    # page labels.
    class Status(models.TextChoices):
        SUBMITTED = "submitted", "Submitted"
        CONTACTED = "contacted", "Contacted"
        CONFIRMED = "confirmed", "Confirmed"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    # These named choices keep the allowed payment status values consistent in the database,
    # forms, and page labels.
    class PaymentStatus(models.TextChoices):
        SIMULATED = "simulated", "Simulated payment accepted"
        NOT_REQUIRED = "not_required", "No payment data"

    # These named choices keep the allowed assignment state values consistent in the database,
    # forms, and page labels.
    class AssignmentState(models.TextChoices):
        UNASSIGNED = "unassigned", "Unassigned"
        PENDING = "pending_acceptance", "Awaiting worker response"
        ASSIGNED = "assigned", "Worker assigned"
        MANUAL_REVIEW = "manual_review", "Owner review required"

    public_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    review_code = models.CharField(
        max_length=13,
        unique=True,
        editable=False,
        default=generate_unique_review_code,
    )
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="party_bookings",
        help_text="Empty for guest checkouts.",
    )
    package = models.ForeignKey(
        PartyPackage,
        on_delete=models.PROTECT,
        related_name="builds",
    )
    guest_tier = models.ForeignKey(
        GuestPriceTier,
        on_delete=models.PROTECT,
        related_name="builds",
        null=True,
        blank=True,
        help_text="Nullable only for legacy requests created before tiered pricing.",
    )
    addons = models.ManyToManyField(
        AddonExperience,
        through="PartyBuildAddon",
        related_name="party_builds",
        blank=True,
    )

    # Personal and event details collected during checkout step two.
    contact_name = models.CharField(max_length=120)
    contact_email = models.EmailField()
    contact_phone = models.CharField(max_length=30)
    event_date = models.DateField()
    event_time = models.TimeField(null=True, blank=True)
    event_address = models.CharField(max_length=240, blank=True)
    postal_code = models.CharField(
        max_length=10,
        blank=True,
        validators=[
            RegexValidator(
                regex=r"^[A-Za-z0-9][A-Za-z0-9\s-]{2,9}$",
                message="Enter a valid postal code.",
            )
        ],
    )
    guest_count = models.PositiveIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(200)]
    )
    notes = models.TextField(blank=True, max_length=1500)

    # Snapshots protect historical orders when administrators change prices later.
    guest_tier_label = models.CharField(max_length=60, blank=True)
    package_price = models.DecimalField(
        max_digits=9,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    addon_price = models.DecimalField(
        max_digits=9,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    total_price = models.DecimalField(
        max_digits=9,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text="Server-calculated total at simulated checkout.",
    )

    # Only non-sensitive payment metadata is stored. Card number and CVV are discarded.
    payment_status = models.CharField(
        max_length=20,
        choices=PaymentStatus.choices,
        default=PaymentStatus.NOT_REQUIRED,
    )
    card_brand = models.CharField(max_length=30, blank=True)
    card_last_four = models.CharField(max_length=4, blank=True)
    payment_reference = models.CharField(max_length=40, blank=True)
    checkout_completed_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.SUBMITTED,
    )
    assignment_state = models.CharField(
        max_length=30,
        choices=AssignmentState.choices,
        default=AssignmentState.UNASSIGNED,
    )
    assignment_requested_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # This inner configuration tells Django how the surrounding record should be ordered,
    # labelled, indexed, or constrained.
    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=("event_date", "status")),
            models.Index(fields=("assignment_state", "event_date")),
            models.Index(fields=("contact_email",)),
            models.Index(fields=("status", "completed_at")),
        ]

    # This save step preserves the model’s business rules whenever the record is written, not only
    # when it comes from one particular form.
    def save(self, *args, **kwargs):
        if self.review_code:
            normalized = format_review_code(self.review_code)
            if not normalized:
                raise ValidationError({"review_code": "The party review code format is invalid."})
            self.review_code = normalized
        super().save(*args, **kwargs)

    # This method handles str for the surrounding party build.
    # It keeps that responsibility close to the object while relying on the existing validation
    # and permission boundaries.
    def __str__(self) -> str:
        return f"{self.contact_name} — {self.package.name} ({self.event_date})"

    # This method handles party size display for the surrounding party build.
    # It keeps that responsibility close to the object while relying on the existing validation
    # and permission boundaries.
    @property
    def party_size_display(self) -> str:
        """Describe capacity without presenting it as confirmed attendance."""

        return self.guest_tier_label or f"Up to {self.guest_count} children"

    # This helper retrieves absolute url for the page or service that called it.
    # It returns a consistent, permission-aware result so callers do not need to repeat the same
    # selection rules.
    def get_absolute_url(self) -> str:
        return reverse(
            "party_builder:party_builder_order_success",
            kwargs={"public_id": self.public_id},
        )


# This model represents party build addon as a stored Popadoo business record.
# Its relationships and validation keep the record meaningful when it is used by customer, worker,
# and management pages.
class PartyBuildAddon(models.Model):
    """Join model preserving the addon price used for a completed checkout."""

    build = models.ForeignKey(
        PartyBuild,
        on_delete=models.CASCADE,
        related_name="addon_items",
    )
    addon = models.ForeignKey(
        AddonExperience,
        on_delete=models.PROTECT,
        related_name="build_items",
    )
    unit_price = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )

    # This inner configuration tells Django how the surrounding record should be ordered,
    # labelled, indexed, or constrained.
    class Meta:
        ordering = ("addon__display_order", "addon__name")
        constraints = [
            models.UniqueConstraint(
                fields=("build", "addon"),
                name="party_build_unique_addon",
            )
        ]

    # This method handles str for the surrounding party build addon.
    # It keeps that responsibility close to the object while relying on the existing validation
    # and permission boundaries.
    def __str__(self) -> str:
        return f"{self.build.public_id}: {self.addon.name}"


# This model represents party review as a stored Popadoo business record.
# Its relationships and validation keep the record meaningful when it is used by customer, worker,
# and management pages.
class PartyReview(models.Model):
    """Verified feedback for one completed customer booking.

    The review remains the single source of truth for both private company
    feedback and public testimonials. Publication is opt-in and can be
    withdrawn by the booking customer at any time.
    """

    # These named choices keep the allowed visibility values consistent in the database, forms,
    # and page labels.
    class Visibility(models.TextChoices):
        PRIVATE = "private", "Private feedback"
        TESTIMONIAL = "testimonial", "Public testimonial"

    # These named choices keep the allowed testimonial name display values consistent in the
    # database, forms, and page labels.
    class TestimonialNameDisplay(models.TextChoices):
        ANONYMOUS = "anonymous", "Anonymous"
        FIRST_NAME = "first_name", "First name only"

    booking = models.OneToOneField(
        PartyBuild,
        on_delete=models.CASCADE,
        related_name="review",
    )
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="party_reviews",
    )
    package_score = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    comment = models.TextField(blank=True, max_length=1500)
    visibility = models.CharField(
        max_length=20,
        choices=Visibility.choices,
        default=Visibility.PRIVATE,
        db_index=True,
    )
    testimonial_name_display = models.CharField(
        max_length=20,
        choices=TestimonialNameDisplay.choices,
        default=TestimonialNameDisplay.ANONYMOUS,
    )
    testimonial_consent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # This inner configuration tells Django how the surrounding record should be ordered,
    # labelled, indexed, or constrained.
    class Meta:
        ordering = ("-updated_at",)
        constraints = [
            models.CheckConstraint(
                condition=Q(package_score__gte=1, package_score__lte=5),
                name="party_review_package_score_1_to_5",
            ),
            models.CheckConstraint(
                condition=Q(visibility__in=("private", "testimonial")),
                name="party_review_supported_visibility",
            ),
            models.CheckConstraint(
                condition=Q(testimonial_name_display__in=("anonymous", "first_name")),
                name="party_review_supported_name_display",
            ),
            # Private comments are never allowed to retain publication consent
            # or a public-facing name choice.
            models.CheckConstraint(
                condition=(
                    Q(visibility="testimonial")
                    | Q(
                        testimonial_name_display="anonymous",
                        testimonial_consent_at__isnull=True,
                    )
                ),
                name="party_review_private_state_is_not_public",
            ),
        ]
        indexes = [
            models.Index(fields=("reviewer", "updated_at")),
            models.Index(fields=("package_score", "updated_at")),
            models.Index(fields=("visibility", "updated_at")),
        ]

    # This validation checks the record as a whole so combinations of fields cannot describe an
    # impossible or unsafe business state.
    def clean(self) -> None:
        super().clean()
        self.comment = (self.comment or "").strip()
        if self.visibility == self.Visibility.TESTIMONIAL and not self.comment:
            raise ValidationError(
                {"comment": "Write a comment before publishing a public testimonial."}
            )
        if self.visibility == self.Visibility.PRIVATE:
            self.testimonial_name_display = self.TestimonialNameDisplay.ANONYMOUS
            self.testimonial_consent_at = None
        if self.booking_id and self.reviewer_id:
            if self.booking.customer_id != self.reviewer_id:
                raise ValidationError("Only the customer who booked this party can review it.")
            if self.booking.status != PartyBuild.Status.COMPLETED:
                raise ValidationError("Only completed parties can be reviewed.")

    # This role check answers whether the current account qualifies as public testimonial.
    # Callers use the answer for navigation and convenience, while protected views and services
    # still enforce access themselves.
    @property
    def is_public_testimonial(self) -> bool:
        """Return whether this review currently has active publication consent."""

        return (
            self.visibility == self.Visibility.TESTIMONIAL
            and self.testimonial_consent_at is not None
            and bool(self.comment.strip())
            and self.booking.status == PartyBuild.Status.COMPLETED
        )

    # This method handles public display name for the surrounding party review.
    # It keeps that responsibility close to the object while relying on the existing validation
    # and permission boundaries.
    @property
    def public_display_name(self) -> str:
        """Return the only customer identity allowed on the public page."""

        if self.testimonial_name_display == self.TestimonialNameDisplay.FIRST_NAME:
            first_name = (self.reviewer.first_name or "").strip()
            if first_name:
                return first_name
        return "Verified customer"

    # This method handles str for the surrounding party review.
    # It keeps that responsibility close to the object while relying on the existing validation
    # and permission boundaries.
    def __str__(self) -> str:
        return f"Review for {self.booking.public_id} by {self.reviewer}"


# This model represents addon rating as a stored Popadoo business record.
# Its relationships and validation keep the record meaningful when it is used by customer, worker,
# and management pages.
class AddonRating(models.Model):
    """A verified score for an add-on that appears in the reviewed booking."""

    review = models.ForeignKey(
        PartyReview,
        on_delete=models.CASCADE,
        related_name="addon_ratings",
    )
    build_addon = models.ForeignKey(
        PartyBuildAddon,
        on_delete=models.CASCADE,
        related_name="ratings",
    )
    score = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    comment = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # This inner configuration tells Django how the surrounding record should be ordered,
    # labelled, indexed, or constrained.
    class Meta:
        ordering = ("build_addon__addon__display_order", "build_addon__addon__name")
        constraints = [
            models.CheckConstraint(
                condition=Q(score__gte=1, score__lte=5),
                name="addon_rating_score_1_to_5",
            ),
            models.UniqueConstraint(
                fields=("review", "build_addon"),
                name="one_rating_per_selected_booking_addon",
            ),
        ]
        indexes = [
            models.Index(fields=("build_addon", "score")),
            models.Index(fields=("review", "updated_at")),
        ]

    # This validation checks the record as a whole so combinations of fields cannot describe an
    # impossible or unsafe business state.
    def clean(self) -> None:
        super().clean()
        self.comment = (self.comment or "").strip()
        if self.review_id and self.build_addon_id:
            if self.review.booking_id != self.build_addon.build_id:
                raise ValidationError(
                    "The add-on rating must belong to the same booking as the review."
                )

    # This method handles str for the surrounding addon rating.
    # It keeps that responsibility close to the object while relying on the existing validation
    # and permission boundaries.
    def __str__(self) -> str:
        return f"{self.build_addon.addon.name}: {self.score}/5"
