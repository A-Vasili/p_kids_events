# This historical migration records the database change identified as 0001_initial.
# It allows new and existing installations to reach the same stored structure or seed data in a
# repeatable order.
# This migration records a database change so every environment can build the same structure.
# Generated for the Popadoo party builder.

import django.core.validators
import django.db.models.deletion
import uuid
from decimal import Decimal

from django.db import migrations, models
from django.db.models import Q


# This migration tells Django how to update the database in a repeatable way.
# This class groups the information and behaviour needed for migration.
# Keeping the related rules together makes the surrounding workflow easier to reuse and test.
class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="AddonExperience",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("name", models.CharField(max_length=120)),
                ("slug", models.SlugField(max_length=140, unique=True)),
                ("short_description", models.CharField(max_length=260)),
                (
                    "price",
                    models.DecimalField(
                        decimal_places=2,
                        max_digits=8,
                        validators=[
                            django.core.validators.MinValueValidator(
                                Decimal("0.00")
                            )
                        ],
                    ),
                ),
                (
                    "duration_minutes",
                    models.PositiveIntegerField(
                        default=0,
                        help_text="Additional event duration. Use 0 when the addon runs in parallel.",
                        validators=[
                            django.core.validators.MaxValueValidator(600)
                        ],
                    ),
                ),
                (
                    "icon",
                    models.CharField(
                        default="✦",
                        help_text="A short decorative symbol; it is hidden from assistive technology.",
                        max_length=8,
                    ),
                ),
                ("is_featured", models.BooleanField(default=False)),
                ("is_active", models.BooleanField(default=True)),
                ("display_order", models.PositiveSmallIntegerField(default=0)),
            ],
            options={"ordering": ("display_order", "name")},
        ),
        migrations.CreateModel(
            name="PartyPackage",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("name", models.CharField(max_length=120)),
                ("slug", models.SlugField(max_length=140, unique=True)),
                ("short_description", models.CharField(max_length=240)),
                (
                    "base_price",
                    models.DecimalField(
                        decimal_places=2,
                        max_digits=8,
                        validators=[
                            django.core.validators.MinValueValidator(
                                Decimal("0.00")
                            )
                        ],
                    ),
                ),
                (
                    "duration_minutes",
                    models.PositiveIntegerField(
                        default=120,
                        validators=[
                            django.core.validators.MinValueValidator(30),
                            django.core.validators.MaxValueValidator(600),
                        ],
                    ),
                ),
                (
                    "included_guest_count",
                    models.PositiveIntegerField(
                        default=15,
                        validators=[
                            django.core.validators.MinValueValidator(1),
                            django.core.validators.MaxValueValidator(200),
                        ],
                    ),
                ),
                (
                    "included_experiences",
                    models.TextField(
                        help_text="Enter one included experience per line."
                    ),
                ),
                (
                    "is_default",
                    models.BooleanField(
                        default=False,
                        help_text="The default package shown when the builder opens.",
                    ),
                ),
                ("is_active", models.BooleanField(default=True)),
                ("display_order", models.PositiveSmallIntegerField(default=0)),
            ],
            options={"ordering": ("display_order", "name")},
        ),
        migrations.CreateModel(
            name="PartyBuild",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "public_id",
                    models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
                ),
                ("contact_name", models.CharField(max_length=120)),
                ("contact_email", models.EmailField(max_length=254)),
                ("contact_phone", models.CharField(max_length=30)),
                ("event_date", models.DateField()),
                (
                    "guest_count",
                    models.PositiveIntegerField(
                        validators=[
                            django.core.validators.MinValueValidator(1),
                            django.core.validators.MaxValueValidator(200),
                        ]
                    ),
                ),
                ("notes", models.TextField(blank=True, max_length=1500)),
                (
                    "total_price",
                    models.DecimalField(
                        decimal_places=2,
                        help_text="Server-calculated price snapshot at submission time.",
                        max_digits=9,
                        validators=[
                            django.core.validators.MinValueValidator(
                                Decimal("0.00")
                            )
                        ],
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("draft", "Draft"),
                            ("submitted", "Submitted"),
                            ("contacted", "Contacted"),
                            ("confirmed", "Confirmed"),
                            ("cancelled", "Cancelled"),
                        ],
                        default="submitted",
                        max_length=20,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "package",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="builds",
                        to="party_builder.partypackage",
                    ),
                ),
            ],
            options={"ordering": ("-created_at",)},
        ),
        migrations.CreateModel(
            name="PartyBuildAddon",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "unit_price",
                    models.DecimalField(
                        decimal_places=2,
                        max_digits=8,
                        validators=[
                            django.core.validators.MinValueValidator(
                                Decimal("0.00")
                            )
                        ],
                    ),
                ),
                (
                    "addon",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="build_items",
                        to="party_builder.addonexperience",
                    ),
                ),
                (
                    "build",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="addon_items",
                        to="party_builder.partybuild",
                    ),
                ),
            ],
            options={"ordering": ("addon__display_order", "addon__name")},
        ),
        migrations.AddField(
            model_name="partybuild",
            name="addons",
            field=models.ManyToManyField(
                blank=True,
                related_name="party_builds",
                through="party_builder.PartyBuildAddon",
                to="party_builder.addonexperience",
            ),
        ),
        migrations.AddConstraint(
            model_name="addonexperience",
            constraint=models.CheckConstraint(
                condition=Q(("price__gte", 0)),
                name="party_addon_price_non_negative",
            ),
        ),
        migrations.AddConstraint(
            model_name="partypackage",
            constraint=models.CheckConstraint(
                condition=Q(("base_price__gte", 0)),
                name="party_package_base_price_non_negative",
            ),
        ),
        migrations.AddConstraint(
            model_name="partypackage",
            constraint=models.UniqueConstraint(
                condition=Q(("is_default", True)),
                fields=("is_default",),
                name="party_builder_single_default_package",
            ),
        ),
        migrations.AddConstraint(
            model_name="partybuildaddon",
            constraint=models.UniqueConstraint(
                fields=("build", "addon"),
                name="party_build_unique_addon",
            ),
        ),
    ]
