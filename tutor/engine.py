import anthropic
from django.conf import settings
from django.utils import timezone

from academics.models import Term
from courses.study_ai import get_or_extract_material_text
from mastery.models import Misconception
from mastery.services import student_subject_mastery, topic_mastery_for_student
from schools.models import SchoolMembership

from .modes import build_system_prompt
from .models import (
    DEFAULT_MAX_HINT_DEPTH, DIFFICULTY_ORDER, DifficultyLevel, TutorMessage, TutorMessageRole, TutorMode,
    TutorSettings, TutorUsageEvent,
)

client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

FALLBACK_REPLY = "I'm having trouble responding right now. Please try again in a moment."
EXAM_MODE_REPLY = (
    "Exam Mode turns tutoring off during a timed attempt - head to your quizzes to "
    "take the assessment; I'll be here to help you prepare before or review after."
)
HINT_LIMIT_REPLY = (
    "You've used all your hints for this problem. Try working through what you have so far, "
    "or ask your teacher for more help."
)
QUOTA_EXCEEDED_REPLY = (
    "Your school has reached its tutor AI usage limit for today. Please try again tomorrow, "
    "or ask your teacher for help in the meantime."
)
ASSESSMENT_PERIOD_REPLY = (
    "The tutor is temporarily unavailable during your school's assessment period. "
    "Please check with your teacher if you need help before then."
)

NEEDS_SUPPORT_STATUSES = {"NEEDS_SUPPORT", "DEVELOPING"}


def _build_messages(session):
    role_map = {
        TutorMessageRole.STUDENT: "user",
        TutorMessageRole.TUTOR: "assistant",
    }
    return [
        {"role": role_map[m.role], "content": m.content}
        for m in session.messages.all()
    ]


def _mastery_context(session):
    if not session.subject_id:
        return None
    try:
        membership = SchoolMembership.objects.get(school=session.school, user=session.student)
        term = Term.objects.filter(
            academic_year__school=session.school
        ).order_by("-academic_year__start_date", "-order").first()
        if term is None:
            return None
        breakdown = student_subject_mastery(membership, session.subject, term)
    except Exception:
        return None

    topics = [
        topic_row["topic"].name
        for strand_row in breakdown["strands"]
        for topic_row in strand_row["topics"]
        if topic_row["status"] in NEEDS_SUPPORT_STATUSES
    ]
    return topics or None


def _hint_state(session):
    """Returns (hint_guidance, limit_reached_without_reveal) for a HINT-mode session.
    Hint number is derived from how many tutor replies this session already has -
    each prior reply in Hint mode was one hint given."""
    settings_row = TutorSettings.objects.filter(school=session.school).first()
    max_hint_depth = settings_row.max_hint_depth if settings_row else DEFAULT_MAX_HINT_DEPTH
    allow_reveal = settings_row.allow_final_answer_reveal if settings_row else False

    hint_number = session.messages.filter(role=TutorMessageRole.TUTOR).count() + 1

    if hint_number > max_hint_depth:
        if not allow_reveal:
            return None, True
        return (
            f"The student has used all {max_hint_depth} hints for this problem. Reveal the "
            "final answer now with a clear, step-by-step explanation of how to reach it.",
            False,
        )

    return (
        f"This is hint {hint_number} of {max_hint_depth} for this problem. Make it a little "
        "more specific than any earlier hint, but do not reveal the final answer yet.",
        False,
    )


def _grounding_text(session):
    """Teacher-approved material takes precedence over a student's own upload."""
    if session.material_id:
        return get_or_extract_material_text(session.material)
    if session.study_document_id:
        return session.study_document.extracted_text
    return None


def _quota_exceeded(school):
    settings_row = TutorSettings.objects.filter(school=school).first()
    limit = settings_row.daily_usage_limit if settings_row else None
    if limit is None:
        return False
    today = timezone.now().date()
    used = TutorUsageEvent.objects.filter(session__school=school, created_at__date=today).count()
    return used >= limit


def _in_assessment_period(school):
    settings_row = TutorSettings.objects.filter(school=school).first()
    if not settings_row or not settings_row.restricted_period_start or not settings_row.restricted_period_end:
        return False
    today = timezone.now().date()
    return settings_row.restricted_period_start <= today <= settings_row.restricted_period_end


def _topic_focus(session):
    if not session.topic_id:
        return None
    return f"{session.topic.strand.name} · {session.topic.name}"


MASTERY_STATUS_TARGET_DIFFICULTY = {
    "NEEDS_SUPPORT": DifficultyLevel.EASY,
    "DEVELOPING": DifficultyLevel.MEDIUM,
    "MASTERED": DifficultyLevel.HARD,
}


