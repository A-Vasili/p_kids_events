# This historical migration records the database change identified as 0003_tiered_checkout.
# It allows new and existing installations to reach the same stored structure or seed data in a
# repeatable order.
# This migration records a database change so every environment can build the same structure.

import django.core.validators
import django.db.models.deletion
from decimal import Decimal
from django.db import migrations, models


# This migration tells Django how to update the database in a repeatable way.
# This class groups the information and behaviour needed for migration.
# Keeping the related rules together makes the surrounding workflow easier to reuse and test.
class Migration(migrations.Migration):

    dependencies = [
        ('party_builder', '0002_seed_party_builder'),
    ]

    operations = [
        migrations.AddField(
            model_name='partybuild',
            name='addon_price',
            field=models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=9, validators=[django.core.validators.MinValueValidator(Decimal('0.00'))]),
        ),
        migrations.AddField(
            model_name='partybuild',
            name='card_brand',
            field=models.CharField(blank=True, max_length=30),
        ),
        migrations.AddField(
            model_name='partybuild',
            name='card_last_four',
            field=models.CharField(blank=True, max_length=4),
        ),
        migrations.AddField(
            model_name='partybuild',
            name='checkout_completed_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='partybuild',
            name='event_address',
            field=models.CharField(blank=True, max_length=240),
        ),
        migrations.AddField(
            model_name='partybuild',
            name='event_time',
            field=models.TimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='partybuild',
            name='guest_tier_label',
            field=models.CharField(blank=True, max_length=60),
        ),
        migrations.AddField(
            model_name='partybuild',
            name='package_price',
            field=models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=9, validators=[django.core.validators.MinValueValidator(Decimal('0.00'))]),
        ),
        migrations.AddField(
            model_name='partybuild',
            name='payment_reference',
            field=models.CharField(blank=True, max_length=40),
        ),
        migrations.AddField(
            model_name='partybuild',
            name='payment_status',
            field=models.CharField(choices=[('simulated', 'Simulated payment accepted'), ('not_required', 'No payment data')], default='not_required', max_length=20),
        ),
        migrations.AddField(
            model_name='partybuild',
            name='postal_code',
            field=models.CharField(blank=True, max_length=10, validators=[django.core.validators.RegexValidator(message='Enter a valid postal code.', regex='^[A-Za-z0-9][A-Za-z0-9\\s-]{2,9}$')]),
        ),
        migrations.AlterField(
            model_name='addonexperience',
            name='icon',
            field=models.CharField(default='✦', help_text='A short decorative symbol hidden from assistive technology.', max_length=8),
        ),
        migrations.AlterField(
            model_name='partybuild',
            name='status',
            field=models.CharField(choices=[('submitted', 'Submitted'), ('contacted', 'Contacted'), ('confirmed', 'Confirmed'), ('cancelled', 'Cancelled')], default='submitted', max_length=20),
        ),
        migrations.AlterField(
            model_name='partybuild',
            name='total_price',
            field=models.DecimalField(decimal_places=2, help_text='Server-calculated total at simulated checkout.', max_digits=9, validators=[django.core.validators.MinValueValidator(Decimal('0.00'))]),
        ),
        migrations.AlterField(
            model_name='partypackage',
            name='base_price',
            field=models.DecimalField(decimal_places=2, help_text='Reference price for the smallest active guest bracket.', max_digits=8, validators=[django.core.validators.MinValueValidator(Decimal('0.00'))]),
        ),
        migrations.AlterField(
            model_name='partypackage',
            name='included_guest_count',
            field=models.PositiveIntegerField(default=10, validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(200)]),
        ),
        migrations.AlterField(
            model_name='partypackage',
            name='is_default',
            field=models.BooleanField(default=False, help_text='The package used when the multi-step checkout opens.'),
        ),
        migrations.CreateModel(
            name='GuestPriceTier',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('label', models.CharField(max_length=60)),
                ('min_guests', models.PositiveSmallIntegerField(validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(200)])),
                ('max_guests', models.PositiveSmallIntegerField(validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(200)])),
                ('total_price', models.DecimalField(decimal_places=2, max_digits=8, validators=[django.core.validators.MinValueValidator(Decimal('0.00'))])),
                ('is_default', models.BooleanField(default=False)),
                ('is_active', models.BooleanField(default=True)),
                ('display_order', models.PositiveSmallIntegerField(default=0)),
                ('package', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='guest_price_tiers', to='party_builder.partypackage')),
            ],
            options={
                'ordering': ('display_order', 'min_guests'),
            },
        ),
        migrations.AddField(
            model_name='partybuild',
            name='guest_tier',
            field=models.ForeignKey(blank=True, help_text='Nullable only for legacy requests created before tiered pricing.', null=True, on_delete=django.db.models.deletion.PROTECT, related_name='builds', to='party_builder.guestpricetier'),
        ),
        migrations.AddConstraint(
            model_name='guestpricetier',
            constraint=models.CheckConstraint(condition=models.Q(('total_price__gte', 0)), name='guest_tier_price_non_negative'),
        ),
        migrations.AddConstraint(
            model_name='guestpricetier',
            constraint=models.CheckConstraint(condition=models.Q(('max_guests__gte', models.F('min_guests'))), name='guest_tier_valid_range'),
        ),
        migrations.AddConstraint(
            model_name='guestpricetier',
            constraint=models.UniqueConstraint(fields=('package', 'min_guests', 'max_guests'), name='guest_tier_unique_range_per_package'),
        ),
        migrations.AddConstraint(
            model_name='guestpricetier',
            constraint=models.UniqueConstraint(condition=models.Q(('is_default', True)), fields=('package',), name='guest_tier_single_default_per_package'),
        ),
    ]
