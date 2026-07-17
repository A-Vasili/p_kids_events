# This historical migration records the database change identified as
# 0007_seed_catalogue_categories.
# It allows new and existing installations to reach the same stored structure or seed data in a
# repeatable order.

from django.db import migrations


# This forward migration prepares the historical records required by this release while preserving
# existing customised data where the migration allows it.
def seed_categories(apps, schema_editor):
    Category = apps.get_model("party_builder", "Category")
    PartyPackage = apps.get_model("party_builder", "PartyPackage")
    AddonExperience = apps.get_model("party_builder", "AddonExperience")

    package_category, _ = Category.objects.get_or_create(
        slug="party-packages",
        defaults={
            "name": "Party Packages",
            "description": "Core party packages available through checkout.",
            "display_order": 10,
            "is_active": True,
        },
    )
    experience_category, _ = Category.objects.get_or_create(
        slug="experiences",
        defaults={
            "name": "Experiences",
            "description": "Optional party add-ons and entertainment experiences.",
            "display_order": 20,
            "is_active": True,
        },
    )

    PartyPackage.objects.filter(category__isnull=True).update(category=package_category)
    AddonExperience.objects.filter(category__isnull=True).update(category=experience_category)


# This reverse step removes or restores only what can be changed safely, avoiding damage to
# records that later activity may already reference.
def reverse_seed(apps, schema_editor):
    # Existing records keep their category assignments if this migration is
    # reversed; removing them would discard useful user data.
    pass


# This class groups the information and behaviour needed for migration.
# Keeping the related rules together makes the surrounding workflow easier to reuse and test.
class Migration(migrations.Migration):
    dependencies = [
        ("party_builder", "0006_addonexperience_image_addonexperience_image_alt_text_and_more"),
    ]

    operations = [migrations.RunPython(seed_categories, reverse_seed)]
