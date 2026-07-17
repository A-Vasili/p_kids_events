# This historical migration records the database change identified as
# 0006_addonexperience_image_addonexperience_image_alt_text_and_more.
# It allows new and existing installations to reach the same stored structure or seed data in a
# repeatable order.

import django.db.models.deletion
import party_builder.validators
from django.db import migrations, models


# This class groups the information and behaviour needed for migration.
# Keeping the related rules together makes the surrounding workflow easier to reuse and test.
class Migration(migrations.Migration):

    dependencies = [
        ('party_builder', '0005_partybuild_assignment_requested_at_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='addonexperience',
            name='image',
            field=models.ImageField(blank=True, upload_to=party_builder.validators.addon_image_upload_to, validators=[party_builder.validators.validate_catalogue_image]),
        ),
        migrations.AddField(
            model_name='addonexperience',
            name='image_alt_text',
            field=models.CharField(blank=True, max_length=180),
        ),
        migrations.AddField(
            model_name='partypackage',
            name='image',
            field=models.ImageField(blank=True, upload_to=party_builder.validators.package_image_upload_to, validators=[party_builder.validators.validate_catalogue_image]),
        ),
        migrations.AddField(
            model_name='partypackage',
            name='image_alt_text',
            field=models.CharField(blank=True, max_length=180),
        ),
        migrations.CreateModel(
            name='Category',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=120)),
                ('slug', models.SlugField(max_length=140, unique=True)),
                ('description', models.TextField(blank=True, max_length=1000)),
                ('image', models.ImageField(blank=True, upload_to=party_builder.validators.category_image_upload_to, validators=[party_builder.validators.validate_catalogue_image])),
                ('image_alt_text', models.CharField(blank=True, help_text='Describe the image for visitors who cannot see it.', max_length=180)),
                ('display_order', models.PositiveSmallIntegerField(default=0)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('parent', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='children', to='party_builder.category')),
            ],
            options={
                'verbose_name_plural': 'categories',
                'ordering': ('display_order', 'name'),
            },
        ),
        migrations.AddField(
            model_name='addonexperience',
            name='category',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='addons', to='party_builder.category'),
        ),
        migrations.AddField(
            model_name='partypackage',
            name='category',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='packages', to='party_builder.category'),
        ),
        migrations.AddIndex(
            model_name='addonexperience',
            index=models.Index(fields=['is_active', 'is_featured', 'display_order'], name='party_build_is_acti_c79180_idx'),
        ),
        migrations.AddIndex(
            model_name='partypackage',
            index=models.Index(fields=['is_active', 'display_order', 'name'], name='party_build_is_acti_e8195b_idx'),
        ),
        migrations.AddIndex(
            model_name='category',
            index=models.Index(fields=['is_active', 'display_order', 'name'], name='party_build_is_acti_4728b8_idx'),
        ),
        migrations.AddIndex(
            model_name='category',
            index=models.Index(fields=['parent', 'is_active'], name='party_build_parent__13c694_idx'),
        ),
    ]
