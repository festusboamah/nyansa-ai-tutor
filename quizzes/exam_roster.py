from academics.models import ClassEnrollment


def eligible_students_for_exam(quiz):
    """
    Returns a queryset of schools.SchoolMembership eligible to sit `quiz`.
    If the exam has no linked offerings, any active student in the quiz's
    school is eligible (legacy quiz behavior). Otherwise, eligibility is
    every actively-enrolled student across the linked offerings' classes.
    """
    from schools.models import SchoolMembership

    offerings = quiz.offerings.all()
    if not offerings.exists():
        return SchoolMembership.objects.filter(
            school=quiz.subject.school,
            role=SchoolMembership.Role.STUDENT,
            status=SchoolMembership.Status.ACTIVE,
        )

    class_ids = offerings.values_list("school_class_id", flat=True)
    student_ids = ClassEnrollment.objects.filter(
        school_class_id__in=class_ids, status=ClassEnrollment.Status.ACTIVE,
    ).values_list("student_id", flat=True)
    return SchoolMembership.objects.filter(id__in=student_ids, status=SchoolMembership.Status.ACTIVE)


def student_may_sit_exam(quiz, membership):
    if membership is None:
        return False
    return eligible_students_for_exam(quiz).filter(id=membership.id).exists()
