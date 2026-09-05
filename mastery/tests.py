from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.core.cache import cache
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import ProtectedError
from django.test import TestCase
from django.urls import reverse

from academics.models import AcademicYear, ClassEnrollment, SchoolClass, SubjectOffering, TeacherAssignment, Term
from accounts.models import User
from courses.models import Enrollment, Subject
from gradebook.history import record_grade_entry, review_grade_entry
from gradebook.models import Assessment, AssessmentCategory, GradeEntry, GradeReviewDecision, GradeScheme
from quizzes.models import Answer, BankQuestion, Question, Quiz, Submission
from schools.models import School, SchoolMembership

from tutor.models import TutorMode, TutorSession

from .models import Misconception, RemediationPlan, StudyGoal, Strand, Topic, TopicRevision
from .services import (
    add_topic_prerequisite,
    can_view_class,
    class_subject_mastery,
    class_topic_bands,
    class_topic_mastery,
    goal_revision_status,
    mastery_cache_key,
    misconception_patterns,
    remediation_plan_outcomes,
    school_remediation_plan_outcomes,
    student_subject_mastery,
    topic_mastery_for_student,
    unmet_prerequisites,
    update_topic,
)


class MasteryTestCase(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="Mastery School", slug="mastery-school")
        self.admin = self._member("mastery-admin", SchoolMembership.Role.SCHOOL_ADMIN)
        self.teacher = self._member("mastery-teacher", SchoolMembership.Role.TEACHER)
        self.unassigned = self._member("unassigned-mastery-teacher", SchoolMembership.Role.TEACHER)
        self.student = self._member("mastery-student", SchoolMembership.Role.STUDENT)
        self.year = AcademicYear.objects.create(
            school=self.school, name="2026/2027", start_date=date(2026, 9, 1),
            end_date=date(2027, 7, 31), is_current=True,
        )
        self.term = Term.objects.create(
            academic_year=self.year, name="Term 1", order=1,
            start_date=date(2026, 9, 7), end_date=date(2026, 9, 11),
        )
        self.school_class = SchoolClass.objects.create(
            school=self.school, academic_year=self.year, name="Basic 6", class_teacher=self.teacher
        )
        ClassEnrollment.objects.create(school_class=self.school_class, student=self.student)
        self.subject = Subject.objects.create(school=self.school, name="Mathematics")
        Enrollment.objects.create(student=self.student.user, subject=self.subject)
        self.offering = SubjectOffering.objects.create(
            school=self.school, school_class=self.school_class, subject=self.subject, term=self.term
        )
        TeacherAssignment.objects.create(offering=self.offering, teacher=self.teacher)

        self.number_strand = Strand.objects.create(school=self.school, subject=self.subject, name="Number", order=1)
        self.fractions = Topic.objects.create(strand=self.number_strand, name="Fractions", order=1)
        self.shape_strand = Strand.objects.create(school=self.school, subject=self.subject, name="Shape", order=2)
        self.angles = Topic.objects.create(strand=self.shape_strand, name="Angles", order=1)

        self.scheme = GradeScheme.objects.create(
            school=self.school, academic_year=self.year, name="Standard", status=GradeScheme.Status.ACTIVE
        )
        self.category = AssessmentCategory.objects.create(
            scheme=self.scheme, name="Coursework", code="coursework", weight=Decimal("100"), order=1
        )
        self.assessment_one = self._assessment("Fractions test one", self.fractions)
        self.assessment_two = self._assessment("Fractions test two", self.fractions)
        self.assessment_three = self._assessment("Angles test", self.angles)
        self._grade(self.assessment_one, "40")
        self._grade(self.assessment_two, "60")
        # assessment_three deliberately left ungraded: Angles has no evidence yet.

    def _member(self, username, role):
        user = User.objects.create_user(
            username=username, password="test-password",
            role=User.Role.TEACHER if role != "STUDENT" else User.Role.STUDENT,
        )
        return SchoolMembership.objects.create(school=self.school, user=user, role=role)

    def _assessment(self, title, topic):
        return Assessment.objects.create(
            school=self.school, offering=self.offering, category=self.category, topic=topic,
            title=title, max_score=Decimal("100"), status=Assessment.Status.CLOSED,
        )

    def _grade(self, assessment, score, student=None):
        return GradeEntry.objects.create(
            school=self.school, assessment=assessment, student=student or self.student,
            recorded_by=self.teacher, score=Decimal(score), status=GradeEntry.Status.PUBLISHED,
            review_status=GradeEntry.ReviewStatus.APPROVED, reviewed_by=self.admin,
        )

    def _login(self, membership):
        self.client.force_login(membership.user)
        session = self.client.session
        session["active_school_id"] = self.school.pk
        session.save()


