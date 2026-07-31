# Delivery Roadmap

The phases are ordered by dependency and risk. Dates should be assigned only after Phase 0 discovery establishes team capacity, deployment constraints, and pilot-school needs.

## Phase 0 — Baseline and decision lock

**Goal:** Make the current system reproducible and remove uncertainty before changing ownership boundaries.

Deliverables:

- Dependency manifest and repeatable local setup.
- Baseline automated tests for existing grading and core user journeys.
- Inventory and backup of the current SQLite data and uploaded media.
- Decisions for membership roles, school selection, class terminology, PostgreSQL hosting, background jobs, file storage, SMS provider, and payment provider.
- Pilot-school workflow interviews and sample report card, grade sheet, receipt, and attendance register.

Exit criteria:

- Existing behavior can be tested before migrations.
- Every unresolved high-impact decision has an owner and target date.
- A restoreable backup exists.

Current status: the dependency manifest, environment template, initial regression suite, baseline audit command, local backup tooling, and first four ADRs are complete. Provider, storage, academic naming, and PostgreSQL decisions remain intentionally open until their implementation phases or pilot-school validation.

## Phase 1 — Multi-tenant foundation

**Goal:** Establish safe school ownership and school administration.

Deliverables:

- `School`, `SchoolMembership`, invitation, branding, and active-school context.
- School Admin and Parent/Guardian membership roles.
- Academic year, term, class, class enrollment, subject offering, and teacher assignment.
- Legacy-school data migration and PostgreSQL-ready configuration.
- Tenant-scoped services, authorization capabilities, and isolation test suite.
- School administrator dashboard shell.

Exit criteria:

- All existing academic records belong to a school.
- School A cannot access School B through any tested path.
- Existing student and teacher workflows continue to operate for the migrated school.

## Phase 2 — Generalized gradebook and offline entry

**Goal:** Create one gradebook for online and offline assessment evidence.

Deliverables:

- Configurable assessment categories and weights.
- Common grade entries sourced from quizzes, assignments, manual entry, or import.
- Roster-based `.xlsx` template download.
- Validated upload, preview, error correction, confirmation, and audit trail.
- Grade review and publication workflow.

Exit criteria:

- A teacher can produce an official grade for a student without a student login.
- Invalid workbooks cannot partially publish results.
- Existing weighted grading results have regression coverage.

## Phase 3 — Lesson-plan approval

**Goal:** Add accountable academic oversight to AI lesson-note generation.

Deliverables:

- Draft, Pending Review, Sent Back, and Approved states.
- Review queue, comments, notifications, and version history.
- Approved-plan locking and controlled revision.
- School/class/subject context on lesson plans.

Exit criteria:

- Permission and transition tests cover every workflow edge.
- Approved content cannot be silently changed.

## Phase 4 — Attendance and school calendar

**Goal:** Provide fast daily attendance and accurate instructional-day calculations.

Deliverables:

- Term dates, weekend policy, holidays, and closures.
- Mobile-first class quick-mark interface.
- Attendance correction and audit workflow.
- Student, class, and school summaries.

Exit criteria:

- A teacher can mark a normal class quickly on a phone.
- Days-open calculations update deterministically when the calendar changes.

## Phase 5 — Term reports

**Goal:** Produce official, school-branded reports from approved source records.

Deliverables:

- Term-report review, approval, publication, and revision workflow.
- Subject results, totals, position policy, attendance, conduct, remarks, and promotion outcome.
- Prior-term comparison and optional AI-drafted narrative.
- GES/WAEC-aligned PDF template and bulk generation/printing.

Exit criteria:

- A whole class can be generated without request timeouts.
- Published reports remain stable after later configuration changes.
- Totals match documented calculations and source records.

## Phase 6 — Guardian portal and communications

**Goal:** Give families secure, timely access through channels that work locally.

Deliverables:

- Verified guardian-student links and responsive portal.
- Message templates, preferences, queue, retries, delivery history, and opt-out handling where applicable.
- Email plus one Ghana-focused SMS adapter.
- Report, attendance, event, and balance notifications.

Exit criteria:

- Guardians see only linked children.
- Failed messages can be retried without duplicate business events.
- Message content follows the privacy policy.

## Phase 7 — Fees and Mobile Money

**Goal:** Provide a trustworthy student ledger and locally relevant payment path.

Deliverables:

- Fee structures, charges, balances, adjustments, payments, allocations, and receipts.
- One payment provider integration supporting relevant Mobile Money channels.
- Authenticated callbacks, idempotency, reconciliation, and exception queue.
- Receipt and reminder notifications.

Exit criteria:

- Ledger totals reconcile for success, failure, duplicate callback, and reversal scenarios.
- No browser-only signal can mark a payment successful.
- Every financial mutation is attributable.

## Phase 8 — Analytics and intervention

**Goal:** Turn operational data into actionable, explainable insight.

Deliverables:

- Teacher trends for assigned classes and subjects.
- School-wide academic and attendance dashboards.
- Configurable early-warning signals.
- AI-assisted narrative summaries grounded in visible metrics.

Exit criteria:

- Metrics state their period and source and agree with authoritative records.
- Authorization and privacy tests cover every drill-down.

## Features held for later evaluation

- Multilingual message-template library.
- QR-based attendance or ID cards.
- Admissions pipeline and applicant portal.
- Inventory, library, transport, hostel, payroll, and full accounting.
- Native mobile applications.
- Cross-school benchmarking using privacy-preserving aggregates.

These are not rejected; they are deliberately sequenced after the core academic, administrative, and financial records are reliable.

## Definition of done for every phase

- Requirements and architecture decisions are updated.
- Data ownership and authorization are explicit.
- Migrations are reversible where technically reasonable and rehearsed against a backup copy.
- Unit, workflow, tenant-isolation, and regression tests pass.
- Accessibility and responsive behavior are checked for user-facing workflows.
- Logging, error behavior, and operational recovery are documented.
- No secrets or real student data appear in fixtures, logs, screenshots, or source control.
- User documentation and release notes are complete.
