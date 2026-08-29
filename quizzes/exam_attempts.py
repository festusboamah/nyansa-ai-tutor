from datetime import timedelta

from django.utils import timezone

from .exam_fees import fee_balance_blocks_exam
from .exam_roster import student_may_sit_exam
from .models import Submission


def exam_start_blocker(quiz, user, membership):
    """
    Returns an error message if `user` (with school membership `membership`)
    cannot start an attempt on `quiz` right now, or None if they can.
    Shared between the direct-start and webcam-consent start paths so both
    enforce the exact same rules.
    """
    if not student_may_sit_exam(quiz, membership):
        return "You are not on the roster for this exam."
    if fee_balance_blocks_exam(membership, quiz):
        return "You have an outstanding fee balance and cannot sit this exam. Please contact the school office."
    if quiz.is_before_start():
        return "This exam hasn't opened yet."
    if quiz.is_past_deadline():
        return "This exam has closed."
    if quiz.questions.count() == 0:
        return "This exam doesn't have any questions yet."

    attempts_used = Submission.objects.filter(quiz=quiz, student=user).count()
    if attempts_used >= quiz.max_attempts:
        return "You've used all your attempts for this exam."
    return None


def create_exam_submission(quiz, user, *, camera_consent_given=False):
    now = timezone.now()
    time_limit_end = now + timedelta(minutes=quiz.time_limit_minutes)
    expires_at = min(time_limit_end, quiz.deadline) if quiz.deadline else time_limit_end

    return Submission.objects.create(
        quiz=quiz, student=user, started_at=now, submitted_at=None, expires_at=expires_at,
        camera_consent_given=camera_consent_given,
        camera_consent_at=now if camera_consent_given else None,
    )
