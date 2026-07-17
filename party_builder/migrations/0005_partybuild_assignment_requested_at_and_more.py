# This historical migration records the database change identified as
# 0005_partybuild_assignment_requested_at_and_more.
# It allows new and existing installations to reach the same stored structure or seed data in a
# repeatable order.
# This migration records a database change so every environment can build the same structure.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


# This migration tells Django how to update the database in a repeatable way.
# This class groups the information and behaviour needed for migration.
# Keeping the related rules together makes the surrounding workflow easier to reuse and test.
class Migration(migrations.Migration):

    dependencies = [
        ('party_builder', '0004_seed_guest_price_tiers'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='partybuild',
            name='assignment_requested_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='partybuild',
            name='assignment_state',
            field=models.CharField(choices=[('unassigned', 'Unassigned'), ('pending_acceptance', 'Awaiting worker response'), ('assigned', 'Worker assigned'), ('manual_review', 'Owner review required')], default='unassigned', max_length=30),
        ),
        migrations.AddField(
            model_name='partybuild',
            name='customer',
            field=models.ForeignKey(blank=True, help_text='Empty for guest checkouts.', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='party_bookings', to=settings.AUTH_USER_MODEL),
        ),
    ]
