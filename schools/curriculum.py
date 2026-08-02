import re

from django.db import transaction

from academics.models import SubjectOffering, Term
from courses.models import Subject


KG_SUBJECTS = (
    "Language and Literacy", "Numeracy", "Our World Our People", "Creative Arts",
)
PRIMARY_CORE = (
    "English Language", "Mathematics", "Science", "History", "Creative Arts",
    "Religious and Moral Education", "Physical Education", "Ghanaian Language",
)
PRIMARY_UPPER_ADDITIONAL = ("French", "Computing")
JHS_SUBJECTS = (
    "English Language", "Mathematics", "Science", "Social Studies", "Computing",
    "Religious and Moral Education", "Physical and Health Education",
    "Creative Arts and Design", "Career Technology", "Ghanaian Language", "French",
)


def class_phase(class_name):
    normalised = re.sub(r"[^a-z0-9]+", " ", class_name.lower()).strip()
    if normalised.startswith(("kg", "kindergarten")):
        return "kg", None
    match = re.search(r"(?:basic|primary)\s*([1-9])", normalised)
    if match:
        level = int(match.group(1))
        return ("primary", level) if level <= 6 else ("jhs", level - 6)
    match = re.search(r"jhs\s*([1-3])", normalised)
    if match:
        return "jhs", int(match.group(1))
    return None, None


def subjects_for_class(school_class):
    phase, level = class_phase(school_class.name)
    school = school_class.school
    if phase == "kg" and school.offers_kg:
        return KG_SUBJECTS
    if phase == "primary" and school.offers_primary:
        return PRIMARY_CORE + (PRIMARY_UPPER_ADDITIONAL if level and level >= 4 else ())
    if phase == "jhs" and school.offers_jhs:
        return JHS_SUBJECTS
    return ()


@transaction.atomic
def generate_ghana_curriculum(*, school):
    subjects_created = offerings_created = 0
    unmatched_classes = []
    classes = school.classes.select_related("academic_year").all()
    for school_class in classes:
        subject_names = subjects_for_class(school_class)
        if not subject_names:
            unmatched_classes.append(school_class.name)
            continue
        terms = Term.objects.filter(academic_year=school_class.academic_year)
        for name in subject_names:
            subject = Subject.objects.filter(school=school, name__iexact=name).first()
            created = subject is None
            if created:
                subject = Subject.objects.create(
                    school=school, name=name, description="Ghana NaCCA-aligned learning area."
                )
            subjects_created += int(created)
            for term in terms:
                _, created = SubjectOffering.objects.get_or_create(
                    school=school, school_class=school_class, subject=subject, term=term
                )
                offerings_created += int(created)
    return subjects_created, offerings_created, unmatched_classes
