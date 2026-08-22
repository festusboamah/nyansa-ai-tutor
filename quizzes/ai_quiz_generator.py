from django.db import transaction

from ai_core.client import AIError, complete_json


def generate_quiz_questions(topic, num_questions, difficulty, *, school=None):
    """
    Returns a list of dicts like:
    [{"text": "...", "question_type": "MCQ", "choices": [{"text": "...", "is_correct": True}, ...]}, ...]
    """
    prompt = f"""You are creating quiz questions for a student learning platform.

Topic: {topic}
Number of questions: {num_questions}
Difficulty: {difficulty}

Generate {num_questions} multiple-choice questions on this topic, at {difficulty} difficulty.
Each question must have exactly 4 answer choices, with exactly one marked correct.

Respond ONLY with valid JSON in this exact structure, no other text:
{{
  "questions": [
    {{
      "text": "question text here",
      "choices": [
        {{"text": "choice 1", "is_correct": false}},
        {{"text": "choice 2", "is_correct": true}},
        {{"text": "choice 3", "is_correct": false}},
        {{"text": "choice 4", "is_correct": false}}
      ]
    }}
  ]
}}"""

    try:
        result = complete_json(prompt, max_tokens=2000, school=school, source="quiz_generation")
        return result.get("questions", [])
    except AIError:
        return []


def create_bank_questions(subject, topic, difficulty, topic_description, num_questions, created_by):
    """
    Generates questions via generate_quiz_questions and persists them as
    BankQuestion/BankQuestionChoice rows, PENDING_REVIEW. Returns the created BankQuestions.
    """
    from .models import BankQuestion, BankQuestionChoice, Question

    generated = generate_quiz_questions(topic_description, num_questions, difficulty, school=subject.school)

    created = []
    with transaction.atomic():
        for q_data in generated:
            text = q_data.get("text", "").strip()
            if not text:
                continue
            bank_question = BankQuestion.objects.create(
                subject=subject,
                topic=topic,
                created_by=created_by,
                text=text,
                question_type=Question.QuestionType.MULTIPLE_CHOICE,
                difficulty=difficulty,
            )
            for choice_data in q_data.get("choices", []):
                choice_text = choice_data.get("text", "").strip()
                if not choice_text:
                    continue
                BankQuestionChoice.objects.create(
                    question=bank_question,
                    text=choice_text,
                    is_correct=choice_data.get("is_correct", False),
                )
            created.append(bank_question)

    return created
