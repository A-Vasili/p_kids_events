# This historical migration records the database change identified as
# 0002_management_query_indexes.
# It allows new and existing installations to reach the same stored structure or seed data in a
# repeatable order.

from django.conf import settings
from django.db import migrations, models


# This class groups the information and behaviour needed for migration.
# Keeping the related rules together makes the surrounding workflow easier to reuse and test.
class Migration(migrations.Migration):

    dependencies = [
        ('operations', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddIndex(
            model_name='auditevent',
            index=models.Index(fields=['event_type', 'created_at'], name='operations__event_t_146c5d_idx'),
        ),
        migrations.AddIndex(
            model_name='auditevent',
            index=models.Index(fields=['actor', 'created_at'], name='operations__actor_i_65690f_idx'),
        ),
        migrations.AddIndex(
            model_name='auditevent',
            index=models.Index(fields=['object_type', 'object_id'], name='operations__object__6edc99_idx'),
        ),
    ]
