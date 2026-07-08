from django.core.mail import send_mail
from django.conf import settings


def send_report_email(student, subject, report_text):
    """
    Sends the AI-generated performance report to the student's email.
    Returns True if successful, False otherwise.
    """
    if not student.email:
        return False, "This student doesn't have an email address on file."

    subject_line = f"Your Performance Report: {subject.name}"
    message = f"""Hi {student.username},

Here is your latest performance report for {subject.name}:

{report_text}

Keep up the great work!

- Nyansa Team
"""

    try:
        send_mail(
            subject_line,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [student.email],
            fail_silently=False,
        )
        return True, "Report sent successfully!"
    except Exception as e:
        return False, f"Failed to send email: {str(e)}"