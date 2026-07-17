# This historical migration records the database change identified as 0004_seed_guest_price_tiers.
# It allows new and existing installations to reach the same stored structure or seed data in a
# repeatable order.
# This migration records a database change so every environment can build the same structure.

from decimal import Decimal

from django.db import migrations


TIERS = [
    {
        "label": "0–10 children",
        "min_guests": 1,
        "max_guests": 10,
        "total_price": Decimal("180.00"),
        "is_default": True,
        "display_order": 10,
    },
    {
        "label": "11–15 children",
        "min_guests": 11,
        "max_guests": 15,
        "total_price": Decimal("255.00"),
        "is_default": False,
        "display_order": 20,
    },
    {
        "label": "16–20 children",
        "min_guests": 16,
        "max_guests": 20,
        "total_price": Decimal("330.00"),
        "is_default": False,
        "display_order": 30,
    },
    {
        "label": "21–25 children",
        "min_guests": 21,
        "max_guests": 25,
        "total_price": Decimal("400.00"),
        "is_default": False,
        "display_order": 40,
    },
    {
        "label": "26–30 children",
        "min_guests": 26,
        "max_guests": 30,
        "total_price": Decimal("465.00"),
        "is_default": False,
        "display_order": 50,
    },
    {
        "label": "31–35 children",
        "min_guests": 31,
        "max_guests": 35,
        "total_price": Decimal("525.00"),
        "is_default": False,
        "display_order": 60,
    },
    {
        "label": "36–40 children",
        "min_guests": 36,
        "max_guests": 40,
        "total_price": Decimal("580.00"),
        "is_default": False,
        "display_order": 70,
    },
]


# This migration helper inserts the default group-size price brackets into a new database.
# This forward migration prepares the historical records required by this release while preserving
# existing customised data where the migration allows it.
def seed_guest_price_tiers(apps, schema_editor):
    PartyPackage = apps.get_model("party_builder", "PartyPackage")
    GuestPriceTier = apps.get_model("party_builder", "GuestPriceTier")
    PartyBuild = apps.get_model("party_builder", "PartyBuild")

    package = PartyPackage.objects.filter(slug="basic-popadoo-party").first()
    if package is None:
        return

    package.base_price = Decimal("180.00")
    package.included_guest_count = 10
    package.short_description = (
        "A two-hour mobile party with a trained host, organised games, music, "
        "activity equipment, and event coordination for up to 10 children."
    )
    package.save(
        update_fields=("base_price", "included_guest_count", "short_description")
    )

    created_tiers = []
    for tier_data in TIERS:
        tier, _ = GuestPriceTier.objects.update_or_create(
            package=package,
            min_guests=tier_data["min_guests"],
            max_guests=tier_data["max_guests"],
            defaults={
                **tier_data,
                "package": package,
                "is_active": True,
            },
        )
        created_tiers.append(tier)

    # Preserve legacy requests while associating them with the closest new range.
    for build in PartyBuild.objects.filter(package=package, guest_tier__isnull=True):
        tier = next(
            (
                item
                for item in created_tiers
                if item.min_guests <= build.guest_count <= item.max_guests
            ),
            created_tiers[-1],
        )
        legacy_addon_price = max(
            build.total_price - package.base_price,
            Decimal("0.00"),
        )
        build.guest_tier = tier
        build.guest_tier_label = tier.label
        build.package_price = package.base_price
        build.addon_price = legacy_addon_price
        build.save(
            update_fields=(
                "guest_tier",
                "guest_tier_label",
                "package_price",
                "addon_price",
            )
        )


# This helper removes guest price tiers after the required checks.
# This migration helper performs the data part of the historical change recorded in this file.
def remove_guest_price_tiers(apps, schema_editor):
    GuestPriceTier = apps.get_model("party_builder", "GuestPriceTier")
    GuestPriceTier.objects.filter(
        package__slug="basic-popadoo-party",
        min_guests__in=[tier["min_guests"] for tier in TIERS],
    ).delete()


# This migration tells Django how to update the database in a repeatable way.
# This class groups the information and behaviour needed for migration.
# Keeping the related rules together makes the surrounding workflow easier to reuse and test.
class Migration(migrations.Migration):
    dependencies = [
        ("party_builder", "0003_tiered_checkout"),
    ]

    operations = [
        migrations.RunPython(seed_guest_price_tiers, remove_guest_price_tiers),
    ]
