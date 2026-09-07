from django.db import migrations


OLD_DESCRIPTION = (
    "For a single independent teacher, not a school. Unlimited lesson notes, "
    "schemes of learning, and student notes after your free generations are used. "
    "PLACEHOLDER PRICE - adjust before promoting this plan."
)
NEW_DESCRIPTION = (
    "For a single independent teacher, not a school. Lesson notes, schemes of "
    "learning, and student notes after your free generations are used - up to "
    "30 AI generations per month, resetting each billing period."
)
OLD_PRICE = "50.00"
NEW_PRICE = "30.00"


def update_plan(apps, schema_editor):
    LicensePlan = apps.get_model("billing", "LicensePlan")
    LicensePlan.objects.filter(code="INDIVIDUAL").update(description=NEW_DESCRIPTION, base_price=NEW_PRICE)


def revert_plan(apps, schema_editor):
    LicensePlan = apps.get_model("billing", "LicensePlan")
    LicensePlan.objects.filter(code="INDIVIDUAL").update(description=OLD_DESCRIPTION, base_price=OLD_PRICE)


class Migration(migrations.Migration):
    dependencies = [
        ("billing", "0005_update_individual_plan_description"),
    ]
    operations = [
        migrations.RunPython(update_plan, revert_plan),
    ]
