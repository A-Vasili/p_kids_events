# This historical migration records the database change identified as
# 0008_require_catalogue_categories.
# It allows new and existing installations to reach the same stored structure or seed data in a
# repeatable order.


import django.db.models.deletion
from django.db import migrations, models


# This class groups the information and behaviour needed for migration.
# Keeping the related rules together makes the surrounding workflow easier to reuse and test.
class Migration(migrations.Migration):
    dependencies = [
        ("party_builder", "0007_seed_catalogue_categories"),
    ]

    operations = [
        migrations.AlterField(
            model_name="addonexperience",
            name="category",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="addons",
                to="party_builder.category",
            ),
        ),
        migrations.AlterField(
            model_name="partypackage",
            name="category",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="packages",
                to="party_builder.category",
            ),
        ),
    ]
