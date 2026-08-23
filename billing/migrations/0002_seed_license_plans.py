from django.db import migrations


PLANS = [
    {
        "code": "STARTER",
        "name": "Starter",
        "description": (
            "Learning Workspace core: subjects, materials, assignments, quizzes, "
            "gradebook, and basic analytics. No AI Tutor or Teacher Copilot."
        ),
        "base_price": "500.00",
        "currency": "GHS",
        "ai_usage_markup_percent": None,
    },
    {
        "code": "STANDARD",
        "name": "Standard",
        "description": (
            "Everything in Starter, plus the AI Tutor, Teacher Copilot, Mastery, "
            "and AI-generated analytics narratives. Base fee plus AI usage cost at "
            "cost + 20%, billed monthly."
        ),
        "base_price": "1500.00",
        "currency": "GHS",
        "ai_usage_markup_percent": "20.00",
    },
    {
        "code": "PARTNER",
        "name": "Partner",
        "description": (
            "Includes the outbound Suku360 integration API. Contact us - priced "
            "per partnership, not a fixed monthly fee."
        ),
        "base_price": "0.00",
        "currency": "GHS",
        "ai_usage_markup_percent": None,
    },
]


def seed_plans(apps, schema_editor):
    LicensePlan = apps.get_model("billing", "LicensePlan")
    for plan in PLANS:
        LicensePlan.objects.update_or_create(code=plan["code"], defaults=plan)


def remove_plans(apps, schema_editor):
    LicensePlan = apps.get_model("billing", "LicensePlan")
    LicensePlan.objects.filter(code__in=[plan["code"] for plan in PLANS]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("billing", "0001_initial"),
    ]
    operations = [
        migrations.RunPython(seed_plans, remove_plans),
    ]
