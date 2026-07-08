QUIZ_WEIGHT = 0.20
ASSIGNMENT_WEIGHT = 0.20
EXAM_WEIGHT = 0.60


def letter_grade(percent):
    if percent is None:
        return "N/A"
    if percent >= 80:
        return "A"
    elif percent >= 70:
        return "B"
    elif percent >= 60:
        return "C"
    elif percent >= 50:
        return "D"
    else:
        return "F"


def calculate_subject_grade(student, subject):
    """
    Returns a dict with category breakdowns and final weighted score/grade for one subject.
    """
    from quizzes.models import Submission, AssignmentSubmission, Quiz

    quiz_submissions = Submission.objects.filter(
        student=student, quiz__subject=subject, quiz__assessment_type=Quiz.AssessmentType.QUIZ
    )
    exam_submissions = Submission.objects.filter(
        student=student, quiz__subject=subject, quiz__assessment_type=Quiz.AssessmentType.EXAM
    )
    assignment_submissions = AssignmentSubmission.objects.filter(
        student=student, assignment__subject=subject, final_score__isnull=False
    )

    def average_score(submissions, score_field="score"):
        scores = [getattr(s, score_field) for s in submissions if getattr(s, score_field) is not None]
        return round(sum(scores) / len(scores), 1) if scores else None

    quiz_avg = average_score(quiz_submissions)
    exam_avg = average_score(exam_submissions)
    assignment_avg = average_score(assignment_submissions, score_field="final_score")

    # Only count categories that have at least one graded submission, and re-weight proportionally
    categories = []
    if quiz_avg is not None:
        categories.append((quiz_avg, QUIZ_WEIGHT))
    if exam_avg is not None:
        categories.append((exam_avg, EXAM_WEIGHT))
    if assignment_avg is not None:
        categories.append((assignment_avg, ASSIGNMENT_WEIGHT))

    if not categories:
        final_score = None
    else:
        total_weight = sum(weight for _, weight in categories)
        final_score = round(sum(score * weight for score, weight in categories) / total_weight, 1)

    return {
        "quiz_avg": quiz_avg,
        "exam_avg": exam_avg,
        "assignment_avg": assignment_avg,
        "final_score": final_score,
        "final_grade": letter_grade(final_score),
    }