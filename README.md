# Nyansa: AI-Powered Tutoring Platform

Nyansa (Twi for "wisdom") is a Django learning management system built for an M.Ed capstone project. It gives students timely feedback and gives teachers tools for creating content, reviewing work, and tracking progress. Human teachers retain control over decisions that need professional judgment.

> Technology should sharpen human wisdom, not replace it.

## Features

### Students

- Browse subjects, study materials, and enroll in available subjects.
- Take timed quizzes and exams with retakes and attempt limits.
- Receive automatic multiple-choice scoring and AI-assisted feedback for short answers.
- Submit assignments and view teacher-approved feedback.
- Upload PDFs to the Self-Study Hub for summaries and document-grounded questions.
- Track upcoming deadlines, subject grades, badges, profile statistics, and login activity.
- Download a transcript PDF with per-subject averages.

### Teachers

- Create subjects, upload learning materials, and manage quizzes without using the Django admin.
- Generate multiple-choice quizzes from a topic with Claude.
- Create GES-format lesson notes and download them as PDFs.
- Review AI-generated assignment score and feedback suggestions before releasing grades.
- View class progress, create student performance reports, and email reports when email is configured.

### Platform

- Custom Django user model with `STUDENT` and `TEACHER` roles.
- Role-aware dashboards and routes.
- Weighted subject grades: quizzes 20%, assignments 20%, and exams 60%.
- SQLite database for local development and local media storage for uploaded documents.

## AI Use

Nyansa uses Anthropic's Claude API for short-answer feedback, quiz summary feedback, quiz generation, study-document summaries and Q&A, student reports, lesson notes, and assignment grading suggestions.

AI-generated assignment grading is advisory. A teacher reviews and finalizes the score and feedback before a student can see it. Multiple-choice questions are scored deterministically by the application.

## Tech Stack

- Python and Django
- SQLite
- Anthropic Claude API
- `pypdf` for uploaded PDF text extraction
- `xhtml2pdf` for transcripts and lesson-note PDFs
- `Markdown` for report rendering
- Custom HTML, CSS, and vanilla JavaScript

## Getting Started

### Prerequisites

- Python 3.11 or later
- An Anthropic API key for AI-powered features

### Install and run

```bash
git clone https://github.com/festusboamah/nyansa-ai-tutor.git
cd nyansa-ai-tutor

# Create and activate a virtual environment.
python -m venv .venv

# Windows PowerShell
.\.venv\Scripts\Activate.ps1

# macOS/Linux
source .venv/bin/activate

# Install application dependencies.
python -m pip install --upgrade pip
pip install -r requirements.txt

# Create .env from .env.example and replace DJANGO_SECRET_KEY with a
# newly generated secret before running Django commands.

# Apply the database schema.
python manage.py migrate

# Verify the current baseline.
python manage.py test
python manage.py baseline_audit

# Create an administrator account (optional).
python manage.py createsuperuser

# Start the development server.
python manage.py runserver
```

Open `http://127.0.0.1:8000/` in a browser. Django's admin is available at `http://127.0.0.1:8000/admin/` for a superuser.

## Configuration

Create a `.env` file in the repository root. It is ignored by Git.

```dotenv
# Required. Generate a unique value with:
# python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
DJANGO_SECRET_KEY=replace-with-a-unique-secret

# Set to True only for local development.
DJANGO_DEBUG=True
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1

# Required for Claude-powered features.
ANTHROPIC_API_KEY=your-anthropic-api-key

# Optional: email defaults to Django's console backend, which prints emails
# to the terminal during local development.
EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend
EMAIL_HOST=
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=
EMAIL_HOST_PASSWORD=
DEFAULT_FROM_EMAIL=Nyansa <noreply@nyansa.com>
```

To send email through SMTP, set `EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend` and provide the SMTP host and credentials. Do not commit `.env` or API keys.

The default local configuration uses SQLite (`db.sqlite3`) and writes uploaded PDFs to `media/`. Both are intentionally ignored by Git. Set `DJANGO_DEBUG=True` only for local development. For HTTPS deployments, `DJANGO_SECURE_SSL_REDIRECT` defaults to `True` and can be explicitly disabled only when TLS is terminated elsewhere.

## Accounts and Roles

New registrations create `STUDENT` accounts. Create a `TEACHER` account through the Django admin, then set its role to `Teacher`. Teachers can create subjects and assessments; students can enroll, study, and submit work.

## Key Routes

| Route | Purpose |
| --- | --- |
| `/` | Home page |
| `/accounts/signup/` | Student registration |
| `/accounts/login/` | Sign in |
| `/courses/dashboard/` | Student dashboard |
| `/courses/browse/` | Browse and enroll in subjects |
| `/courses/study/` | Self-Study Hub |
| `/courses/transcript/` | Student transcript |
| `/quizzes/create-choice/` | Choose and create a quiz |
| `/dashboard/` | Teacher dashboard |
| `/admin/` | Django administration |

## Project Structure

```text
accounts/        Custom user model, authentication, and profile views
config/          Django settings, root URLs, ASGI, and WSGI configuration
courses/         Subjects, enrolments, materials, study documents, transcripts
dashboard/       Teacher dashboard, reports, email, and lesson notes
quizzes/         Quizzes, exams, assignments, grading, and AI generation
static/          CSS and image assets
templates/       Shared and app-specific Django templates
manage.py        Django management entry point
requirements.txt Python dependencies
```

## Project Roadmap Documentation

Nyansa's planned evolution into a multi-tenant school management system is documented in the [project documentation](docs/README.md). It covers the product vision, requirements, target architecture, domain model, tenancy and security rules, delivery phases, engineering workflow, and architecture decisions.

## Tests

Run the Django test suite with:

```bash
python manage.py test
```

## Development Notes

- AI features require a valid `ANTHROPIC_API_KEY`; other local pages and workflows can be explored without one, but AI requests will not succeed.
- Keep production secrets out of `config/settings.py`; supply them through environment variables.
- Before deployment, configure `DJANGO_ALLOWED_HOSTS`, use a production database and media storage, and serve static files with an appropriate production setup.

## License

This project is available under the [MIT License](LICENSE).
