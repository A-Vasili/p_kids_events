from django.db import migrations, models


# This migration changes only the staff-facing wording for the existing waiting status; stored
# values, unread behaviour, and chat permissions remain exactly the same.
class Migration(migrations.Migration):

    dependencies = [
        ('communications', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='customerchat',
            name='status',
            field=models.CharField(choices=[('waiting_staff', 'Waiting for P Kids Events'), ('waiting_customer', 'Waiting for customer')], default='waiting_staff', max_length=24),
        ),
    ]
