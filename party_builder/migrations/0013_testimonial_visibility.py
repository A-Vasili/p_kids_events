# This historical migration records the database change identified as 0013_testimonial_visibility.
# It allows new and existing installations to reach the same stored structure or seed data in a
# repeatable order.

from django.conf import settings
from django.db import migrations, models


# Apply the testimonial visibility schema migration, including the fields, constraints, or indexes
# declared below. Dependencies preserve a deterministic upgrade order.
class Migration(migrations.Migration):

    dependencies = [
        ('party_builder', '0012_require_review_codes'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='partyreview',
            name='testimonial_consent_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='partyreview',
            name='testimonial_name_display',
            field=models.CharField(choices=[('anonymous', 'Anonymous'), ('first_name', 'First name only')], default='anonymous', max_length=20),
        ),
        migrations.AddField(
            model_name='partyreview',
            name='visibility',
            field=models.CharField(choices=[('private', 'Private feedback'), ('testimonial', 'Public testimonial')], db_index=True, default='private', max_length=20),
        ),
        migrations.AddIndex(
            model_name='partyreview',
            index=models.Index(fields=['visibility', 'updated_at'], name='party_build_visibil_a7d6a2_idx'),
        ),
        migrations.AddConstraint(
            model_name='partyreview',
            constraint=models.CheckConstraint(condition=models.Q(('visibility__in', ('private', 'testimonial'))), name='party_review_supported_visibility'),
        ),
        migrations.AddConstraint(
            model_name='partyreview',
            constraint=models.CheckConstraint(condition=models.Q(('testimonial_name_display__in', ('anonymous', 'first_name'))), name='party_review_supported_name_display'),
        ),
        migrations.AddConstraint(
            model_name='partyreview',
            constraint=models.CheckConstraint(condition=models.Q(('visibility', 'testimonial'), models.Q(('testimonial_consent_at__isnull', True), ('testimonial_name_display', 'anonymous')), _connector='OR'), name='party_review_private_state_is_not_public'),
        ),
    ]
