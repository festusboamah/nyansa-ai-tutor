# Product Vision

## Vision

Nyansa will become a Ghana-focused school operating system built around an AI-assisted academic engine. It will connect teaching, assessment, attendance, reporting, parent communication, and school finance without removing professional judgment from teachers and administrators.

Nyansa means "wisdom" in Twi. The product promise is therefore not automation at any cost: **technology should sharpen human judgment, not replace it.**

## Product evolution

The current application already provides subjects, enrollments, learning materials, quizzes, assignments, AI-assisted grading, lesson-note generation, student reports, and transcripts. The next product stage adds the administrative structure needed by real schools.

The governing design principle is:

> **Wrap, don't replace.** Extend the existing academic capabilities with school, class, term, finance, communication, and reporting context. Avoid parallel implementations of grading or content workflows.

## Primary users

### Student

Learns from materials, completes online assessments where connectivity permits, receives feedback, and reviews academic progress. A student's official record must not depend on the student having a personal device or platform login.

### Teacher

Manages assigned classes and subjects, creates learning content and assessments, enters offline results, marks attendance, submits lesson plans, reviews AI suggestions, and prepares student remarks.

### School administrator

Configures the school and academic calendar, manages people and classes, approves lesson plans and reports, oversees fees and communication, and views school-wide performance. This role is limited to its school.

### Parent or guardian

Views linked children's approved results, attendance, fee balances, receipts, and school notices. A guardian account is separate from the student's account and may be linked to multiple children.

### Platform operator

Supports the shared service, manages tenants, investigates operational problems, and performs tightly controlled platform administration. This is not a normal school role.

## Product pillars

1. **Academic intelligence:** AI-assisted creation, feedback, analysis, and intervention, with human approval for consequential decisions.
2. **School operations:** Admissions, student records, classes, attendance, access control, and academic progression.
3. **Parent connection:** Accessible, timely communication through the portal, email, and Ghana-relevant SMS channels.
4. **Financial clarity:** Fee structures, invoices, payments, balances, receipts, and Mobile Money reconciliation.
5. **Contextual fit:** GES/WAEC-aligned outputs, local payment and messaging providers, multilingual communication, and offline-tolerant workflows.

## Product principles

- **Tenant isolation is foundational.** No feature ships if it can expose one school's data to another.
- **Human approval for high-impact AI.** AI may draft, suggest, summarize, or flag; authorized people publish grades, remarks, and official reports.
- **Offline participation is a first-class path.** Teachers can enter or import records for students who never sign in.
- **One source of truth.** Reports and dashboards derive from operational records; they do not maintain competing grade or attendance calculations.
- **Auditability over convenience.** Changes to grades, payments, attendance, permissions, and approvals must be attributable.
- **Accessible communication.** Mobile-first layouts, printable documents, and local-language messages are product requirements rather than polish.
- **Incremental delivery.** Each phase must be deployable, testable, and useful without depending on unfinished later modules.

## Initial success measures

- A school can configure an academic year, classes, subjects, teachers, and students without Django admin.
- Automated isolation tests show that users cannot read or mutate another school's records.
- A teacher can complete daily attendance for a class in under two minutes on a phone.
- A teacher can import a class grade sheet, review validation errors, and publish approved results.
- A school can bulk-generate consistent report cards from approved records.
- A parent can see only linked children and receive an accurate balance or report notification.
- Every posted payment and official grade change has an audit trail.

## Explicit non-goals for the first release

- Replacing a full accounting or payroll system.
- Building a general-purpose learning marketplace.
- Allowing AI to publish final grades, disciplinary decisions, or financial adjustments autonomously.
- Supporting arbitrary custom workflows before the core Ghanaian school workflow is reliable.
- Native mobile applications; the initial target is a responsive, installable web experience.
