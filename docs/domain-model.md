# Domain Model

This document defines the proposed conceptual model. Field names may evolve during implementation, but ownership and lifecycle rules should remain stable unless recorded in an architecture decision.

## Core relationships

```text
School
├── SchoolMembership ── User
├── AcademicYear
│   ├── Term
│   │   ├── SchoolHoliday
│   │   ├── AttendanceSession ── AttendanceRecord ── Student
│   │   └── TermReport ── TermSubjectResult
│   └── SchoolClass ── ClassEnrollment ── Student
│       └── SubjectOffering ── Subject
│           ├── TeacherAssignment ── Teacher
│           ├── Assessment ── GradeEntry
│           └── LessonPlan ── LessonPlanReview
├── GuardianLink ── Guardian + Student
├── FeeStructure ── Charge ── StudentLedger
│   └── Payment ── Receipt
└── Message ── DeliveryAttempt
```

## Identity and tenancy

### School

The tenant root. Expected fields include name, slug, contact details, address, timezone, logo, stamp, report-card settings, status, and timestamps. School assets must use private storage when they include signatures or stamps.

### User

Global authentication identity. The existing `role` field becomes transitional because a person may have different roles across schools. Authentication details belong here; school permissions do not.

### SchoolMembership

Links a user to a school with role, status, invitation metadata, staff/student identifier, and dates. Uniqueness is normally `(school, user, role)` unless product research establishes that one active membership per user and school is sufficient.

### GuardianLink

Links a guardian membership to a student membership. Include relationship type, access status, primary-contact preference, and authorization metadata. Access is never inferred from shared surname, phone number, or email address.

## Academic organization

### AcademicYear

A school-owned named period such as `2026/2027`. It has start/end dates and lifecycle status. At most one year should be marked current per school.

### Term

Belongs to an academic year and has a name, order, start/end dates, and status. Terms must not overlap within the same school unless an explicit future requirement permits it.

### SchoolClass

A cohort for an academic year, such as Basic 5A or JHS 2. It may have a class teacher and capacity. Historical classes are retained rather than overwritten during rollover.

### ClassEnrollment

Places a student in a class for an academic year. It stores enrollment state and effective dates. A student should not have conflicting active primary-class enrollments for the same academic year.

### Subject

The catalog identity for a subject within a school. Existing global `Subject` records will be assigned to a school during migration.

### SubjectOffering

Represents a subject taught to a class for an academic period. Assessments, lesson plans, teacher assignments, and results attach here rather than directly to an undifferentiated subject.

## Assessment and gradebook

### AssessmentCategory

A school- or offering-level category with name, code, weight, order, and active status. Configuration is versioned or frozen once results are published.

### Assessment

Generalized graded activity. Existing `Quiz` and `Assignment` objects may initially reference an assessment record or expose a common adapter rather than being replaced immediately.

### GradeEntry

One student's score for an assessment, with maximum score, source (`ONLINE`, `MANUAL`, `IMPORT`), publication state, and audit metadata. Unique constraints prevent duplicate authoritative entries for the same student and assessment.

### GradeImport

Tracks an uploaded workbook, parsing state, validation report, actor, timestamps, and resulting batch. Uploading does not publish grades. Parsed rows should be staged until the teacher confirms a valid preview.

## Lessons

### LessonPlan

The evolution of `LessonNote`. It belongs to a subject offering and includes week/topic information, generated or edited content, workflow status, author, current version, and approval metadata.

### LessonPlanReview

Append-oriented workflow history containing action, reviewer, comment, timestamp, and version. Returning a plan requires a comment. Approved content is frozen as a versioned record.

## Attendance

### SchoolHoliday

A school-owned closure date or inclusive date range associated with a term. Reasons are retained for audit and calendar display.

### AttendanceSession

Represents attendance taken for a class and school date. It records status, submitted actor/time, and optional finalization state. One regular session per class and date avoids incomplete duplicate registers.

### AttendanceRecord

One status per enrolled student and session: Present, Absent, or Excused. Corrections record actor, time, and reason.

Days school was open is derived from term dates, weekend policy, and closures. It is not stored on each student report.

## Reporting

### TermReport

The official student-and-term snapshot. It records calculated totals, attendance summary, conduct, remarks, position where enabled, promotion outcome, approval state, and publication/version metadata.

### TermSubjectResult

A frozen subject result within a term report, including category breakdown, final score, grade, position where enabled, and teacher remark. Snapshotting protects historical reports when later configuration changes.

Generated PDFs are artifacts of a report version, not the authoritative data record.

## Finance

### FeeStructure and FeeItem

Define charges for an academic period and their applicability. Changes after assignment create a new version or explicit adjustment rather than rewriting posted student charges.

### Charge

An immutable debit on a student's ledger, with due date, source, amount, currency, and status.

### Payment

A recorded credit with channel, normalized state, provider reference, payer details, amount, and reconciliation metadata. Provider events must be idempotent.

### Adjustment and Refund

Explicit ledger entries that correct or reverse amounts. Financial history is retained; posted entries are not silently edited or deleted.

### Receipt

A stable numbered document linked to a successful payment allocation. Regeneration must preserve its number and financial facts.

## Communication and auditing

### Message

A tenant-owned notification intent with template, audience, language, safe rendered content, schedule, and business-event reference.

### DeliveryAttempt

One provider attempt with channel, normalized state, provider ID, timestamps, and sanitized response metadata.

### AuditEvent

An append-oriented record containing school, actor, action, object type/ID, timestamp, request correlation ID, and a safe summary of changes. Do not store secrets, full payment payloads, or unnecessary sensitive content in the audit log.

## Deletion and retention rules

- Schools, users, memberships, and operational configuration may be deactivated.
- Published grades, attendance corrections, report versions, ledger entries, payment events, receipts, approvals, and audit events should not be hard-deleted through ordinary workflows.
- Uploaded files follow documented retention rules and authorization checks.
- Tenant offboarding requires an export, retention decision, and controlled deletion process rather than ad hoc cascading deletes.
