from django.db import migrations


OLD_DESCRIPTION = (
    "For a single independent teacher, not a school. Unlimited lesson notes, "
    "schemes of learning, and student notes after the 3 free generations. "
    "PLACEHOLDER PRICE - adjust before promoting this plan."
)
NEW_DESCRIPTION = (
    "For a single independent teacher, not a school. Unlimited lesson notes, "
    "schemes of learning, and student notes after your free generations are used. "
    "PLACEHOLDER PRICE - adjust before promoting this plan."
)


def update_description(apps, schema_editor):
    LicensePlan = apps.get_model("billing", "LicensePlan")
    LicensePlan.objects.filter(code="INDIVIDUAL").update(description=NEW_DESCRIPTION)


def revert_description(apps, schema_editor):
    LicensePlan = apps.get_model("billing", "LicensePlan")
    LicensePlan.objects.filter(code="INDIVIDUAL").update(description=OLD_DESCRIPTION)


class Migration(migrations.Migration):
    dependencies = [
        ("billing", "0004_alter_licenseplan_code"),
    ]
    operations = [
        migrations.RunPython(update_description, revert_description),
    ]
