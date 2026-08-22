from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from academics.models import ClassEnrollment, TeacherAssignment
from gradebook.models import GradeEntry
from quizzes.models import Answer
from schools.models import SchoolMembership
from tutor.models import TutorSession

from .models import Misconception, RemediationPlan, Strand, Topic, TopicRevision

REVISION_DUE_AFTER = timedelta(days=7)


def can_view_class(actor, school_class, term):
    if actor.school_id != school_class.school_id or not actor.is_active:
        return False
    if actor.role == SchoolMembership.Role.SCHOOL_ADMIN:
        return True
    return actor.role == SchoolMembership.Role.TEACHER and (
        school_class.class_teacher_id == actor.id or TeacherAssignment.objects.filter(
            teacher=actor, offering__school_class=school_class, offering__term=term
        ).exists()
    )


def _bucket(percentage):
    if percentage is None:
        return "NO_EVIDENCE"
    if percentage >= 80:
        return "MASTERED"
    if percentage >= 50:
        return "DEVELOPING"
    return "NEEDS_SUPPORT"


def _assessment_percentages(entries):
    values = list(entries.values_list("score", "assessment__max_score"))
    return [score / max_score * Decimal("100") for score, max_score in values if max_score]


def _question_percentages(student_user_ids, topic, term):
    """Each answered question tagged with `topic`, for a submission whose quiz is
    linked to a gradebook Assessment scoped to `term`, is one evidence item."""
    if isinstance(student_user_ids, int):
        student_user_ids = [student_user_ids]
    values = Answer.objects.filter(
        question__topic=topic,
        submission__student_id__in=student_user_ids,
        submission__quiz__gradebook_assessment__offering__term=term,
        is_correct__isnull=False,
    ).values_list("is_correct", flat=True)
    return [Decimal("100") if correct else Decimal("0") for correct in values]


def _combine(assessment_percentages, question_percentages, term):
    all_percentages = assessment_percentages + question_percentages
    average = (
        (sum(all_percentages, Decimal("0")) / len(all_percentages)).quantize(Decimal("0.01"))
        if all_percentages else None
    )
    return {
        "mastery_percentage": average,
        "status": _bucket(average),
        "evidence_count": len(all_percentages),
        "assessment_evidence_count": len(assessment_percentages),
        "question_evidence_count": len(question_percentages),
        "source": "Published, administrator-approved gradebook entries and quiz-question attempts tagged with this topic",
        "period": f"{term.academic_year.name} · {term.name}",
    }


def topic_mastery_for_student(student, topic, term):
    entries = GradeEntry.objects.filter(
        student=student, assessment__topic=topic, assessment__offering__term=term,
        status=GradeEntry.Status.PUBLISHED, review_status=GradeEntry.ReviewStatus.APPROVED,
    )
    result = _combine(
        _assessment_percentages(entries), _question_percentages(student.user_id, topic, term), term
    )
    result["topic"] = topic
    return result


def _creates_cycle(topic, new_prerequisite):
    """Would adding `new_prerequisite` as a prerequisite of `topic` create a cycle -
    i.e. is `topic` already reachable from `new_prerequisite` via existing edges?"""
    visited, stack = set(), [new_prerequisite]
    while stack:
        current = stack.pop()
        if current.id == topic.id:
            return True
        if current.id in visited:
            continue
        visited.add(current.id)
        stack.extend(current.prerequisites.all())
    return False


def add_topic_prerequisite(topic, prerequisite):
    if topic.id == prerequisite.id:
        raise ValidationError("A topic cannot be its own prerequisite.")
    if _creates_cycle(topic, prerequisite):
        raise ValidationError("That would create a circular prerequisite chain.")
    topic.prerequisites.add(prerequisite)


def unmet_prerequisites(student, topic, term):
    """This topic's prerequisites the student hasn't yet MASTERED, each with
    their own topic_mastery_for_student result attached."""
    unmet = []
    for prerequisite in topic.prerequisites.all():
        result = topic_mastery_for_student(student, prerequisite, term)
        if result["status"] != "MASTERED":
            unmet.append({"topic": prerequisite, "result": result})
    return unmet


@transaction.atomic
def update_topic(*, topic, actor, name=None, strand=None, reason):
    reason = reason.strip()
    if not reason:
        raise ValidationError("A reason is required to edit a topic.")
    changed = bool(name and name != topic.name) or bool(strand and strand.id != topic.strand_id)
    if not changed:
        raise ValidationError("No changes to save.")
    previous_name, previous_strand_name = topic.name, topic.strand.name
    if name:
        topic.name = name
    if strand:
        topic.strand = strand
    topic.full_clean()
    topic.save()
    TopicRevision.objects.create(
        topic=topic, previous_name=previous_name, new_name=topic.name,
        previous_strand_name=previous_strand_name, new_strand_name=topic.strand.name,
        reason=reason, changed_by=actor,
    )
    return topic


def goal_revision_status(goal, term):
    last_session = TutorSession.objects.filter(
        student=goal.student.user, topic=goal.topic
    ).order_by("-created_at").first()
    last_studied_at = last_session.created_at if last_session else None
    due = last_studied_at is None or timezone.now() - last_studied_at > REVISION_DUE_AFTER
    mastery = topic_mastery_for_student(goal.student, goal.topic, term) if term else None
    return {"last_studied_at": last_studied_at, "due": due, "mastery": mastery}


def student_subject_mastery(student, subject, term):
    strands = Strand.objects.filter(subject=subject).prefetch_related("topics")
    rows = []
    for strand in strands:
        topic_rows = [topic_mastery_for_student(student, topic, term) for topic in strand.topics.all()]
        rows.append({"strand": strand, "topics": topic_rows})
    return {
        "period": f"{term.academic_year.name} · {term.name}",
        "subject": subject,
        "strands": rows,
    }


