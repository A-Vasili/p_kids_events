# This historical migration records the database change identified as
# 0009_management_query_indexes.
# It allows new and existing installations to reach the same stored structure or seed data in a
# repeatable order.

from django.conf import settings
from django.db import migrations, models


# Apply the management query indexes schema migration, including the fields, constraints, or indexes
# declared below. Dependencies preserve a deterministic upgrade order.
class Migration(migrations.Migration):

    dependencies = [
        ('party_builder', '0008_require_catalogue_categories'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddIndex(
            model_name='partybuild',
            index=models.Index(fields=['event_date', 'status'], name='party_build_event_d_56ccc4_idx'),
        ),
        migrations.AddIndex(
            model_name='partybuild',
            index=models.Index(fields=['assignment_state', 'event_date'], name='party_build_assignm_f7285d_idx'),
        ),
        migrations.AddIndex(
            model_name='partybuild',
            index=models.Index(fields=['contact_email'], name='party_build_contact_59e0c5_idx'),
        ),
    ]
