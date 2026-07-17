# This historical migration records the database change identified as 0001_initial.
# It allows new and existing installations to reach the same stored structure or seed data in a
# repeatable order.
# Only explanatory comments belong here because changing a past migration could make databases
# disagree.
# This migration records a database change so every environment can build the same structure.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


# This migration tells Django how to update the database in a repeatable way.
# This class groups the information and behaviour needed for migration.
# Keeping the related rules together makes the surrounding workflow easier to reuse and test.
class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('accounts', '0001_initial'),
        ('party_builder', '0005_partybuild_assignment_requested_at_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='AuditEvent',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('event_type', models.CharField(max_length=80)),
                ('object_type', models.CharField(max_length=80)),
                ('object_id', models.CharField(blank=True, max_length=80)),
                ('summary', models.CharField(max_length=300)),
                ('before_data', models.JSONField(blank=True, default=dict)),
                ('after_data', models.JSONField(blank=True, default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('actor', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='popadoo_audit_events', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ('-created_at',),
            },
        ),
        migrations.CreateModel(
            name='PartyAssignment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('status', models.CharField(choices=[('pending', 'Pending response'), ('accepted', 'Accepted'), ('declined', 'Declined'), ('superseded', 'Superseded'), ('cancelled', 'Cancelled')], default='pending', max_length=20)),
                ('assignment_source', models.CharField(choices=[('automatic', 'Automatic'), ('owner_manual', 'Owner manual'), ('admin_override', 'Administrator override')], default='automatic', max_length=20)),
                ('assigned_at', models.DateTimeField(auto_now_add=True)),
                ('responded_at', models.DateTimeField(blank=True, null=True)),
                ('decline_reason', models.CharField(blank=True, max_length=500)),
                ('owner_note', models.CharField(blank=True, max_length=500)),
                ('conflict_override_reason', models.CharField(blank=True, max_length=500)),
                ('assigned_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='created_party_assignments', to=settings.AUTH_USER_MODEL)),
                ('party_build', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='assignments', to='party_builder.partybuild')),
                ('worker', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='assignments', to='accounts.workerprofile')),
            ],
            options={
                'ordering': ('-assigned_at',),
                'permissions': [('view_all_schedules', 'Can view all worker schedules'), ('manually_assign_party', 'Can manually assign parties to workers')],
                'indexes': [models.Index(fields=['worker', 'status', 'assigned_at'], name='operations__worker__fb9773_idx'), models.Index(fields=['party_build', 'status'], name='operations__party_b_8d393f_idx')],
                'constraints': [models.UniqueConstraint(condition=models.Q(('status', 'accepted')), fields=('party_build',), name='operations_one_accepted_assignment_per_booking'), models.UniqueConstraint(condition=models.Q(('status', 'pending')), fields=('party_build', 'worker'), name='operations_one_pending_offer_per_worker_booking')],
            },
        ),
        migrations.CreateModel(
            name='WorkerAvailability',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('start_at', models.DateTimeField()),
                ('end_at', models.DateTimeField()),
                ('availability_type', models.CharField(choices=[('available', 'Available'), ('preferred', 'Preferred'), ('unavailable', 'Unavailable')], default='available', max_length=20)),
                ('notes', models.CharField(blank=True, max_length=300)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('worker', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='availability_periods', to='accounts.workerprofile')),
            ],
            options={
                'ordering': ('start_at', 'worker__display_name'),
                'permissions': [('manage_all_availability', "Can manage every worker's availability")],
                'indexes': [models.Index(fields=['worker', 'start_at', 'end_at'], name='operations__worker__f0ce25_idx')],
            },
        ),
    ]
