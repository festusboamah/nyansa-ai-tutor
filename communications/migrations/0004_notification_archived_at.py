from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("communications", "0003_repair_notification_targets")]
    operations = [
        migrations.AddField(
            model_name="notification",
            name="archived_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
