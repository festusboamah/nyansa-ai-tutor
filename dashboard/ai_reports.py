from ai_core.client import AIError, complete_text


def generate_student_report(student, subject, submissions):
    if not submissions:
        return "This student has not attempted any quizzes in this subject yet."

    submission_details = []
    for sub in submissions:
        detail = f"Quiz: {sub.quiz.title} | Score: {sub.score}%"
        submission_details.append(detail)

    history_text = "\n".join(submission_details)
    scores = [s.score for s in submissions if s.score is not None]
    avg_score = round(sum(scores) / len(scores), 1) if scores else "N/A"

    prompt = f"""You are an assistant helping a teacher understand a student's progress.

Student: {student.username}
Subject: {subject.name}
Average score across all quizzes: {avg_score}%

Quiz history:
{history_text}

Write a concise, professional performance report (3-4 sentences) for the teacher. Include:
1. An overall assessment of the student's performance
2. Specific strengths observed
3. Any areas that may need attention or reinforcement
4. One actionable suggestion for the teacher

Respond with ONLY the report text, no preamble or headers."""

    try:
        return complete_text(prompt, max_tokens=300)
    except AIError:
        return "A performance report could not be generated automatically right now. Review the quiz history above directly."