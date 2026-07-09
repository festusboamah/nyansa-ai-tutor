# 📘 Nyansa — AI-Powered Tutoring Platform

**Nyansa** (Twi for *"wisdom"*) is a full-stack, AI-powered learning management system built for an M.Ed Capstone Project. It's designed to help students learn faster through instant AI feedback, and help teachers teach more by automating grading, content creation, and reporting — while keeping human judgment at the center of every important decision.

> Technology should sharpen human wisdom, not replace it.

---

## ✨ Key Features

### For Students
- 📚 Browse subjects, materials, and self-enroll in courses
- 📝 Take quizzes with **AI-graded short answers** and instant multiple-choice scoring
- ⏱ Countdown timers, attempt limits, and retake support on every quiz
- 🏆 Earn achievement badges (Perfect Score, First-Try Success, Most Improved)
- 📄 **Self-Study Hub** — upload any PDF, get an AI-generated summary, and ask follow-up questions
- 📊 Weighted grading per subject (Quiz 20% + Assignment 20% + Exam 60%), calculated automatically
- ⏰ Deadline radar — see every upcoming quiz, exam, and assignment due date in one place
- 🎓 Downloadable transcript (PDF) with per-subject averages
- 👤 Personal profile with login tracking and quiz statistics

### For Teachers
- ➕ Create subjects, upload materials, and manage content — no Django admin required
- 🤖 **AI Quiz Generator** — describe a topic, get a complete multiple-choice quiz in seconds
- 📋 **AI Lesson Notes** — generates full standards-based (GES-format) weekly lesson plans as downloadable PDFs
- 📈 **AI-generated student performance reports**, emailable directly to students
- 📎 Assignment grading with a **hybrid AI + teacher workflow** — Claude suggests a score and feedback, but the teacher always reviews and finalizes before a student sees anything
- 👥 Class dashboard showing enrolled students and their progress at a glance

### Platform-Wide
- 🔐 Role-based access control (Student / Teacher) with a custom Django User model
- 🎨 Custom-designed, animated UI (no frontend framework — hand-built CSS)
- 🛡️ Secure `.env`-based configuration for API keys and email credentials

---

## 🧠 AI Integration

Nyansa uses **Anthropic's Claude API** (Claude Sonnet 4.5) across nine distinct features:

| Feature | Description |
|---|---|
| Short-answer grading | Evaluates open-ended quiz responses, not just keyword matching |
| Per-answer feedback | Personalized explanation for every question |
| Quiz summary feedback | Encouraging, actionable overall feedback per submission |
| Teacher performance reports | Narrative analysis of a student's progress over time |
| AI quiz generation | Generates a full quiz from a topic description |
| PDF summarization | Summarizes uploaded study documents |
| Document Q&A | Answers student questions grounded in their uploaded material |
| AI lesson notes | Generates standards-based weekly lesson plans |
| Assignment grading suggestions | Suggests a score + feedback for teacher review (never final without approval) |

**Design principle:** AI is used for full automation only where the task is mechanical (e.g. MCQ grading). Anywhere real judgment is required (assignment grading), AI assists but a human teacher always has the final say.

---

## 🛠️ Tech Stack

- **Backend:** Django (Python)
- **Database:** SQLite
- **AI:** Anthropic Claude API
- **PDF Processing:** pypdf, xhtml2pdf
- **Markdown Rendering:** python-markdown
- **Frontend:** Custom HTML/CSS (no framework), vanilla JavaScript for timers/interactivity
- **Version Control:** Git & GitHub

---

## 🚀 Getting Started

### Prerequisites
- Python 3.11+
- An [Anthropic API key](https://console.anthropic.com)

### Installation

```bash
# Clone the repository
git clone https://github.com/festusboamah/nyansa-ai-tutor.git
cd nyansa-ai-tutor

# Create and activate a virtual environment
python -m venv venv
venv\Scripts\activate      # Windows
source venv/bin/activate   # macOS/Linux

# Install dependencies
pip install -r requirements.txt

# Set up environment variables
# Create a .env file in the project root with:
# ANTHROPIC_API_KEY=your-key-here

# Run migrations
python manage.py migrate

# Create a superuser (for admin access)
python manage.py createsuperuser

# Start the development server
python manage.py runserver
```

Visit `http://127.0.0.1:8000` in your browser.

---

## 📁 Project Structure