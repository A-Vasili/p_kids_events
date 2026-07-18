# This historical migration records the database change identified as 0010_review_system.
# It allows new and existing installations to reach the same stored structure or seed data in a
# repeatable order.

import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


# Create the AddonRating and PartyReview database tables and their declared relationships,
# constraints, and indexes. This initial schema is applied only after its listed migration
# dependencies.
class Migration(migrations.Migration):

    dependencies = [
        ('party_builder', '0009_management_query_indexes'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='AddonRating',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('score', models.PositiveSmallIntegerField(validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(5)])),
                ('comment', models.CharField(blank=True, max_length=500)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'ordering': ('build_addon__addon__display_order', 'build_addon__addon__name'),
            },
        ),
        migrations.CreateModel(
            name='PartyReview',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('package_score', models.PositiveSmallIntegerField(validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(5)])),
                ('comment', models.TextField(blank=True, max_length=1500)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'ordering': ('-updated_at',),
            },
        ),
        migrations.AddField(
            model_name='partybuild',
            name='completed_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='partybuild',
            name='review_code',
            field=models.CharField(blank=True, editable=False, max_length=13, null=True),
        ),
        migrations.AlterField(
            model_name='partybuild',
            name='status',
            field=models.CharField(choices=[('submitted', 'Submitted'), ('contacted', 'Contacted'), ('confirmed', 'Confirmed'), ('completed', 'Completed'), ('cancelled', 'Cancelled')], default='submitted', max_length=20),
        ),
        migrations.AddIndex(
            model_name='partybuild',
            index=models.Index(fields=['status', 'completed_at'], name='party_build_status_3eb0bd_idx'),
        ),
        migrations.AddField(
            model_name='addonrating',
            name='build_addon',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='ratings', to='party_builder.partybuildaddon'),
        ),
        migrations.AddField(
            model_name='partyreview',
            name='booking',
            field=models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='review', to='party_builder.partybuild'),
        ),
        migrations.AddField(
            model_name='partyreview',
            name='reviewer',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='party_reviews', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='addonrating',
            name='review',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='addon_ratings', to='party_builder.partyreview'),
        ),
        migrations.AddIndex(
            model_name='partyreview',
            index=models.Index(fields=['reviewer', 'updated_at'], name='party_build_reviewe_ee24e8_idx'),
        ),
        migrations.AddIndex(
            model_name='partyreview',
            index=models.Index(fields=['package_score', 'updated_at'], name='party_build_package_6f8fec_idx'),
        ),
        migrations.AddConstraint(
            model_name='partyreview',
            constraint=models.CheckConstraint(condition=models.Q(('package_score__gte', 1), ('package_score__lte', 5)), name='party_review_package_score_1_to_5'),
        ),
        migrations.AddIndex(
            model_name='addonrating',
            index=models.Index(fields=['build_addon', 'score'], name='party_build_build_a_d22fb5_idx'),
        ),
        migrations.AddIndex(
            model_name='addonrating',
            index=models.Index(fields=['review', 'updated_at'], name='party_build_review__d913ae_idx'),
        ),
        migrations.AddConstraint(
            model_name='addonrating',
            constraint=models.CheckConstraint(condition=models.Q(('score__gte', 1), ('score__lte', 5)), name='addon_rating_score_1_to_5'),
        ),
        migrations.AddConstraint(
            model_name='addonrating',
            constraint=models.UniqueConstraint(fields=('review', 'build_addon'), name='one_rating_per_selected_booking_addon'),
        ),
    ]