class MasteryComputationTests(MasteryTestCase):
    def test_student_subject_mastery_computes_topic_percentages_and_buckets(self):
        result = student_subject_mastery(self.student, self.subject, self.term)
        self.assertEqual(result["strands"][0]["strand"], self.number_strand)
        fractions_row = result["strands"][0]["topics"][0]
        self.assertEqual(fractions_row["mastery_percentage"], Decimal("50.00"))
        self.assertEqual(fractions_row["status"], "DEVELOPING")
        self.assertEqual(fractions_row["evidence_count"], 2)

        angles_row = result["strands"][1]["topics"][0]
        self.assertIsNone(angles_row["mastery_percentage"])
        self.assertEqual(angles_row["status"], "NO_EVIDENCE")
        self.assertEqual(angles_row["evidence_count"], 0)

    def test_class_topic_mastery_aggregates_roster(self):
        result = class_topic_mastery(self.school_class, self.fractions, self.term)
        self.assertEqual(result["mastery_percentage"], Decimal("50.00"))
        self.assertEqual(result["evidence_count"], 2)
        self.assertEqual(result["student_count"], 1)

    def test_mastery_bucket_thresholds(self):
        self._grade(self.assessment_three, "90")
        mastered = student_subject_mastery(self.student, self.subject, self.term)["strands"][1]["topics"][0]
        self.assertEqual(mastered["mastery_percentage"], Decimal("90.00"))
        self.assertEqual(mastered["status"], "MASTERED")

    def test_can_view_class_allows_admin_and_assigned_teacher_only(self):
        self.assertTrue(can_view_class(self.admin, self.school_class, self.term))
        self.assertTrue(can_view_class(self.teacher, self.school_class, self.term))
        self.assertFalse(can_view_class(self.unassigned, self.school_class, self.term))

    def test_class_topic_bands_counts_students_per_band(self):
        needs_support_student = self._member("needs-support-student", SchoolMembership.Role.STUDENT)
        ClassEnrollment.objects.create(school_class=self.school_class, student=needs_support_student)
        self._grade(self.assessment_one, "10", student=needs_support_student)
        self._grade(self.assessment_two, "10", student=needs_support_student)

        rows = class_topic_bands(self.school_class, self.subject, self.term)

        fractions_row = next(row for row in rows if row["topic"] == self.fractions)
        self.assertEqual(fractions_row["counts"], {
            "MASTERED": 0, "DEVELOPING": 1, "NEEDS_SUPPORT": 1, "NO_EVIDENCE": 0,
        })
        angles_row = next(row for row in rows if row["topic"] == self.angles)
        self.assertEqual(angles_row["counts"], {
            "MASTERED": 0, "DEVELOPING": 0, "NEEDS_SUPPORT": 0, "NO_EVIDENCE": 2,
        })


class ClassSubjectMasteryCachingTests(MasteryTestCase):
    def setUp(self):
        super().setUp()
        cache.clear()

    def test_second_call_is_served_from_cache(self):
        first = class_subject_mastery(self.school_class, self.subject, self.term)

        with self.assertNumQueries(0):
            second = class_subject_mastery(self.school_class, self.subject, self.term)

        self.assertEqual(second, first)

    def _cache_key(self):
        return mastery_cache_key(self.school_class.id, self.subject.id, self.term.id)

    def test_publishing_a_grade_entry_busts_the_cache(self):
        class_subject_mastery(self.school_class, self.subject, self.term)  # populate the cache
        self.assertIsNotNone(cache.get(self._cache_key()))

        record_grade_entry(
            school=self.school, assessment=self.assessment_three, student=self.student,
            actor=self.teacher, score=Decimal("90"), source=GradeEntry.Source.MANUAL,
            status=GradeEntry.Status.PUBLISHED, reason="Marked",
        )

        self.assertIsNone(cache.get(self._cache_key()))

    def test_approving_a_grade_entry_busts_the_cache(self):
        entry, _ = record_grade_entry(
            school=self.school, assessment=self.assessment_three, student=self.student,
            actor=self.teacher, score=Decimal("90"), source=GradeEntry.Source.MANUAL,
            status=GradeEntry.Status.PUBLISHED, reason="Marked",
        )
        # Published but not yet approved: Angles has no APPROVED evidence yet.
        cached = class_subject_mastery(self.school_class, self.subject, self.term)
        self.assertEqual(cached["strands"][1]["topics"][0]["evidence_count"], 0)

        review_grade_entry(
            entry=entry, reviewer=self.admin, decision=GradeReviewDecision.Decision.APPROVED,
        )

        refreshed = class_subject_mastery(self.school_class, self.subject, self.term)
        self.assertEqual(refreshed["strands"][1]["topics"][0]["evidence_count"], 1)


class CurriculumViewTests(MasteryTestCase):
    def test_only_admin_can_create_strands_and_topics(self):
        self._login(self.teacher)
        response = self.client.get(reverse("mastery_curriculum"), secure=True)
        self.assertEqual(response.status_code, 403)

        self._login(self.admin)
        response = self.client.post(reverse("mastery_curriculum"), {
            "form": "strand", "subject": self.subject.pk, "name": "Algebra", "order": 3,
        }, secure=True)
        self.assertRedirects(response, reverse("mastery_curriculum"), fetch_redirect_response=False)
        algebra = Strand.objects.get(school=self.school, name="Algebra")

        response = self.client.post(reverse("mastery_curriculum"), {
            "form": "topic", "strand": algebra.pk, "name": "Linear equations", "order": 1,
        }, secure=True)
        self.assertRedirects(response, reverse("mastery_curriculum"), fetch_redirect_response=False)
        self.assertTrue(Topic.objects.filter(strand=algebra, name="Linear equations").exists())


class AssignTopicsViewTests(MasteryTestCase):
    def test_assigned_teacher_can_assign_topics(self):
        untagged = self._assessment("Untagged assessment", None)

        self._login(self.teacher)
        response = self.client.post(
            reverse("mastery_assign_topics", args=[self.offering.pk]),
            {f"topic_{untagged.pk}": self.angles.pk},
            secure=True,
        )
        self.assertRedirects(
            response, reverse("mastery_assign_topics", args=[self.offering.pk]), fetch_redirect_response=False
        )
        untagged.refresh_from_db()
        self.assertEqual(untagged.topic, self.angles)

    def test_unassigned_teacher_cannot_assign_topics(self):
        self._login(self.unassigned)
        response = self.client.get(
            reverse("mastery_assign_topics", args=[self.offering.pk]), secure=True
        )
        self.assertEqual(response.status_code, 403)

    def test_assigning_a_topic_from_another_school_is_ignored(self):
        untagged = self._assessment("Untagged assessment", None)
        other_school = School.objects.create(name="Other Mastery School", slug="other-mastery-school")
        other_subject = Subject.objects.create(school=other_school, name="Mathematics")
        other_strand = Strand.objects.create(school=other_school, subject=other_subject, name="Number")
        foreign_topic = Topic.objects.create(strand=other_strand, name="Foreign Fractions")

        self._login(self.teacher)
        self.client.post(
            reverse("mastery_assign_topics", args=[self.offering.pk]),
            {f"topic_{untagged.pk}": foreign_topic.pk},
            secure=True,
        )

        untagged.refresh_from_db()
        self.assertIsNone(untagged.topic)


