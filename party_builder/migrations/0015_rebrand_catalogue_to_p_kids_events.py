from django.db import migrations


# This migration updates only the original seeded package names. Exact-value checks protect any
# package names that an Owner has already customised through the management panel.
def apply_p_kids_events_catalogue_name(apps, schema_editor):
    PartyPackage = apps.get_model("party_builder", "PartyPackage")
    Category = apps.get_model("party_builder", "Category")

    package_names = {
        "Basic Popadoo Party": "Basic P Kids Events Party",
        "Popadoo Plus Party": "P Kids Events Plus Party",
        "Popadoo Classic Party": "P Kids Events Classic Party",
        "Popadoo Big Party": "P Kids Events Big Party",
        "Popadoo XL Party": "P Kids Events XL Party",
        "Popadoo Mega Party": "P Kids Events Mega Party",
        "Popadoo Super Party": "P Kids Events Super Party",
        "Popadoo Festival Party": "P Kids Events Festival Party",
    }
    for old_name, new_name in package_names.items():
        PartyPackage.objects.filter(name=old_name).update(name=new_name)

    Category.objects.filter(
        slug="party-packages",
        description="Capacity-based starting packages for Popadoo celebrations.",
    ).update(
        description="Capacity-based starting packages for P Kids Events celebrations."
    )


# Reversal restores only values produced by this migration, so later Owner customisations are not
# overwritten when a deployment is rolled back.
def restore_previous_catalogue_name(apps, schema_editor):
    PartyPackage = apps.get_model("party_builder", "PartyPackage")
    Category = apps.get_model("party_builder", "Category")

    package_names = {
        "Basic P Kids Events Party": "Basic Popadoo Party",
        "P Kids Events Plus Party": "Popadoo Plus Party",
        "P Kids Events Classic Party": "Popadoo Classic Party",
        "P Kids Events Big Party": "Popadoo Big Party",
        "P Kids Events XL Party": "Popadoo XL Party",
        "P Kids Events Mega Party": "Popadoo Mega Party",
        "P Kids Events Super Party": "Popadoo Super Party",
        "P Kids Events Festival Party": "Popadoo Festival Party",
    }
    for new_name, old_name in package_names.items():
        PartyPackage.objects.filter(name=new_name).update(name=old_name)

    Category.objects.filter(
        slug="party-packages",
        description="Capacity-based starting packages for P Kids Events celebrations.",
    ).update(
        description="Capacity-based starting packages for Popadoo celebrations."
    )


# This migration changes presentation data only; package slugs, prices, capacities, bookings, and
# image relationships remain unchanged so existing links and historical records continue to work.
class Migration(migrations.Migration):
    dependencies = [("party_builder", "0014_seed_capacity_packages_and_experiences")]

    operations = [
        migrations.RunPython(
            apply_p_kids_events_catalogue_name,
            restore_previous_catalogue_name,
        )
    ]
