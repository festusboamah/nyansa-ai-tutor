from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("schools", "0003_school_student_access_and_profile")]
    operations = [
        migrations.AddField(model_name="school", name="offers_kg", field=models.BooleanField(default=False)),
        migrations.AddField(model_name="school", name="offers_primary", field=models.BooleanField(default=True)),
        migrations.AddField(model_name="school", name="offers_jhs", field=models.BooleanField(default=False)),
    ]