def _mastery_target_difficulty(session, min_difficulty, max_difficulty):
    if not session.topic_id:
        return None
    try:
        membership = SchoolMembership.objects.get(school=session.school, user=session.student)
        term = Term.objects.filter(
            academic_year__school=session.school
        ).order_by("-academic_year__start_date", "-order").first()
        if term is None:
            return None
        result = topic_mastery_for_student(membership, session.topic, term)
    except Exception:
        return None

    target = MASTERY_STATUS_TARGET_DIFFICULTY.get(result["status"])
    if target is None:
        return None
    order = DIFFICULTY_ORDER
    clamped_index = min(max(order.index(target), order.index(min_difficulty)), order.index(max_difficulty))
    return order[clamped_index]


def _difficulty_range(session):
    if session.mode != TutorMode.PRACTICE:
        return None
    settings_row = TutorSettings.objects.filter(school=session.school).first()
    min_difficulty = settings_row.min_difficulty if settings_row else DifficultyLevel.EASY
    max_difficulty = settings_row.max_difficulty if settings_row else DifficultyLevel.HARD
    min_label = DifficultyLevel(min_difficulty).label
    max_label = DifficultyLevel(max_difficulty).label

    target = _mastery_target_difficulty(session, min_difficulty, max_difficulty)
    if target is not None:
        return (
            f"Based on this student's current mastery of this topic, generate practice questions "
            f"at {DifficultyLevel(target).label} difficulty. Stay within the school's allowed range: "
            f"{min_label} to {max_label}."
        )

    if min_difficulty == DifficultyLevel.EASY and max_difficulty == DifficultyLevel.HARD:
        return None
    return (
        f"Keep generated practice questions within this difficulty range: {min_label} to "
        f"{max_label}. Do not go easier than {min_label} or harder than {max_label}."
    )


def _record_misconception(session, student_text, hypothesis_text):
    """One Misconception row per session, not per message - a follow-up message
    in the same EXPLAIN_MY_MISTAKE conversation updates the hypothesis rather than
    creating a duplicate. Never touches `status`, so a teacher's dismiss/resolve
    call survives later messages in the same session. Never raises."""
    try:
        student_membership = SchoolMembership.objects.get(school=session.school, user=session.student)
        Misconception.objects.update_or_create(
            source_session=session,
            defaults={
                "school": session.school,
                "student": student_membership,
                "topic": session.topic,
                "student_description": student_text,
                "hypothesis": hypothesis_text,
            },
        )
    except Exception:
        pass


def send_message(session, student_text):
    """
    Persists the student's message, calls Claude for a reply in the session's
    mode, and persists the tutor's reply (or a graceful fallback on failure)
    plus a usage event. Never raises - AI failure must not block the chat.
    """
    TutorMessage.objects.create(
        session=session, role=TutorMessageRole.STUDENT, content=student_text
    )

    if _in_assessment_period(session.school):
        return TutorMessage.objects.create(
            session=session, role=TutorMessageRole.TUTOR, content=ASSESSMENT_PERIOD_REPLY
        )

    if session.mode == TutorMode.EXAM_MODE:
        return TutorMessage.objects.create(
            session=session, role=TutorMessageRole.TUTOR, content=EXAM_MODE_REPLY
        )

    hint_guidance = None
    if session.mode == TutorMode.HINT:
        hint_guidance, limit_reached = _hint_state(session)
        if limit_reached:
            return TutorMessage.objects.create(
                session=session, role=TutorMessageRole.TUTOR, content=HINT_LIMIT_REPLY
            )

    if _quota_exceeded(session.school):
        return TutorMessage.objects.create(
            session=session, role=TutorMessageRole.TUTOR, content=QUOTA_EXCEEDED_REPLY
        )

    mastery_context = (
        _mastery_context(session) if session.mode == TutorMode.REVISE_WITH_ME else None
    )
    system_prompt = build_system_prompt(
        session.mode,
        subject_name=session.subject.name if session.subject else None,
        grounding_text=_grounding_text(session),
        mastery_context=mastery_context,
        hint_guidance=hint_guidance,
        topic_focus=_topic_focus(session),
        difficulty_range=_difficulty_range(session),
    )
    # session.messages.all() already includes the student message just created above.
    messages = _build_messages(session)
    model = settings.TUTOR_AI_MODEL

    ai_succeeded = False
    try:
        response = client.messages.create(
            model=model,
            max_tokens=1000,
            system=system_prompt,
            messages=messages,
        )
        reply_text = response.content[0].text.strip()
        ai_succeeded = True
        TutorUsageEvent.objects.create(
            session=session,
            model=model,
            input_tokens=getattr(response.usage, "input_tokens", None),
            output_tokens=getattr(response.usage, "output_tokens", None),
            succeeded=True,
        )
    except Exception as exc:
        reply_text = FALLBACK_REPLY
        TutorUsageEvent.objects.create(
            session=session,
            model=model,
            succeeded=False,
            error_message=str(exc),
        )

    if ai_succeeded and session.mode == TutorMode.EXPLAIN_MY_MISTAKE:
        _record_misconception(session, student_text, reply_text)

    return TutorMessage.objects.create(
        session=session, role=TutorMessageRole.TUTOR, content=reply_text
    )