class DashboardRenderTests(MasteryTestCase):
    def test_student_overview_renders_computed_mastery(self):
        self._login(self.student)
        response = self.client.get(reverse("mastery_overview"), {"term": self.term.pk}, secure=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Fractions")
        self.assertEqual(
            response.context["subject_rows"][0]["strands"][0]["topics"][0]["mastery_percentage"],
            Decimal("50.00"),
        )

    def test_teacher_overview_lists_classes_and_class_detail_renders(self):
        self._login(self.teacher)
        overview_response = self.client.get(reverse("mastery_overview"), {"term": self.term.pk}, secure=True)
        self.assertEqual(overview_response.status_code, 200)
        self.assertContains(overview_response, self.school_class.name)

        class_response = self.client.get(
            reverse("mastery_class", args=[self.school_class.pk, self.term.pk]), secure=True
        )
        self.assertEqual(class_response.status_code, 200)
        self.assertContains(class_response, "Fractions")

    def test_unassigned_teacher_cannot_view_class_detail(self):
        self._login(self.unassigned)
        response = self.client.get(
            reverse("mastery_class", args=[self.school_class.pk, self.term.pk]), secure=True
        )
        self.assertEqual(response.status_code, 403)

    def test_cross_school_class_is_not_visible(self):
        other = School.objects.create(name="Other Mastery", slug="other-mastery")
        user = User.objects.create_user(username="other-mastery-admin", password="test-password")
        SchoolMembership.objects.create(school=other, user=user, role=SchoolMembership.Role.SCHOOL_ADMIN)
        self.client.force_login(user)
        session = self.client.session
        session["active_school_id"] = other.pk
        session.save()
        response = self.client.get(
            reverse("mastery_class", args=[self.school_class.pk, self.term.pk]), secure=True
        )
        self.assertEqual(response.status_code, 404)


class QuestionLevelMasteryTests(MasteryTestCase):
    def setUp(self):
        super().setUp()
        self.quiz = Quiz.objects.create(subject=self.subject, teacher=self.teacher.user, title="Fractions Quiz")
        self.question_one = Question.objects.create(quiz=self.quiz, text="1/2 + 1/2 = ?", topic=self.fractions)
        self.question_two = Question.objects.create(quiz=self.quiz, text="1/4 + 1/4 = ?", topic=self.fractions)
        # Linking the quiz to a gradebook Assessment for this offering is what scopes its
        # answers to this term - see mastery/services.py::_question_percentages.
        Assessment.objects.create(
            school=self.school, offering=self.offering, category=self.category, legacy_quiz=self.quiz,
            title="Fractions Quiz (synced)", max_score=Decimal("100"), status=Assessment.Status.CLOSED,
        )
        self.submission = Submission.objects.create(quiz=self.quiz, student=self.student.user, score=50)
        Answer.objects.create(submission=self.submission, question=self.question_one, is_correct=True)
        Answer.objects.create(submission=self.submission, question=self.question_two, is_correct=False)

    def test_topic_mastery_blends_assessment_and_question_evidence(self):
        result = topic_mastery_for_student(self.student, self.fractions, self.term)
        # Assessment evidence: 40%, 60%. Question evidence: 100% (correct), 0% (incorrect).
        self.assertEqual(result["mastery_percentage"], Decimal("50.00"))
        self.assertEqual(result["assessment_evidence_count"], 2)
        self.assertEqual(result["question_evidence_count"], 2)
        self.assertEqual(result["evidence_count"], 4)

    def test_question_evidence_excluded_when_quiz_not_linked_to_term_assessment(self):
        unlinked_quiz = Quiz.objects.create(subject=self.subject, teacher=self.teacher.user, title="Unlinked quiz")
        question = Question.objects.create(quiz=unlinked_quiz, text="2+2=?", topic=self.fractions)
        submission = Submission.objects.create(quiz=unlinked_quiz, student=self.student.user, score=100)
        Answer.objects.create(submission=submission, question=question, is_correct=True)

        result = topic_mastery_for_student(self.student, self.fractions, self.term)
        self.assertEqual(result["evidence_count"], 4)
        self.assertEqual(result["question_evidence_count"], 2)

    def test_class_topic_mastery_includes_question_evidence_across_roster(self):
        result = class_topic_mastery(self.school_class, self.fractions, self.term)
        self.assertEqual(result["question_evidence_count"], 2)
        self.assertEqual(result["assessment_evidence_count"], 2)
        self.assertEqual(result["evidence_count"], 4)


class AssignQuestionTopicsViewTests(MasteryTestCase):
    def setUp(self):
        super().setUp()
        self.quiz = Quiz.objects.create(subject=self.subject, teacher=self.teacher.user, title="Fractions Quiz")
        self.question = Question.objects.create(quiz=self.quiz, text="1/2 + 1/2 = ?")

    def test_owning_teacher_can_assign_question_topics(self):
        self._login(self.teacher)
        response = self.client.post(
            reverse("mastery_assign_question_topics", args=[self.quiz.pk]),
            {f"topic_{self.question.pk}": self.fractions.pk},
            secure=True,
        )
        self.assertRedirects(
            response, reverse("mastery_assign_question_topics", args=[self.quiz.pk]), fetch_redirect_response=False
        )
        self.question.refresh_from_db()
        self.assertEqual(self.question.topic, self.fractions)

    def test_other_teacher_cannot_assign_question_topics(self):
        self._login(self.unassigned)
        response = self.client.get(
            reverse("mastery_assign_question_topics", args=[self.quiz.pk]), secure=True
        )
        self.assertEqual(response.status_code, 403)

    def test_admin_can_assign_question_topics(self):
        self._login(self.admin)
        response = self.client.post(
            reverse("mastery_assign_question_topics", args=[self.quiz.pk]),
            {f"topic_{self.question.pk}": self.angles.pk},
            secure=True,
        )
        self.assertRedirects(
            response, reverse("mastery_assign_question_topics", args=[self.quiz.pk]), fetch_redirect_response=False
        )
        self.question.refresh_from_db()
        self.assertEqual(self.question.topic, self.angles)

    def test_assigning_a_question_topic_from_another_school_is_ignored(self):
        other_school = School.objects.create(name="Other Question School", slug="other-question-school")
        other_subject = Subject.objects.create(school=other_school, name="Mathematics")
        other_strand = Strand.objects.create(school=other_school, subject=other_subject, name="Number")
        foreign_topic = Topic.objects.create(strand=other_strand, name="Foreign Fractions")

        self._login(self.teacher)
        self.client.post(
            reverse("mastery_assign_question_topics", args=[self.quiz.pk]),
            {f"topic_{self.question.pk}": foreign_topic.pk},
            secure=True,
        )

        self.question.refresh_from_db()
        self.assertIsNone(self.question.topic)


class MisconceptionsViewTests(MasteryTestCase):
    def setUp(self):
        super().setUp()
        self.misconception = Misconception.objects.create(
            school=self.school, student=self.student, topic=self.fractions,
            student_description="I added the denominators too.",
            hypothesis="The student may be adding denominators instead of keeping them constant.",
        )

    def test_teacher_can_list_open_misconceptions(self):
        self._login(self.teacher)
        response = self.client.get(
            reverse("mastery_misconceptions", args=[self.school_class.pk, self.term.pk]), secure=True
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "I added the denominators too.")

    def test_unassigned_teacher_cannot_view_misconceptions(self):
        self._login(self.unassigned)
        response = self.client.get(
            reverse("mastery_misconceptions", args=[self.school_class.pk, self.term.pk]), secure=True
        )
        self.assertEqual(response.status_code, 403)

    def test_teacher_can_dismiss_a_misconception(self):
        self._login(self.teacher)
        self.client.post(reverse("mastery_misconceptions", args=[self.school_class.pk, self.term.pk]), {
            "misconception_id": self.misconception.pk, "action": "dismiss",
        }, secure=True)

        self.misconception.refresh_from_db()
        self.assertEqual(self.misconception.status, Misconception.Status.DISMISSED)
        self.assertEqual(self.misconception.reviewed_by, self.teacher)
        self.assertIsNotNone(self.misconception.reviewed_at)

    def test_admin_can_resolve_a_misconception(self):
        self._login(self.admin)
        self.client.post(reverse("mastery_misconceptions", args=[self.school_class.pk, self.term.pk]), {
            "misconception_id": self.misconception.pk, "action": "resolve",
        }, secure=True)

        self.misconception.refresh_from_db()
        self.assertEqual(self.misconception.status, Misconception.Status.RESOLVED)

    def test_dismissed_misconception_no_longer_listed(self):
        self.misconception.status = Misconception.Status.DISMISSED
        self.misconception.save(update_fields=["status"])
        self._login(self.teacher)

        response = self.client.get(
            reverse("mastery_misconceptions", args=[self.school_class.pk, self.term.pk]), secure=True
        )

        self.assertNotContains(response, "I added the denominators too.")

    def test_cross_school_misconception_is_not_visible(self):
        other_school = School.objects.create(name="Other Mastery School", slug="other-mastery-misc")
        other_user = User.objects.create_user(username="other-mastery-misc-admin", password="test-password")
        SchoolMembership.objects.create(school=other_school, user=other_user, role=SchoolMembership.Role.SCHOOL_ADMIN)
        self.client.force_login(other_user)
        session = self.client.session
        session["active_school_id"] = other_school.pk
        session.save()

        response = self.client.get(
            reverse("mastery_misconceptions", args=[self.school_class.pk, self.term.pk]), secure=True
        )
        self.assertEqual(response.status_code, 404)


class MisconceptionPatternTests(MasteryTestCase):
    def _misconception(self, student, topic=None, status=Misconception.Status.OPEN):
        return Misconception.objects.create(
            school=self.school, student=student, topic=topic or self.fractions,
            student_description="I mixed up the steps.",
            hypothesis="The student may be confusing the procedure.",
            status=status,
        )

    def test_topic_shared_by_two_students_is_a_pattern(self):
        other_student = self._member("pattern-other-student", SchoolMembership.Role.STUDENT)
        ClassEnrollment.objects.create(school_class=self.school_class, student=other_student)
        self._misconception(self.student)
        self._misconception(other_student)

        patterns = misconception_patterns(self.school_class, self.term)

        self.assertEqual(len(patterns), 1)
        self.assertEqual(patterns[0]["topic"], self.fractions)
        self.assertEqual(patterns[0]["student_count"], 2)
        self.assertEqual(patterns[0]["misconception_count"], 2)

    def test_one_student_recurring_on_same_topic_is_a_pattern(self):
        self._misconception(self.student)
        self._misconception(self.student)

        patterns = misconception_patterns(self.school_class, self.term)

        self.assertEqual(len(patterns), 1)
        self.assertEqual(patterns[0]["student_count"], 1)
        self.assertEqual(patterns[0]["misconception_count"], 2)

    def test_single_isolated_misconception_is_not_a_pattern(self):
        self._misconception(self.student)

        patterns = misconception_patterns(self.school_class, self.term)

        self.assertEqual(patterns, [])

    def test_dismissed_misconception_does_not_count_toward_pattern(self):
        other_student = self._member("pattern-dismissed-student", SchoolMembership.Role.STUDENT)
        ClassEnrollment.objects.create(school_class=self.school_class, student=other_student)
        self._misconception(self.student)
        self._misconception(other_student, status=Misconception.Status.DISMISSED)

        patterns = misconception_patterns(self.school_class, self.term)

        self.assertEqual(patterns, [])

    def test_misconceptions_view_includes_patterns_in_context(self):
        other_student = self._member("pattern-view-student", SchoolMembership.Role.STUDENT)
        ClassEnrollment.objects.create(school_class=self.school_class, student=other_student)
        self._misconception(self.student)
        self._misconception(other_student)
        self._login(self.teacher)

        response = self.client.get(
            reverse("mastery_misconceptions", args=[self.school_class.pk, self.term.pk]), secure=True
        )

        self.assertEqual(len(response.context["patterns"]), 1)
        self.assertContains(response, "Recurring Patterns")
        self.assertContains(response, "Fractions")


class DifferentiatedTasksViewTests(MasteryTestCase):
    def setUp(self):
        super().setUp()
        self.mastered_student = self._member("mastered-student", SchoolMembership.Role.STUDENT)
        self.needs_support_student = self._member("needs-support-student", SchoolMembership.Role.STUDENT)
        ClassEnrollment.objects.create(school_class=self.school_class, student=self.mastered_student)
        ClassEnrollment.objects.create(school_class=self.school_class, student=self.needs_support_student)
        self._grade(self.assessment_one, "90", student=self.mastered_student)
        self._grade(self.assessment_two, "90", student=self.mastered_student)
        self._grade(self.assessment_one, "20", student=self.needs_support_student)
        self._grade(self.assessment_two, "20", student=self.needs_support_student)

    def _url(self, topic=None):
        return reverse(
            "mastery_differentiate", args=[self.school_class.pk, self.term.pk, (topic or self.fractions).pk]
        )

    def test_get_buckets_students_by_mastery_band(self):
        self._login(self.teacher)

        response = self.client.get(self._url(), secure=True)

        self.assertEqual(response.status_code, 200)
        bands = response.context["bands"]
        self.assertEqual([entry["student"] for entry in bands["MASTERED"]], [self.mastered_student])
        self.assertEqual([entry["student"] for entry in bands["DEVELOPING"]], [self.student])
        self.assertEqual([entry["student"] for entry in bands["NEEDS_SUPPORT"]], [self.needs_support_student])

    def test_unassigned_teacher_cannot_view(self):
        self._login(self.unassigned)

        response = self.client.get(self._url(), secure=True)

        self.assertEqual(response.status_code, 403)

    def test_student_cannot_view(self):
        self._login(self.student)

        response = self.client.get(self._url(), secure=True)

        self.assertRedirects(response, reverse("home"), fetch_redirect_response=False)

    @patch("quizzes.ai_quiz_generator.generate_quiz_questions")
    def test_generating_for_needs_support_band_creates_easy_bank_questions(self, mock_generate):
        mock_generate.return_value = [{"text": "1/4 + 1/4 = ?", "choices": [
            {"text": "1/2", "is_correct": True}, {"text": "1", "is_correct": False},
        ]}]
        self._login(self.teacher)

        self.client.post(self._url(), {
            "action": "NEEDS_SUPPORT", "topic_description": "Fractions basics", "num_questions": 2,
        }, secure=True)

        bank_question = BankQuestion.objects.get(subject=self.subject, topic=self.fractions)
        self.assertEqual(bank_question.difficulty, BankQuestion.Difficulty.EASY)
        self.assertEqual(bank_question.status, BankQuestion.Status.PENDING_REVIEW)
        self.assertEqual(bank_question.choices.count(), 2)

    @patch("quizzes.ai_quiz_generator.generate_quiz_questions")
    def test_generating_for_mastered_band_creates_hard_bank_questions(self, mock_generate):
        mock_generate.return_value = [{"text": "Extension question", "choices": [
            {"text": "A", "is_correct": True}, {"text": "B", "is_correct": False},
        ]}]
        self._login(self.teacher)

        self.client.post(self._url(), {
            "action": "MASTERED", "topic_description": "Fractions extension", "num_questions": 1,
        }, secure=True)

        bank_question = BankQuestion.objects.get(subject=self.subject, topic=self.fractions)
        self.assertEqual(bank_question.difficulty, BankQuestion.Difficulty.HARD)

    @patch("quizzes.ai_quiz_generator.generate_quiz_questions")
    def test_generating_for_a_band_with_no_students_is_a_noop(self, mock_generate):
        mock_generate.return_value = [{"text": "x", "choices": []}]
        self._login(self.teacher)

        # Angles has no evidence at all in this fixture, so every band is empty for it.
        self.client.post(self._url(topic=self.angles), {
            "action": "MASTERED", "topic_description": "Angles", "num_questions": 1,
        }, secure=True)

        self.assertFalse(BankQuestion.objects.exists())
        mock_generate.assert_not_called()


class RemediationPlanTests(DifferentiatedTasksViewTests):
    def test_teacher_can_create_a_plan_for_a_needs_support_student(self):
        self._login(self.teacher)

        response = self.client.post(self._url(), {
            "action": "create_plan", "student_id": self.needs_support_student.pk,
            "plan_text": "Daily 10-minute fraction drills.",
        }, secure=True)

        self.assertRedirects(response, self._url(), fetch_redirect_response=False)
        plan = RemediationPlan.objects.get(student=self.needs_support_student, topic=self.fractions)
        self.assertEqual(plan.status, RemediationPlan.Status.ACTIVE)
        self.assertEqual(plan.mastery_percentage_at_start, Decimal("20.00"))
        self.assertEqual(plan.created_by, self.teacher)

    def test_creating_a_plan_for_a_non_roster_student_is_rejected(self):
        outsider = self._member("outsider-student", SchoolMembership.Role.STUDENT)
        self._login(self.teacher)

        response = self.client.post(self._url(), {
            "action": "create_plan", "student_id": outsider.pk, "plan_text": "Some plan.",
        }, secure=True)

        self.assertEqual(response.status_code, 404)
        self.assertFalse(RemediationPlan.objects.exists())

    def test_completing_a_plan_captures_outcome_and_current_mastery(self):
        self._login(self.teacher)
        self.client.post(self._url(), {
            "action": "create_plan", "student_id": self.needs_support_student.pk,
            "plan_text": "Daily 10-minute fraction drills.",
        }, secure=True)
        plan = RemediationPlan.objects.get(student=self.needs_support_student, topic=self.fractions)
        GradeEntry.objects.filter(
            assessment__in=[self.assessment_one, self.assessment_two], student=self.needs_support_student,
        ).update(score=Decimal("80"))

        self.client.post(self._url(), {
            "action": "complete_plan", "plan_id": plan.pk, "outcome": "Student improved significantly.",
        }, secure=True)

        plan.refresh_from_db()
        self.assertEqual(plan.status, RemediationPlan.Status.COMPLETED)
        self.assertEqual(plan.outcome, "Student improved significantly.")
        self.assertEqual(plan.mastery_percentage_at_completion, Decimal("80.00"))
        self.assertIsNotNone(plan.completed_at)

    def test_cancelling_a_plan_sets_status_without_mastery_capture(self):
        self._login(self.teacher)
        self.client.post(self._url(), {
            "action": "create_plan", "student_id": self.needs_support_student.pk,
            "plan_text": "Daily 10-minute fraction drills.",
        }, secure=True)
        plan = RemediationPlan.objects.get(student=self.needs_support_student, topic=self.fractions)

        self.client.post(self._url(), {"action": "cancel_plan", "plan_id": plan.pk}, secure=True)

        plan.refresh_from_db()
        self.assertEqual(plan.status, RemediationPlan.Status.CANCELLED)
        self.assertIsNone(plan.mastery_percentage_at_completion)

    def test_unassigned_teacher_cannot_create_a_plan(self):
        self._login(self.unassigned)

        response = self.client.post(self._url(), {
            "action": "create_plan", "student_id": self.needs_support_student.pk, "plan_text": "Some plan.",
        }, secure=True)

        self.assertEqual(response.status_code, 403)
        self.assertFalse(RemediationPlan.objects.exists())


class StudyGoalTests(MasteryTestCase):
    def _url(self):
        return reverse("mastery_study_goals")

    def test_student_can_create_a_goal_for_an_enrolled_topic(self):
        self._login(self.student)

        response = self.client.post(self._url(), {
            "action": "create", "topic_id": self.fractions.pk, "note": "Ace the next test.",
        }, secure=True)

        self.assertRedirects(response, self._url(), fetch_redirect_response=False)
        goal = StudyGoal.objects.get(student=self.student, topic=self.fractions)
        self.assertEqual(goal.status, StudyGoal.Status.ACTIVE)
        self.assertEqual(goal.note, "Ace the next test.")

    def test_creating_a_duplicate_active_goal_is_a_noop(self):
        self._login(self.student)
        self.client.post(self._url(), {"action": "create", "topic_id": self.fractions.pk}, secure=True)

        self.client.post(self._url(), {"action": "create", "topic_id": self.fractions.pk}, secure=True)

        self.assertEqual(StudyGoal.objects.filter(student=self.student, topic=self.fractions).count(), 1)

    def test_goal_for_topic_outside_enrolled_subjects_is_rejected(self):
        other_subject = Subject.objects.create(school=self.school, name="Science")
        other_strand = Strand.objects.create(school=self.school, subject=other_subject, name="Biology", order=1)
        other_topic = Topic.objects.create(strand=other_strand, name="Cells", order=1)
        self._login(self.student)

        response = self.client.post(
            self._url(), {"action": "create", "topic_id": other_topic.pk}, secure=True
        )

        self.assertEqual(response.status_code, 404)
        self.assertFalse(StudyGoal.objects.filter(topic=other_topic).exists())

    def test_goal_revision_status_reports_due_when_never_studied(self):
        goal = StudyGoal.objects.create(school=self.school, student=self.student, topic=self.fractions)

        status = goal_revision_status(goal, self.term)

        self.assertTrue(status["due"])
        self.assertIsNone(status["last_studied_at"])
        self.assertEqual(status["mastery"]["status"], "DEVELOPING")

    def test_recent_tutor_session_clears_due_status(self):
        goal = StudyGoal.objects.create(school=self.school, student=self.student, topic=self.fractions)
        TutorSession.objects.create(
            school=self.school, student=self.student.user, mode=TutorMode.REVISE_WITH_ME,
            subject=self.subject, topic=self.fractions,
        )

        status = goal_revision_status(goal, self.term)

        self.assertFalse(status["due"])
        self.assertIsNotNone(status["last_studied_at"])

    def test_marking_a_goal_achieved_sets_status_and_timestamp(self):
        goal = StudyGoal.objects.create(school=self.school, student=self.student, topic=self.fractions)
        self._login(self.student)

        self.client.post(self._url(), {"action": "achieve", "goal_id": goal.pk}, secure=True)

        goal.refresh_from_db()
        self.assertEqual(goal.status, StudyGoal.Status.ACHIEVED)
        self.assertIsNotNone(goal.achieved_at)

    def test_abandoning_a_goal_sets_status(self):
        goal = StudyGoal.objects.create(school=self.school, student=self.student, topic=self.fractions)
        self._login(self.student)

        self.client.post(self._url(), {"action": "abandon", "goal_id": goal.pk}, secure=True)

        goal.refresh_from_db()
        self.assertEqual(goal.status, StudyGoal.Status.ABANDONED)
        self.assertIsNone(goal.achieved_at)


class RemediationPlanOutcomeTests(MasteryTestCase):
    def _plan(self, status, start=None, completion=None, student=None):
        return RemediationPlan.objects.create(
            school=self.school, student=student or self.student, topic=self.fractions, term=self.term,
            plan="Some plan.", status=status,
            mastery_percentage_at_start=start, mastery_percentage_at_completion=completion,
            created_by=self.teacher,
        )

    def test_remediation_plan_outcomes_counts_and_rate(self):
        self._plan(RemediationPlan.Status.COMPLETED, start=Decimal("20"), completion=Decimal("80"))
        self._plan(RemediationPlan.Status.COMPLETED, start=Decimal("60"), completion=Decimal("50"))
        self._plan(RemediationPlan.Status.COMPLETED, start=Decimal("30"), completion=None)
        self._plan(RemediationPlan.Status.CANCELLED)
        self._plan(RemediationPlan.Status.ACTIVE)

        outcomes = remediation_plan_outcomes(self.school_class, self.term)

        self.assertEqual(outcomes["plan_count"], 5)
        self.assertEqual(outcomes["completed_count"], 3)
        self.assertEqual(outcomes["comparable_count"], 2)
        self.assertEqual(outcomes["improved_count"], 1)
        self.assertEqual(outcomes["improvement_rate"], Decimal("50.00"))

    def test_no_comparable_plans_returns_none_rate(self):
        outcomes = remediation_plan_outcomes(self.school_class, self.term)

        self.assertEqual(outcomes["plan_count"], 0)
        self.assertIsNone(outcomes["improvement_rate"])

    def test_school_remediation_plan_outcomes_sums_across_classes(self):
        other_class = SchoolClass.objects.create(
            school=self.school, academic_year=self.year, name="Basic 7", class_teacher=self.teacher
        )
        other_student = self._member("outcome-other-student", SchoolMembership.Role.STUDENT)
        ClassEnrollment.objects.create(school_class=other_class, student=other_student)
        self._plan(RemediationPlan.Status.COMPLETED, start=Decimal("20"), completion=Decimal("80"))
        self._plan(
            RemediationPlan.Status.COMPLETED, start=Decimal("40"), completion=Decimal("80"),
            student=other_student,
        )

        outcomes = school_remediation_plan_outcomes(self.school, self.term)

        self.assertEqual(outcomes["comparable_count"], 2)
        self.assertEqual(outcomes["improved_count"], 2)
        self.assertEqual(outcomes["improvement_rate"], Decimal("100.00"))
        self.assertEqual(len(outcomes["classes"]), 2)

    def test_admin_sees_school_wide_report(self):
        self._login(self.admin)

        response = self.client.get(reverse("mastery_improvement_report"), secure=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("classes", response.context["outcomes"])

    def test_teacher_sees_only_their_own_classes(self):
        other_class = SchoolClass.objects.create(
            school=self.school, academic_year=self.year, name="Basic 8"
        )
        self._login(self.teacher)

        response = self.client.get(reverse("mastery_improvement_report"), secure=True)

        class_names = [row["school_class"].name for row in response.context["outcomes"]["classes"]]
        self.assertIn(self.school_class.name, class_names)
        self.assertNotIn(other_class.name, class_names)

    def test_student_cannot_view_report(self):
        self._login(self.student)

        response = self.client.get(reverse("mastery_improvement_report"), secure=True)

        self.assertRedirects(response, reverse("home"), fetch_redirect_response=False)


class PrerequisiteTests(MasteryTestCase):
    def setUp(self):
        super().setUp()
        self.whole_numbers = Topic.objects.create(strand=self.number_strand, name="Whole Numbers", order=2)

    def test_adding_a_prerequisite_creates_the_relationship(self):
        add_topic_prerequisite(self.fractions, self.whole_numbers)

        self.assertIn(self.whole_numbers, self.fractions.prerequisites.all())

    def test_topic_cannot_be_its_own_prerequisite(self):
        with self.assertRaises(ValidationError):
            add_topic_prerequisite(self.fractions, self.fractions)

    def test_indirect_cycle_is_rejected(self):
        counting = Topic.objects.create(strand=self.number_strand, name="Counting", order=3)
        add_topic_prerequisite(self.fractions, self.whole_numbers)
        add_topic_prerequisite(self.whole_numbers, counting)

        with self.assertRaises(ValidationError):
            add_topic_prerequisite(counting, self.fractions)

    def test_unmet_prerequisites_excludes_mastered_topics(self):
        add_topic_prerequisite(self.fractions, self.whole_numbers)

        unmet = unmet_prerequisites(self.student, self.fractions, self.term)
        self.assertEqual(len(unmet), 1)
        self.assertEqual(unmet[0]["topic"], self.whole_numbers)
        self.assertEqual(unmet[0]["result"]["status"], "NO_EVIDENCE")

        wn_assessment = self._assessment("Whole numbers test", self.whole_numbers)
        self._grade(wn_assessment, "90")

        unmet = unmet_prerequisites(self.student, self.fractions, self.term)
        self.assertEqual(unmet, [])

    def test_differentiated_tasks_view_shows_unmet_prerequisites(self):
        needs_support_student = self._member("prereq-needs-support", SchoolMembership.Role.STUDENT)
        ClassEnrollment.objects.create(school_class=self.school_class, student=needs_support_student)
        self._grade(self.assessment_one, "20", student=needs_support_student)
        self._grade(self.assessment_two, "20", student=needs_support_student)
        add_topic_prerequisite(self.fractions, self.whole_numbers)
        self._login(self.teacher)

        response = self.client.get(
            reverse("mastery_differentiate", args=[self.school_class.pk, self.term.pk, self.fractions.pk]),
            secure=True,
        )

        bands = response.context["bands"]
        needs_support_entry = next(e for e in bands["NEEDS_SUPPORT"] if e["student"] == needs_support_student)
        self.assertEqual(len(needs_support_entry["unmet_prerequisites"]), 1)
        self.assertEqual(needs_support_entry["unmet_prerequisites"][0]["topic"], self.whole_numbers)

    def test_curriculum_view_add_and_remove_prerequisite(self):
        self._login(self.admin)

        self.client.post(reverse("mastery_curriculum"), {
            "action": "add_prerequisite", "topic_id": self.fractions.pk, "prerequisite_id": self.whole_numbers.pk,
        }, secure=True)
        self.assertIn(self.whole_numbers, self.fractions.prerequisites.all())

        self.client.post(reverse("mastery_curriculum"), {
            "action": "remove_prerequisite", "topic_id": self.fractions.pk, "prerequisite_id": self.whole_numbers.pk,
        }, secure=True)
        self.assertNotIn(self.whole_numbers, self.fractions.prerequisites.all())

    def test_non_admin_cannot_add_prerequisite(self):
        self._login(self.teacher)

        response = self.client.post(reverse("mastery_curriculum"), {
            "action": "add_prerequisite", "topic_id": self.fractions.pk, "prerequisite_id": self.whole_numbers.pk,
        }, secure=True)

        self.assertEqual(response.status_code, 403)
        self.assertNotIn(self.whole_numbers, self.fractions.prerequisites.all())


class TopicVersioningTests(MasteryTestCase):
    def test_deleting_a_topic_leaves_remediation_plans_and_goals_intact(self):
        plan = RemediationPlan.objects.create(
            school=self.school, student=self.student, topic=self.angles, term=self.term,
            plan="Practice angle types.", created_by=self.teacher,
        )
        goal = StudyGoal.objects.create(school=self.school, student=self.student, topic=self.angles)

        self.angles.delete()

        plan.refresh_from_db()
        goal.refresh_from_db()
        self.assertIsNone(plan.topic)
        self.assertIsNone(goal.topic)

    def test_update_topic_requires_a_reason(self):
        with self.assertRaises(ValidationError):
            update_topic(topic=self.fractions, actor=self.admin, name="Fractions II", reason="")

    def test_noop_edit_is_rejected(self):
        with self.assertRaises(ValidationError):
            update_topic(topic=self.fractions, actor=self.admin, name=self.fractions.name, reason="No real change")

    def test_update_topic_creates_a_revision(self):
        update_topic(topic=self.fractions, actor=self.admin, name="Fractions Advanced", reason="Curriculum refresh")

        self.fractions.refresh_from_db()
        self.assertEqual(self.fractions.name, "Fractions Advanced")
        revision = TopicRevision.objects.get(topic=self.fractions)
        self.assertEqual(revision.previous_name, "Fractions")
        self.assertEqual(revision.new_name, "Fractions Advanced")
        self.assertEqual(revision.reason, "Curriculum refresh")
        self.assertEqual(revision.changed_by, self.admin)

    def test_topic_revision_is_immutable(self):
        update_topic(topic=self.fractions, actor=self.admin, name="Fractions Advanced", reason="Curriculum refresh")
        revision = TopicRevision.objects.get(topic=self.fractions)

        with self.assertRaises(ValidationError):
            revision.reason = "Changed my mind"
            revision.save()
        with self.assertRaises(ValidationError):
            revision.delete()

    def test_topic_with_revision_history_cannot_be_deleted(self):
        update_topic(topic=self.fractions, actor=self.admin, name="Fractions Advanced", reason="Curriculum refresh")

        with self.assertRaises(ProtectedError):
            self.fractions.delete()

    def test_curriculum_view_edit_topic_action(self):
        self._login(self.admin)

        response = self.client.post(reverse("mastery_curriculum"), {
            "action": "edit_topic", "topic_id": self.fractions.pk, "name": "Fractions Advanced",
            "strand_id": self.number_strand.pk, "reason": "Curriculum refresh",
        }, secure=True)

        self.assertRedirects(response, reverse("mastery_curriculum"), fetch_redirect_response=False)
        self.fractions.refresh_from_db()
        self.assertEqual(self.fractions.name, "Fractions Advanced")
        self.assertTrue(TopicRevision.objects.filter(topic=self.fractions).exists())

    def test_non_admin_cannot_edit_topic(self):
        self._login(self.teacher)

        response = self.client.post(reverse("mastery_curriculum"), {
            "action": "edit_topic", "topic_id": self.fractions.pk, "name": "Fractions Advanced",
            "strand_id": self.number_strand.pk, "reason": "Curriculum refresh",
        }, secure=True)

        self.assertEqual(response.status_code, 403)
        self.fractions.refresh_from_db()
        self.assertEqual(self.fractions.name, "Fractions")
