# Nyansa learning frontend

The learning workspace uses the existing Django views, authentication and school context. It adds responsive learner and teacher dashboards, searchable subjects and study documents, subject resource sections, and an accessible tutor setup form. No database migration or JavaScript build step is required.

Shared templates live in `templates/learning/`; existing route templates inherit them. `static/css/learning-workspace.css` contains the visual system, and `static/js/learning-workspace.js` progressively enhances search and enrolment confirmation. All content remains available without JavaScript. The service worker cache version changes to refresh assets; authenticated HTML remains uncached.

Teacher subjects include material, quiz and assignment ownership within the current school. Learner deadlines exclude draft quizzes and apply the existing exam roster permission check. Learning scores retain the existing calculation and do not establish official school report-card authority. Tutor field names, source grounding, CSRF protection and server validation are preserved.

## Verification

Run `python manage.py test courses.test_learning_workspace courses.tests dashboard.tests accounts.tests config.tests tutor.tests --noinput` with the repository's development/test settings and dependencies installed. Focused workspace tests cover tenant boundaries, role access, escaped names, draft visibility, subject sections and preserved form fields.

Browser review should cover learner and teacher dashboards, matching and empty search results, mobile navigation and keyboard focus, subject resources, study documents, and tutor source controls. Use synthetic learner data for screenshots. Check both desktop and a 390-pixel phone viewport.
