import re

from django.db import transaction

from academics.models import SubjectOffering, Term
from academics.models import AcademicYear, SchoolClass
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

# SHS, STEM, and TVET are programme-based (a school offering them typically runs
# several elective tracks/trades, which vary too much per school to guess safely).
# These lists are deliberately just the compulsory subjects every student in that
# programme takes regardless of track/trade - electives and trade specializations
# are added by the school itself through the normal "Add offering" flow, same as
# any custom subject today.
SHS_CORE_SUBJECTS = ("English Language", "Core Mathematics", "Integrated Science", "Social Studies")
STEM_CORE_SUBJECTS = SHS_CORE_SUBJECTS + ("Elective Mathematics", "Computing")
TVET_CORE_SUBJECTS = ("English Language", "Mathematics", "ICT")

LEVEL_CLASS_NAMES = {
    "kg": ("KG 1", "KG 2"),
    "primary": tuple(f"Basic {level}" for level in range(1, 7)),
    "jhs": tuple(f"JHS {level}" for level in range(1, 4)),
    "shs": ("SHS 1", "SHS 2", "SHS 3"),
    "stem": ("STEM 1", "STEM 2", "STEM 3"),
    "tvet": ("TVET 1", "TVET 2", "TVET 3"),
}


@transaction.atomic
def generate_school_classes(*, school):
    academic_year = AcademicYear.objects.filter(school=school, is_current=True).first()
    if academic_year is None:
        academic_year = AcademicYear.objects.filter(school=school).order_by("-start_date").first()
    if academic_year is None:
        return None, 0
    selected_phases = []
    if school.offers_kg:
        selected_phases.append("kg")
    if school.offers_primary:
        selected_phases.append("primary")
    if school.offers_jhs:
        selected_phases.append("jhs")
    if school.offers_shs:
        selected_phases.append("shs")
    if school.offers_stem:
        selected_phases.append("stem")
    if school.offers_tvet:
        selected_phases.append("tvet")
    suffixes = ("A", "B") if school.stream_structure == school.StreamStructure.DOUBLE else ("",)
    created_count = 0
    for phase in selected_phases:
        for base_name in LEVEL_CLASS_NAMES[phase]:
            for suffix in suffixes:
                _, created = SchoolClass.objects.get_or_create(
                    school=school,
                    academic_year=academic_year,
                    name=f"{base_name}{suffix}",
                )
                created_count += int(created)
    return academic_year, created_count


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
    match = re.search(r"stem\s*([1-3])", normalised)
    if match:
        return "stem", int(match.group(1))
    match = re.search(r"tvet\s*([1-3])", normalised)
    if match:
        return "tvet", int(match.group(1))
    match = re.search(r"shs\s*([1-3])", normalised)
    if match:
        return "shs", int(match.group(1))
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
    if phase == "shs" and school.offers_shs:
        return SHS_CORE_SUBJECTS
    if phase == "stem" and school.offers_stem:
        return STEM_CORE_SUBJECTS
    if phase == "tvet" and school.offers_tvet:
        return TVET_CORE_SUBJECTS
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
