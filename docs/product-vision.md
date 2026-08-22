# Product Vision

## Vision

Nyansa AI is the teaching-and-learning layer of the PagezTech education ecosystem: a platform that helps learners study, practise, and receive timely support, and helps teachers create learning experiences, assess work, understand mastery, and intervene pedagogically. It is not a full school-management system — Suku360 is the institutional system of record for school operations (attendance, fees, official grades, report cards, admissions, HR). See [`product-boundary.md`](product-boundary.md) for the full ownership line.

Nyansa means "wisdom" in Twi. The product promise is therefore not automation at any cost: **technology should sharpen human judgment, not replace it.**

## Product evolution

The current application already provides subjects, enrollments, learning materials, quizzes, assignments, AI-assisted grading, a Self-Study Hub, lesson-note generation, and a generalized gradebook — this is the core to strengthen. It also contains substantial school-operations functionality (attendance, fees/Mobile Money, guardian portal, term-report publication) built under the previous "full school system" direction; that functionality stays deployed and working, but is frozen for new scope and is a future extraction target once a Suku360 integration contract exists. See [`repository-audit.md`](repository-audit.md) for the concrete classification.

The governing design principle is:

> **Wrap, don't replace.** Extend the existing academic capabilities with tutoring, mastery, and teacher-copilot intelligence. Avoid parallel implementations of grading or content workflows, and avoid rebuilding institutional record-keeping that belongs to Suku360.

## Primary users

### Student

Learns from materials, completes online assessments where connectivity permits, receives tutoring and feedback, and reviews learning progress and mastery.

### Teacher

Manages assigned classes and subjects, creates learning content and assessments, enters grades, reviews AI suggestions, drafts lesson plans and feedback, and monitors student mastery and learning gaps.

### School administrator

Configures subjects, classes, and academic structure within Nyansa, and oversees teacher and student learning activity for their school. Institutional configuration (fees, official attendance policy, admissions) is Suku360's domain, not Nyansa's.

### Parent or guardian

Currently views linked children's results and progress inside Nyansa. Under the new boundary, school-wide guardian relationship records and official communications ownership move to Suku360 over time; Nyansa's role narrows to learning-progress visibility.

### Platform operator

Supports the shared service, manages tenants, investigates operational problems, and performs tightly controlled platform administration. This is not a normal school role.

## Product pillars

1. **Intelligent Tutor:** Conversational, curriculum-aware support; explanations; guided questioning; practice; document-grounded study; age-appropriate responses.
2. **Learning Workspace:** Subjects, materials, assignments, quizzes, exams, deadlines, study plans, revision, and learner progress.
3. **Teacher Copilot:** Lesson planning, question generation, rubrics, feedback drafts, differentiation suggestions, classroom learning-resource creation.
4. **Mastery & Learning Intelligence:** Topic/strand mastery, misconceptions, learning gaps, progress trends, evidence-based recommendations.
5. **Suku360 Integration:** Roster/context sync from Suku360, and approved learning evidence/mastery summaries back to Suku360 — without duplicating institutional authority.

## Product principles

- **Tenant isolation is foundational.** No feature ships if it can expose one school's data to another.
- **Human approval for high-impact AI.** AI may draft, suggest, summarize, or flag; teachers approve grades, feedback, and anything consequential.
- **One source of truth.** Nyansa's learning evidence and mastery views derive from operational records; official institutional records remain Suku360's authority, not Nyansa's to duplicate.
- **Auditability over convenience.** Changes to grades, mastery evidence, and approvals must be attributable.
- **Incremental delivery.** Each phase must be deployable, testable, and useful without depending on unfinished later modules.
- **Boundary discipline.** New features map to one of the five pillars above; institutional-operations scope (admissions, fees, payroll, inventory, official attendance/report authority) does not get built here — see [`AGENTS.md`](../AGENTS.md).

## Initial success measures

- A teacher can create a subject, assessment, and grade entries without Django admin.
- Automated isolation tests show that users cannot read or mutate another school's records.
- A student can get a tutored explanation, practice, and document-grounded answers grounded in approved material.
- A teacher can generate a lesson plan, quiz, or feedback draft and revise it before publishing.
- Mastery/learning-gap views state their evidence and period, and never silently alter official grades.
- Every grade or mastery-affecting change has an audit trail.

## Explicit non-goals

- Owning official school admissions and enrolment administration.
- Owning school fee structures, official student ledgers, payment reconciliation, and receipts.
- Owning official attendance authority or official term-report/report-card publication.
- Owning staff HR/payroll, inventory, transport, hostel, or library administration.
- Owning school-wide parent relationship master records or official intervention case management.
- Allowing AI to publish final grades, disciplinary decisions, or financial adjustments autonomously.
- Native mobile applications; the target is a responsive, installable web experience.
