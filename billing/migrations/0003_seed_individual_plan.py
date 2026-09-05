from django.db import migrations


# Placeholder pricing - adjust via Django admin once real pricing is decided.
PLAN = {
    "code": "INDIVIDUAL",
    "name": "Individual Teacher",
    "description": (
        "For a single independent teacher, not a school. Unlimited lesson notes, "
        "schemes of learning, and student notes after the 3 free generations. "
        "PLACEHOLDER PRICE - adjust before promoting this plan."
    ),
    "base_price": "50.00",
    "currency": "GHS",
    "ai_usage_markup_percent": None,
}


def seed_plan(apps, schema_editor):
    LicensePlan = apps.get_model("billing", "LicensePlan")
    LicensePlan.objects.update_or_create(code=PLAN["code"], defaults=PLAN)


def remove_plan(apps, schema_editor):
    LicensePlan = apps.get_model("billing", "LicensePlan")
    LicensePlan.objects.filter(code=PLAN["code"]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("billing", "0002_seed_license_plans"),
    ]
    operations = [
        migrations.RunPython(seed_plan, remove_plan),
    ]
