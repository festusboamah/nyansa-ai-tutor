import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import connection

from accounts.models import User
from courses.models import Enrollment, Material, StudyDocument, Subject
from dashboard.models import LessonNote
from quizzes.models import Assignment, AssignmentSubmission, Quiz, Submission


class Command(BaseCommand):
    help = "Report non-sensitive baseline counts and migration risks without changing data."

    def add_arguments(self, parser):
        parser.add_argument(
            "--output",
            type=Path,
            help="Optional JSON output path. Parent directory must already exist.",
        )

    def handle(self, *args, **options):
        users_by_role = {
            role: User.objects.filter(role=role).count()
            for role, _label in User.Role.choices
        }
        counts = {
            "users": User.objects.count(),
            "subjects": Subject.objects.count(),
            "enrollments": Enrollment.objects.count(),
            "materials": Material.objects.count(),
            "study_documents": StudyDocument.objects.count(),
            "quizzes": Quiz.objects.count(),
            "quiz_submissions": Submission.objects.count(),
            "assignments": Assignment.objects.count(),
            "assignment_submissions": AssignmentSubmission.objects.count(),
            "lesson_notes": LessonNote.objects.count(),
        }
        risks = {
            "users_with_unknown_role": User.objects.exclude(
                role__in=[choice for choice, _label in User.Role.choices]
            ).count(),
            "duplicate_enrollments": self._duplicate_enrollment_count(),
            "graded_assignments_without_grader_timestamp": AssignmentSubmission.objects.filter(
                final_score__isnull=False, graded_at__isnull=True
            ).count(),
            "quiz_submissions_without_score": Submission.objects.filter(score__isnull=True).count(),
            "lesson_notes_without_generated_content": LessonNote.objects.filter(
                generated_content=""
            ).count(),
        }
        media_root = Path(settings.MEDIA_ROOT)
        report = {
            "database": {
                "vendor": connection.vendor,
                "name": Path(connection.settings_dict["NAME"]).name
                if connection.vendor == "sqlite"
                else connection.settings_dict["NAME"],
            },
            "counts": counts,
            "users_by_role": users_by_role,
            "migration_risks": risks,
            "media": {
                "configured": str(media_root),
                "exists": media_root.exists(),
                "file_count": sum(1 for item in media_root.rglob("*") if item.is_file())
                if media_root.exists()
                else 0,
            },
        }

        rendered = json.dumps(report, indent=2, sort_keys=True)
        self.stdout.write(rendered)

        output = options.get("output")
        if output:
            output = output.resolve()
            if not output.parent.exists():
                raise ValueError(f"Output directory does not exist: {output.parent}")
            output.write_text(rendered + "\n", encoding="utf-8")

    @staticmethod
    def _duplicate_enrollment_count():
        # A database uniqueness constraint currently prevents duplicates. Keeping this
        # check makes migration rehearsals explicitly verify the assumption.
        from django.db.models import Count

        return (
            Enrollment.objects.values("student_id", "subject_id")
            .annotate(total=Count("id"))
            .filter(total__gt=1)
            .count()
        )
