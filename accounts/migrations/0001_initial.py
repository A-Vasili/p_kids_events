# This historical migration records the database change identified as 0001_initial.
# It allows new and existing installations to reach the same stored structure or seed data in a
# repeatable order.
# This migration records a database change so every environment can build the same structure.

import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


# This migration tells Django how to update the database in a repeatable way.
# This class groups the information and behaviour needed for migration.
# Keeping the related rules together makes the surrounding workflow easier to reuse and test.
class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='CustomerProfile',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('phone', models.CharField(blank=True, max_length=30, validators=[django.core.validators.RegexValidator(message='Enter a valid phone number.', regex='^\\+?[0-9\\s().-]{7,30}$')])),
                ('default_address', models.CharField(blank=True, max_length=240)),
                ('default_postal_code', models.CharField(blank=True, max_length=10, validators=[django.core.validators.RegexValidator(message='Enter a valid postal code.', regex='^[A-Za-z0-9][A-Za-z0-9\\s-]{2,9}$')])),
                ('preferred_language', models.CharField(choices=[('en', 'English'), ('el', 'Greek')], default='en', max_length=2)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='customer_profile', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ('user__last_name', 'user__first_name', 'user__username'),
            },
        ),
        migrations.CreateModel(
            name='WorkerProfile',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('display_name', models.CharField(blank=True, max_length=120)),
                ('phone', models.CharField(blank=True, max_length=30, validators=[django.core.validators.RegexValidator(message='Enter a valid phone number.', regex='^\\+?[0-9\\s().-]{7,30}$')])),
                ('is_active_worker', models.BooleanField(default=True, help_text='Inactive workers remain in history but receive no new assignments.')),
                ('max_daily_parties', models.PositiveSmallIntegerField(default=2, validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(10)])),
                ('notes_for_owner', models.TextField(blank=True, help_text='Private operational notes visible only to owners and administrators.', max_length=1000)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='worker_profile', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ('display_name', 'user__username'),
                'permissions': [('manage_worker_roles', 'Can promote, demote, and activate workers'), ('manage_pricing_rights', 'Can grant or revoke pricing-management rights'), ('view_all_worker_schedules', 'Can view all worker schedules')],
            },
        ),
    ]
