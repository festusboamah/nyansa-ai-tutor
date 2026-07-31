# Product Requirements

Requirement IDs are stable references for implementation tickets, tests, and release notes. Priority meanings: **P0** is required for safe operation, **P1** is required for the first complete school release, and **P2** is a valuable extension.

## Tenancy and identity

- **TEN-001 (P0):** Every school-owned record must resolve to exactly one `School` tenant, directly or through an unambiguous parent relationship.
- **TEN-002 (P0):** Every authenticated school request must be evaluated against an active school membership and role.
- **TEN-003 (P0):** School-scoped query APIs must deny access by default when school context is absent.
- **TEN-004 (P0):** Cross-school create, read, update, delete, export, search, and identifier-guessing attempts must be covered by automated tests.
- **IDN-001 (P1):** A user may hold a role through a school membership rather than through one global role field.
- **IDN-002 (P1):** Supported school roles are School Admin, Teacher, Student, and Parent/Guardian.
- **IDN-003 (P1):** Platform operator privileges remain separate from school roles.
- **IDN-004 (P1):** Administrators can invite, activate, suspend, and assign members without using Django admin.

## Academic structure

- **ACA-001 (P0):** Each school manages academic years and dated terms.
- **ACA-002 (P1):** Each school manages classes/cohorts and assigns students for a specific academic year.
- **ACA-003 (P1):** Subjects are offered to classes and assigned to one or more teachers.
- **ACA-004 (P1):** Existing quizzes, assignments, materials, enrollments, submissions, and lesson notes must be associated with the correct school through their academic relationships.
- **ACA-005 (P1):** Academic-year rollover promotes, repeats, graduates, or transfers students while preserving historical records.

## Gradebook

- **GRD-001 (P1):** A school can configure assessment categories and weights, with validation that active weights total 100 percent.
- **GRD-002 (P1):** Categories support class assignments, tests, projects, group work, quizzes, and examinations without hard-coding one national scheme.
- **GRD-003 (P1):** Online quiz and assignment results feed the same gradebook used for manual entries.
- **GRD-004 (P1):** Teachers can download an `.xlsx` roster template for a selected class, subject, and term.
- **GRD-005 (P1):** Uploaded grade sheets are validated before import and provide row-level errors without partially publishing invalid data.
- **GRD-006 (P0):** Grade publication and later changes are permission-controlled and audited.
- **GRD-007 (P1):** Official grades can exist for a student who has never logged into Nyansa.

## Lesson-plan workflow

- **LES-001 (P1):** Lesson plans move through Draft, Pending Review, Sent Back, and Approved states.
- **LES-002 (P1):** Only the author can submit or revise a returned plan; only an authorized reviewer can approve or return it.
- **LES-003 (P1):** Review comments, actor, and timestamp are retained as workflow history.
- **LES-004 (P0):** Approved plans are immutable; corrections require a versioned revision or explicit reopening action.
- **LES-005 (P1):** AI-generated lesson content remains editable before submission.

## Attendance and calendar

- **ATT-001 (P1):** Terms have start and end dates, and schools maintain holidays or closures.
- **ATT-002 (P1):** The system derives instructional days from term dates minus weekends and school closures.
- **ATT-003 (P1):** Teachers can quick-mark Present, Absent, or Excused for an entire class and date.
- **ATT-004 (P1):** Attendance corrections are authorized and audited.
- **ATT-005 (P1):** Attendance percentages use the derived instructional-day count and are not manually typed.

## Term reports

- **RPT-001 (P1):** A term report combines approved subject results, attendance, conduct, teacher remarks, headteacher remarks, and promotion status.
- **RPT-002 (P1):** Overall average and class position use a documented, deterministic calculation.
- **RPT-003 (P1):** Reports can include comparison with the immediately preceding term.
- **RPT-004 (P1):** Schools can generate, download, and print individual or class-bulk PDF report cards.
- **RPT-005 (P1):** Report cards use school branding and support GES/WAEC-aligned layouts.
- **RPT-006 (P0):** Published reports are immutable snapshots; later corrections create a traceable revision.
- **RPT-007 (P1):** AI may draft remarks or summaries, but an authorized human must approve published text.

## Parent portal and communications

- **PAR-001 (P1):** A guardian can access only explicitly linked students.
- **PAR-002 (P1):** One guardian can be linked to multiple students, and a student can have multiple guardians.
- **COM-001 (P1):** The system supports templated email and SMS notifications for reports, balances, meetings, and school events.
- **COM-002 (P1):** Message delivery is asynchronous, retryable, and recorded with provider status.
- **COM-003 (P0):** Sensitive academic or financial details must not be placed in SMS messages beyond the school's configured privacy policy.
- **COM-004 (P2):** Parent messages support English, Twi, Ga, and Ewe templates.
- **COM-005 (P1):** SMS providers are replaceable behind a gateway interface, initially targeting Hubtel or Arkesel.

## Fees and payments

- **FIN-001 (P1):** Administrators configure fee items and assign charges by class, student, or applicable group.
- **FIN-002 (P1):** Each student ledger shows charges, payments, adjustments, refunds, and current balance.
- **FIN-003 (P1):** Payments generate unique, reproducible receipts.
- **FIN-004 (P0):** Payment provider callbacks are authenticated, idempotent, and reconciled before affecting balances.
- **FIN-005 (P1):** Mobile Money integration supports provider-agnostic transaction states such as Pending, Successful, Failed, Reversed, and Unknown.
- **FIN-006 (P0):** Financial records are not hard-deleted through normal product workflows.
- **FIN-007 (P1):** Balance reminders and payment receipts use the communications service.

## Analytics and interventions

- **ANL-001 (P1):** Teachers see trends only for assigned classes and subjects.
- **ANL-002 (P1):** School administrators see school-wide academic and attendance aggregates.
- **ANL-003 (P2):** The system flags configurable risks such as falling grades, repeated absence, or sustained non-submission.
- **ANL-004 (P1):** Every displayed metric states its period and source; analytics do not maintain separate authoritative results.
- **ANL-005 (P2):** AI-generated narratives identify their underlying period and require human review before external sharing.

## Cross-cutting quality requirements

- **QLT-001 (P0):** Responsive workflows support current mobile browsers at common low-to-mid-range phone widths.
- **QLT-002 (P0):** Long operations such as PDF batches, imports, AI calls, and notifications do not block web requests.
- **QLT-003 (P0):** Production uses PostgreSQL, environment-based secrets, secure cookies, HTTPS, and restricted hosts.
- **QLT-004 (P1):** Important workflows provide accessible labels, keyboard navigation, readable contrast, and printable output.
- **QLT-005 (P0):** Backups and restoration are documented and restoration is tested before production launch.
- **QLT-006 (P1):** User-facing timestamps use the school's configured timezone; stored timestamps remain timezone-aware.
