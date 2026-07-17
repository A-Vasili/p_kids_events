# This historical migration records the database change identified as 0012_require_review_codes.
# It allows new and existing installations to reach the same stored structure or seed data in a
# repeatable order.

import party_builder.models
from django.db import migrations, models


# This class groups the information and behaviour needed for migration.
# Keeping the related rules together makes the surrounding workflow easier to reuse and test.
class Migration(migrations.Migration):
    dependencies = [("party_builder", "0011_populate_review_codes")]
    operations = [
        migrations.AlterField(
            model_name="partybuild",
            name="review_code",
            field=models.CharField(
                default=party_builder.models.generate_unique_review_code,
                editable=False,
                max_length=13,
                unique=True,
            ),
        ),
    ]
