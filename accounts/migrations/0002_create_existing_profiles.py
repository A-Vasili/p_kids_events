# This historical migration records the database change identified as
# 0002_create_existing_profiles.
# It allows new and existing installations to reach the same stored structure or seed data in a
# repeatable order.
# This migration records a database change so every environment can build the same structure.

from django.db import migrations


# Backfill one CustomerProfile for every existing auth user during the migration, using
# get_or_create so reruns do not duplicate profiles.
def create_existing_profiles(apps, schema_editor):
    User = apps.get_model("auth", "User")
    CustomerProfile = apps.get_model("accounts", "CustomerProfile")
    for user_id in User.objects.values_list("pk", flat=True):
        CustomerProfile.objects.get_or_create(user_id=user_id)


# This migration tells Django how to update the database in a repeatable way.
# This class groups the information and behaviour needed for migration.
# Keeping the related rules together makes the surrounding workflow easier to reuse and test.
class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0001_initial"),
    ]
    operations = [
        migrations.RunPython(create_existing_profiles, migrations.RunPython.noop),
    ]
