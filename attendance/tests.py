from datetime import date
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.urls import reverse

from academics.models import AcademicYear, ClassEnrollment, SchoolClass, SubjectOffering, TeacherAssignment, Term
from accounts.models import User
from courses.models import Subject
from communications.models import Notification
from schools.models import School, SchoolMembership

from .models import AttendanceRecord, AttendanceRevision, AttendanceSession, SchoolCalendarPolicy, SchoolClosure
from .services import correct_attendance, instructional_dates, student_attendance_summary, submit_attendance


class AttendanceWorkflowTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="Attendance School", slug="attendance-school")
        self.year = AcademicYear.objects.create(
            school=self.school,
            name="2026/2027",
            start_date=date(2026, 9, 1),
            end_date=date(2027, 7, 31),
            is_current=True,
        )
        self.term = Term.objects.create(
            academic_year=self.year,
            name="Term 1",
            order=1,
            start_date=date(2026, 9, 7),
            end_date=date(2026, 9, 13),
        )
        self.school_class = SchoolClass.objects.create(
            school=self.school, academic_year=self.year, name="Basic 5"
        )
        self.subject = Subject.objects.create(school=self.school, name="Mathematics")
        self.offering = SubjectOffering.objects.create(
            school=self.school,
            school_class=self.school_class,
            subject=self.subject,
            term=self.term,
        )
        self.teacher_user = User.objects.create_user(
            username="attendance-teacher", password="test-password", role=User.Role.TEACHER
        )
        self.teacher = SchoolMembership.objects.create(
            school=self.school, user=self.teacher_user, role=SchoolMembership.Role.TEACHER
        )
        TeacherAssignment.objects.create(offering=self.offering, teacher=self.teacher)
        self.other_teacher_user = User.objects.create_user(
            username="unassigned-attendance-teacher", password="test-password", role=User.Role.TEACHER
        )
        self.other_teacher = SchoolMembership.objects.create(
            school=self.school, user=self.other_teacher_user, role=SchoolMembership.Role.TEACHER
        )
        self.students = []
        for number in (1, 2):
            user = User.objects.create_user(username=f"attendance-student-{number}", password="test-password")
            membership = SchoolMembership.objects.create(
                school=self.school, user=user, role=SchoolMembership.Role.STUDENT
            )
            ClassEnrollment.objects.create(school_class=self.school_class, student=membership)
            self.students.append(membership)
        self.admin_user = User.objects.create_user(username="attendance-admin", password="test-password")
        self.administrator = SchoolMembership.objects.create(
            school=self.school, user=self.admin_user, role=SchoolMembership.Role.SCHOOL_ADMIN
        )

    def _statuses(self, first=AttendanceRecord.Status.PRESENT, second=AttendanceRecord.Status.PRESENT):
        return {self.students[0].pk: first, self.students[1].pk: second}

    def test_instructional_dates_exclude_weekends_and_closures(self):
        SchoolClosure.objects.create(
            school=self.school,
            term=self.term,
            name="Midweek closure",
            closure_type=SchoolClosure.ClosureType.CLOSURE,
            start_date=date(2026, 9, 9),
            end_date=date(2026, 9, 10),
            created_by=self.administrator,
        )
        self.assertEqual(
            instructional_dates(self.term),
            [date(2026, 9, 7), date(2026, 9, 8), date(2026, 9, 11)],
        )

    def test_school_weekday_policy_changes_derived_days(self):
        policy = SchoolCalendarPolicy.objects.create(
            school=self.school, instructional_weekdays="0,1,2,3,4,5"
        )
        policy.full_clean()
        self.assertIn(date(2026, 9, 12), instructional_dates(self.term))

    def test_teacher_submits_complete_register_once(self):
        session = submit_attendance(
            school_class=self.school_class,
            term=self.term,
            attendance_date=date(2026, 9, 7),
            actor=self.teacher,
            statuses=self._statuses(second=AttendanceRecord.Status.ABSENT),
        )
        self.assertEqual(session.status, AttendanceSession.Status.SUBMITTED)
        self.assertEqual(session.records.count(), 2)
        with self.assertRaisesMessage(ValidationError, "already submitted"):
            submit_attendance(
                school_class=self.school_class,
                term=self.term,
                attendance_date=date(2026, 9, 7),
                actor=self.teacher,
                statuses=self._statuses(),
            )

    def test_register_saves_reasons_only_for_non_present_students(self):
        session = submit_attendance(
            school_class=self.school_class,
            term=self.term,
            attendance_date=date(2026, 9, 7),
            actor=self.teacher,
            statuses=self._statuses(second=AttendanceRecord.Status.EXCUSED),
            reasons={
                self.students[0].pk: "Should be cleared",
                self.students[1].pk: "Medical appointment",
            },
        )

        self.assertEqual(session.records.get(student=self.students[0]).reason, "")
        self.assertEqual(
            session.records.get(student=self.students[1]).reason,
            "Medical appointment",
        )

    def test_absence_creates_an_admin_attendance_alert(self):
        session = submit_attendance(
            school_class=self.school_class,
            term=self.term,
            attendance_date=date(2026, 9, 7),
            actor=self.teacher,
            statuses=self._statuses(second=AttendanceRecord.Status.ABSENT),
            reasons={self.students[1].pk: "Reported sick"},
        )

        alert = Notification.objects.get(
            recipient=self.administrator,
            kind=Notification.Kind.ATTENDANCE,
        )
        self.assertIn("Reported sick", alert.message)
        self.assertIn(self.school_class.name, alert.message)
        self.assertEqual(
            alert.deduplication_key,
            f"attendance:{session.pk}:student:{self.students[1].pk}",
        )
        self.assertIn("date=2026-09-07", alert.target_url)

    def test_present_students_do_not_create_admin_attendance_alerts(self):
        submit_attendance(
            school_class=self.school_class,
            term=self.term,
            attendance_date=date(2026, 9, 7),
            actor=self.teacher,
            statuses=self._statuses(),
        )
        self.assertFalse(Notification.objects.filter(kind=Notification.Kind.ATTENDANCE).exists())

    def test_correction_to_absent_creates_admin_attendance_alert(self):
        session = submit_attendance(
            school_class=self.school_class,
            term=self.term,
            attendance_date=date(2026, 9, 7),
            actor=self.teacher,
            statuses=self._statuses(),
        )
        record = session.records.get(student=self.students[0])

        corrected = correct_attendance(
            record=record,
            actor=self.teacher,
            new_status=AttendanceRecord.Status.ABSENT,
            reason="Parent reported illness",
        )

        alert = Notification.objects.get(
            recipient=self.administrator,
            kind=Notification.Kind.ATTENDANCE,
        )
        self.assertIn("Parent reported illness", alert.message)
        self.assertTrue(alert.deduplication_key.startswith("attendance-correction:"))
        self.assertEqual(corrected.reason, "Parent reported illness")

    def test_partial_register_is_rejected_without_writes(self):
        with self.assertRaisesMessage(ValidationError, "every active student"):
            submit_attendance(
                school_class=self.school_class,
                term=self.term,
                attendance_date=date(2026, 9, 7),
                actor=self.teacher,
                statuses={self.students[0].pk: AttendanceRecord.Status.PRESENT},
            )
        self.assertFalse(AttendanceSession.objects.exists())

    def test_weekend_attendance_is_rejected(self):
        with self.assertRaisesMessage(ValidationError, "instructional day"):
            submit_attendance(
                school_class=self.school_class,
                term=self.term,
                attendance_date=date(2026, 9, 12),
                actor=self.teacher,
                statuses=self._statuses(),
            )

    def test_unassigned_teacher_cannot_submit(self):
        with self.assertRaises(PermissionDenied):
            submit_attendance(
                school_class=self.school_class,
                term=self.term,
                attendance_date=date(2026, 9, 7),
                actor=self.other_teacher,
                statuses=self._statuses(),
            )

    def test_correction_requires_reason_and_creates_immutable_revision(self):
        session = submit_attendance(
            school_class=self.school_class,
            term=self.term,
            attendance_date=date(2026, 9, 7),
            actor=self.teacher,
            statuses=self._statuses(second=AttendanceRecord.Status.ABSENT),
        )
        record = session.records.get(student=self.students[1])
        with self.assertRaisesMessage(ValidationError, "reason is required"):
            correct_attendance(
                record=record,
                actor=self.teacher,
                new_status=AttendanceRecord.Status.EXCUSED,
                reason="",
            )
        corrected = correct_attendance(
            record=record,
            actor=self.teacher,
            new_status=AttendanceRecord.Status.EXCUSED,
            reason="Medical appointment documented",
        )
        revision = corrected.revisions.get()
        self.assertEqual(revision.previous_status, AttendanceRecord.Status.ABSENT)
        self.assertEqual(revision.new_status, AttendanceRecord.Status.EXCUSED)
        revision.reason = "Changed"
        with self.assertRaisesMessage(ValidationError, "immutable"):
            revision.save()

    def test_summary_uses_derived_days_open(self):
        submit_attendance(
            school_class=self.school_class,
            term=self.term,
            attendance_date=date(2026, 9, 7),
            actor=self.teacher,
            statuses=self._statuses(first=AttendanceRecord.Status.PRESENT),
        )
        summary = student_attendance_summary(student=self.students[0], term=self.term)
        self.assertEqual(summary["days_open"], 5)
        self.assertEqual(summary["present"], 1)
        self.assertEqual(summary["percentage"], Decimal("20.00"))

    def test_summary_ignores_legacy_weekend_registers(self):
        valid_session = submit_attendance(
            school_class=self.school_class,
            term=self.term,
            attendance_date=date(2026, 9, 7),
            actor=self.teacher,
            statuses=self._statuses(),
        )
        legacy_session = AttendanceSession.objects.create(
            school=self.school,
            school_class=self.school_class,
            term=self.term,
            attendance_date=date(2026, 9, 12),
            status=AttendanceSession.Status.SUBMITTED,
            submitted_by=self.teacher,
        )
        AttendanceRecord.objects.create(
            session=legacy_session,
            student=self.students[0],
            status=AttendanceRecord.Status.PRESENT,
            marked_by=self.teacher,
        )

        summary = student_attendance_summary(student=self.students[0], term=self.term)

        self.assertEqual(valid_session.records.filter(student=self.students[0]).count(), 1)
        self.assertEqual(summary["present"], 1)
        self.assertEqual(summary["days_open"], 5)
        self.assertEqual(summary["percentage"], Decimal("20.00"))

    def test_teacher_register_view_is_assignment_scoped(self):
        self.client.force_login(self.other_teacher_user)
        response = self.client.get(
            reverse("attendance_register", args=[self.school_class.pk, self.term.pk]),
            secure=True,
        )
        self.assertEqual(response.status_code, 404)

    def test_register_shows_bulk_present_control_and_reason_fields(self):
        self.client.force_login(self.teacher_user)
        response = self.client.get(
            reverse("attendance_register", args=[self.school_class.pk, self.term.pk]),
            {"date": "2026-09-07"},
            secure=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Mark all present")
        self.assertContains(response, f'name="reason_{self.students[0].pk}"')

    def test_assigned_teacher_can_download_class_attendance_csv(self):
        submit_attendance(
            school_class=self.school_class,
            term=self.term,
            attendance_date=date(2026, 9, 7),
            actor=self.teacher,
            statuses=self._statuses(second=AttendanceRecord.Status.ABSENT),
        )
        self.client.force_login(self.teacher_user)

        response = self.client.get(
            reverse("attendance_summary_csv", args=[self.school_class.pk, self.term.pk]),
            secure=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv")
        self.assertIn("attachment;", response["Content-Disposition"])
        content = response.content.decode()
        self.assertIn("Student ID,Student,Present,Absent,Excused,Days open,Attendance %", content)
        self.assertIn("attendance-student-1", content)

    def test_unassigned_teacher_cannot_download_attendance_csv(self):
        self.client.force_login(self.other_teacher_user)
        response = self.client.get(
            reverse("attendance_summary_csv", args=[self.school_class.pk, self.term.pk]),
            secure=True,
        )
        self.assertEqual(response.status_code, 404)

    def test_admin_can_add_tenant_scoped_closure(self):
        self.client.force_login(self.admin_user)
        response = self.client.post(
            reverse("attendance_add_closure"),
            {
                "term": self.term.pk,
                "name": "Founders Day",
                "closure_type": SchoolClosure.ClosureType.HOLIDAY,
                "start_date": "2026-09-10",
                "end_date": "2026-09-10",
            },
            secure=True,
        )
        self.assertRedirects(response, reverse("attendance_calendar"), fetch_redirect_response=False)
        self.assertEqual(SchoolClosure.objects.get().school, self.school)
