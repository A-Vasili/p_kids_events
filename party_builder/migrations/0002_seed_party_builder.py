# This historical migration records the database change identified as 0002_seed_party_builder.
# It allows new and existing installations to reach the same stored structure or seed data in a
# repeatable order.
# This migration records a database change so every environment can build the same structure.

from decimal import Decimal

from django.db import migrations


PACKAGE = {
    "name": "Basic Popadoo Party",
    "slug": "basic-popadoo-party",
    "short_description": (
        "A two-hour mobile party foundation with a host, organised games, "
        "music, and essential event coordination for up to 15 children."
    ),
    "base_price": Decimal("180.00"),
    "duration_minutes": 120,
    "included_guest_count": 15,
    "included_experiences": (
        "One trained party host\n"
        "Music and movement games\n"
        "Age-appropriate group activities\n"
        "Basic activity equipment and setup\n"
        "Event flow and parent coordination"
    ),
    "is_default": True,
    "is_active": True,
    "display_order": 10,
}

ADDONS = [
    {
        "name": "Face Painting",
        "slug": "face-painting",
        "short_description": "Colourful, child-friendly designs during the party.",
        "price": Decimal("70.00"),
        "duration_minutes": 0,
        "icon": "🎨",
        "is_featured": True,
        "display_order": 10,
    },
    {
        "name": "Balloon Modelling",
        "slug": "balloon-modelling",
        "short_description": "Twisted balloon creations for children to enjoy and take home.",
        "price": Decimal("60.00"),
        "duration_minutes": 0,
        "icon": "🎈",
        "is_featured": True,
        "display_order": 20,
    },
    {
        "name": "Treasure Hunt",
        "slug": "treasure-hunt",
        "short_description": "A guided clue trail adapted to the venue and age group.",
        "price": Decimal("75.00"),
        "duration_minutes": 30,
        "icon": "🗺️",
        "is_featured": True,
        "display_order": 30,
    },
    {
        "name": "Creative Craft Workshop",
        "slug": "creative-craft-workshop",
        "short_description": "A supervised make-and-take activity with basic materials included.",
        "price": Decimal("85.00"),
        "duration_minutes": 45,
        "icon": "✂️",
        "is_featured": False,
        "display_order": 40,
    },
    {
        "name": "Mini Magic Show",
        "slug": "mini-magic-show",
        "short_description": "An interactive magic performance designed for children.",
        "price": Decimal("110.00"),
        "duration_minutes": 40,
        "icon": "🎩",
        "is_featured": True,
        "display_order": 50,
    },
    {
        "name": "Themed Balloon Decoration",
        "slug": "themed-balloon-decoration",
        "short_description": "A coordinated balloon arrangement for the main celebration area.",
        "price": Decimal("95.00"),
        "duration_minutes": 0,
        "icon": "🌈",
        "is_featured": False,
        "display_order": 60,
    },
    {
        "name": "Extra Entertainer",
        "slug": "extra-entertainer",
        "short_description": "Recommended for larger groups or parallel activities.",
        "price": Decimal("80.00"),
        "duration_minutes": 0,
        "icon": "🧑‍🤝‍🧑",
        "is_featured": False,
        "display_order": 70,
    },
    {
        "name": "Party Favour Pack",
        "slug": "party-favour-pack",
        "short_description": "Simple take-home favour packs for up to 15 children.",
        "price": Decimal("45.00"),
        "duration_minutes": 0,
        "icon": "🎁",
        "is_featured": False,
        "display_order": 80,
    },
]


# This migration helper inserts the starting package and add-ons into a new database.
# This forward migration prepares the historical records required by this release while preserving
# existing customised data where the migration allows it.
def seed_party_builder(apps, schema_editor):
    PartyPackage = apps.get_model("party_builder", "PartyPackage")
    AddonExperience = apps.get_model("party_builder", "AddonExperience")

    PartyPackage.objects.update_or_create(
        slug=PACKAGE["slug"],
        defaults=PACKAGE,
    )

    for addon in ADDONS:
        AddonExperience.objects.update_or_create(
            slug=addon["slug"],
            defaults={**addon, "is_active": True},
        )


# This helper removes seed data after the required checks.
# This migration helper performs the data part of the historical change recorded in this file.
def remove_seed_data(apps, schema_editor):
    PartyPackage = apps.get_model("party_builder", "PartyPackage")
    AddonExperience = apps.get_model("party_builder", "AddonExperience")

    PartyPackage.objects.filter(slug=PACKAGE["slug"]).delete()
    AddonExperience.objects.filter(
        slug__in=[addon["slug"] for addon in ADDONS]
    ).delete()


# This migration tells Django how to update the database in a repeatable way.
# This class groups the information and behaviour needed for migration.
# Keeping the related rules together makes the surrounding workflow easier to reuse and test.
class Migration(migrations.Migration):
    dependencies = [("party_builder", "0001_initial")]

    operations = [
        migrations.RunPython(seed_party_builder, remove_seed_data),
    ]
