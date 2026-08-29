from datetime import date

from django.test import TestCase

from academics.models import AcademicYear, SchoolClass, Term

from .curriculum import (
    SHS_CORE_SUBJECTS,
    STEM_CORE_SUBJECTS,
    TVET_CORE_SUBJECTS,
    class_phase,
    generate_ghana_curriculum,
    generate_school_classes,
    subjects_for_class,
)
from .models import School


class CurriculumPhaseParsingTests(TestCase):
    def test_class_phase_recognises_shs_stem_and_tvet(self):
        self.assertEqual(class_phase("SHS 2"), ("shs", 2))
        self.assertEqual(class_phase("STEM 1"), ("stem", 1))
        self.assertEqual(class_phase("TVET 3"), ("tvet", 3))
        self.assertEqual(class_phase("SHS 2 Science A"), ("shs", 2))

    def test_class_phase_does_not_confuse_stem_with_shs(self):
        phase, level = class_phase("STEM 1")
        self.assertEqual(phase, "stem")


class GenerateSchoolClassesTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Accra Technical Institute", slug="accra-technical",
            offers_primary=False, offers_shs=True, offers_stem=True, offers_tvet=True,
        )
        self.year = AcademicYear.objects.create(
            school=self.school, name="2026/2027",
            start_date=date(2026, 9, 1), end_date=date(2027, 7, 31), is_current=True,
        )

    def test_generates_shs_stem_and_tvet_classes(self):
        academic_year, created_count = generate_school_classes(school=self.school)

        self.assertEqual(academic_year, self.year)
        names = set(SchoolClass.objects.filter(school=self.school).values_list("name", flat=True))
        self.assertEqual(
            names,
            {"SHS 1", "SHS 2", "SHS 3", "STEM 1", "STEM 2", "STEM 3", "TVET 1", "TVET 2", "TVET 3"},
        )
        self.assertEqual(created_count, 9)

    def test_does_not_generate_levels_the_school_does_not_offer(self):
        self.school.offers_tvet = False
        self.school.save(update_fields=["offers_tvet"])

        generate_school_classes(school=self.school)

        self.assertFalse(SchoolClass.objects.filter(school=self.school, name__startswith="TVET").exists())


class SubjectsForClassTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Kumasi Senior High", slug="kumasi-senior-high",
            offers_primary=False, offers_shs=True, offers_stem=True, offers_tvet=True,
        )
        self.year = AcademicYear.objects.create(
            school=self.school, name="2026/2027",
            start_date=date(2026, 9, 1), end_date=date(2027, 7, 31), is_current=True,
        )

    def test_shs_class_gets_shs_core_subjects(self):
        school_class = SchoolClass.objects.create(school=self.school, academic_year=self.year, name="SHS 1")
        self.assertEqual(subjects_for_class(school_class), SHS_CORE_SUBJECTS)

    def test_stem_class_gets_stem_core_subjects_including_shs_core(self):
        school_class = SchoolClass.objects.create(school=self.school, academic_year=self.year, name="STEM 2")
        subjects = subjects_for_class(school_class)
        self.assertEqual(subjects, STEM_CORE_SUBJECTS)
        for subject in SHS_CORE_SUBJECTS:
            self.assertIn(subject, subjects)

    def test_tvet_class_gets_tvet_core_subjects(self):
        school_class = SchoolClass.objects.create(school=self.school, academic_year=self.year, name="TVET 3")
        self.assertEqual(subjects_for_class(school_class), TVET_CORE_SUBJECTS)

    def test_returns_nothing_when_school_does_not_offer_that_level(self):
        self.school.offers_stem = False
        self.school.save(update_fields=["offers_stem"])
        school_class = SchoolClass.objects.create(school=self.school, academic_year=self.year, name="STEM 1")

        self.assertEqual(subjects_for_class(school_class), ())


class GenerateGhanaCurriculumTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Tamale Girls SHS", slug="tamale-girls-shs",
            offers_primary=False, offers_shs=True,
        )
        self.year = AcademicYear.objects.create(
            school=self.school, name="2026/2027",
            start_date=date(2026, 9, 1), end_date=date(2027, 7, 31), is_current=True,
        )
        Term.objects.create(
            academic_year=self.year, name="Term 1", order=1,
            start_date=date(2026, 9, 1), end_date=date(2026, 12, 15),
        )

    def test_creates_shs_subjects_and_offerings(self):
        generate_school_classes(school=self.school)

        subjects_created, offerings_created, unmatched = generate_ghana_curriculum(school=self.school)

        self.assertEqual(subjects_created, len(SHS_CORE_SUBJECTS))
        self.assertEqual(offerings_created, len(SHS_CORE_SUBJECTS) * 3)  # 3 SHS classes, 1 term each
        self.assertEqual(unmatched, [])