def class_topic_mastery(school_class, topic, term):
    roster = ClassEnrollment.objects.filter(
        school_class=school_class, status=ClassEnrollment.Status.ACTIVE
    ).select_related("student")
    roster_student_ids = [enrollment.student_id for enrollment in roster]
    roster_user_ids = [enrollment.student.user_id for enrollment in roster]

    entries = GradeEntry.objects.filter(
        student_id__in=roster_student_ids, assessment__topic=topic, assessment__offering__term=term,
        status=GradeEntry.Status.PUBLISHED, review_status=GradeEntry.ReviewStatus.APPROVED,
    )
    result = _combine(
        _assessment_percentages(entries), _question_percentages(roster_user_ids, topic, term), term
    )
    result["topic"] = topic
    result["student_count"] = len(roster_student_ids)
    return result


def class_topic_bands(school_class, subject, term):
    """Per-topic counts of each mastery band across the class roster."""
    roster = ClassEnrollment.objects.filter(
        school_class=school_class, status=ClassEnrollment.Status.ACTIVE
    ).select_related("student")
    strands = Strand.objects.filter(subject=subject).prefetch_related("topics")
    rows = []
    for strand in strands:
        for topic in strand.topics.all():
            counts = {"MASTERED": 0, "DEVELOPING": 0, "NEEDS_SUPPORT": 0, "NO_EVIDENCE": 0}
            for enrollment in roster:
                result = topic_mastery_for_student(enrollment.student, topic, term)
                counts[result["status"]] += 1
            rows.append({"strand": strand, "topic": topic, "counts": counts})
    return rows


def misconception_patterns(school_class, term):
    """Groups open misconceptions by topic, surfacing only genuine patterns:
    a topic where 2+ distinct students are affected, or one student recurs on it."""
    roster_student_ids = ClassEnrollment.objects.filter(
        school_class=school_class, status=ClassEnrollment.Status.ACTIVE
    ).values_list("student_id", flat=True)
    open_misconceptions = Misconception.objects.filter(
        student_id__in=roster_student_ids, status=Misconception.Status.OPEN, topic__isnull=False,
    ).select_related("student__user", "topic__strand")

    by_topic = {}
    for item in open_misconceptions:
        by_topic.setdefault(item.topic_id, {"topic": item.topic, "items": []})["items"].append(item)

    patterns = []
    for group in by_topic.values():
        by_student = {}
        for item in group["items"]:
            by_student.setdefault(item.student_id, {"student": item.student, "items": []})["items"].append(item)
        student_rows = sorted(by_student.values(), key=lambda row: -len(row["items"]))
        student_count = len(student_rows)
        if student_count >= 2 or any(len(row["items"]) >= 2 for row in student_rows):
            patterns.append({
                "topic": group["topic"], "student_count": student_count,
                "misconception_count": len(group["items"]), "students": student_rows,
            })

    patterns.sort(key=lambda row: (-row["student_count"], -row["misconception_count"]))
    return patterns


def remediation_plan_outcomes(school_class, term):
    roster_ids = ClassEnrollment.objects.filter(
        school_class=school_class, status=ClassEnrollment.Status.ACTIVE
    ).values_list("student_id", flat=True)
    plans = RemediationPlan.objects.filter(student_id__in=roster_ids, term=term)
    completed = plans.filter(status=RemediationPlan.Status.COMPLETED)
    comparable = completed.filter(
        mastery_percentage_at_start__isnull=False, mastery_percentage_at_completion__isnull=False,
    )
    improved = comparable.filter(mastery_percentage_at_completion__gt=F("mastery_percentage_at_start"))
    comparable_count = comparable.count()
    improved_count = improved.count()
    return {
        "period": f"{term.academic_year.name} · {term.name}",
        "source": "Completed remediation plans with recorded mastery at both start and completion",
        "plan_count": plans.count(),
        "completed_count": completed.count(),
        "comparable_count": comparable_count,
        "improved_count": improved_count,
        "improvement_rate": (
            (Decimal(improved_count) / comparable_count * 100).quantize(Decimal("0.01"))
            if comparable_count else None
        ),
    }


def remediation_plan_outcomes_for_classes(classes, term):
    rows = [{"school_class": item, "outcomes": remediation_plan_outcomes(item, term)} for item in classes]
    comparable_total = sum(row["outcomes"]["comparable_count"] for row in rows)
    improved_total = sum(row["outcomes"]["improved_count"] for row in rows)
    return {
        "period": f"{term.academic_year.name} · {term.name}",
        "source": "Completed remediation plans with recorded mastery at both start and completion",
        "plan_count": sum(row["outcomes"]["plan_count"] for row in rows),
        "completed_count": sum(row["outcomes"]["completed_count"] for row in rows),
        "comparable_count": comparable_total,
        "improved_count": improved_total,
        "improvement_rate": (
            (Decimal(improved_total) / comparable_total * 100).quantize(Decimal("0.01"))
            if comparable_total else None
        ),
        "classes": rows,
    }


def school_remediation_plan_outcomes(school, term):
    classes = school.classes.filter(academic_year=term.academic_year)
    return remediation_plan_outcomes_for_classes(classes, term)


def class_subject_mastery(school_class, subject, term):
    strands = Strand.objects.filter(subject=subject).prefetch_related("topics")
    rows = []
    for strand in strands:
        topic_rows = [class_topic_mastery(school_class, topic, term) for topic in strand.topics.all()]
        rows.append({"strand": strand, "topics": topic_rows})
    return {
        "period": f"{term.academic_year.name} · {term.name}",
        "subject": subject,
        "strands": rows,
    }
