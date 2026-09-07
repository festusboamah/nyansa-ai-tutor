"""What each institutional plan includes, for the comparison table on
billing/plans.html. Hardcoded, not a DB model: plan content here already
changes via numbered data migrations (0002/0003/0005/0006), not admin-UI
edits - the same fixed, code-level pattern TutorMode already uses, not
GradeBoundary's per-tenant-model one (these rows don't vary per school).

Individual Teacher is deliberately excluded - a different product for a
different buyer (one person, not a school), with its own signup page.

Partner's real description never commits to specific inclusions beyond the
Suku360 API ("Contact us - priced per partnership") - its cells stay
"Custom" rather than asserting claims the plan's own prose doesn't make.
"""

INSTITUTIONAL_COMPARISON_CODES = ["STARTER", "STANDARD", "PARTNER"]

FEATURE_ROWS = [
    (
        "Learning Workspace (subjects, materials, assignments, quizzes, gradebook, analytics)",
        {"STARTER": True, "STANDARD": True, "PARTNER": "Custom"},
    ),
    (
        "AI Tutor, Teacher Copilot, Mastery, AI analytics narratives",
        {"STARTER": False, "STANDARD": True, "PARTNER": "Custom"},
    ),
    (
        "Outbound Suku360 integration API",
        {"STARTER": False, "STANDARD": False, "PARTNER": True},
    ),
    (
        "AI usage billing",
        {"STARTER": "-", "STANDARD": "Cost + 20%", "PARTNER": "Custom"},
    ),
]
