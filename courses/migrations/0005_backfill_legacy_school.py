from django.db import migrations


LEGACY_SCHOOL_SLUG = "nyansa-legacy"


def backfill_legacy_school(apps, schema_editor):
    database = schema_editor.connection.alias
    User = apps.get_model("accounts", "User")
    Subject = apps.get_model("courses", "Subject")
    StudyDocument = apps.get_model("courses", "StudyDocument")
    School = apps.get_model("schools", "School")
    SchoolMembership = apps.get_model("schools", "SchoolMembership")

    if not (
        User.objects.using(database).exists()
        or Subject.objects.using(database).exists()
        or StudyDocument.objects.using(database).exists()
    ):
        return

    school, _created = School.objects.using(database).get_or_create(
        slug=LEGACY_SCHOOL_SLUG,
        defaults={"name": "Nyansa Legacy School", "timezone": "Africa/Accra"},
    )
    Subject.objects.using(database).filter(school__isnull=True).update(school=school)
    StudyDocument.objects.using(database).filter(school__isnull=True).update(school=school)

    for user in User.objects.using(database).all().iterator():
        role = "TEACHER" if user.role == "TEACHER" else "STUDENT"
        SchoolMembership.objects.using(database).get_or_create(
            school=school,
            user=user,
            defaults={"role": role, "status": "ACTIVE"},
        )


def reverse_legacy_school(apps, schema_editor):
    database = schema_editor.connection.alias
    Subject = apps.get_model("courses", "Subject")
    StudyDocument = apps.get_model("courses", "StudyDocument")
    School = apps.get_model("schools", "School")

    legacy_schools = School.objects.using(database).filter(slug=LEGACY_SCHOOL_SLUG)
    Subject.objects.using(database).filter(school__in=legacy_schools).update(school=None)
    StudyDocument.objects.using(database).filter(school__in=legacy_schools).update(school=None)
    legacy_schools.delete()


class Migration(migrations.Migration):
    dependencies = [
        ("schools", "0001_initial"),
        ("courses", "0004_add_school_ownership"),
    ]

    operations = [migrations.RunPython(backfill_legacy_school, reverse_legacy_school)]
