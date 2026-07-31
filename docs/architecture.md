# System Architecture

## Current baseline

Nyansa is a Django application organized into `accounts`, `courses`, `quizzes`, and `dashboard` apps. It uses a custom user model, server-rendered templates, SQLite, local media storage, synchronous AI calls, and PDF generation. School, class, term, parent, attendance, and finance domains do not yet exist.

The architecture should evolve incrementally. A modular Django monolith remains appropriate for the next stage: it preserves transactional consistency and keeps operational complexity proportionate to the project. Separate services can be introduced later only where scale or independent failure handling justifies them.

## Target module boundaries

| Module | Responsibility |
|---|---|
| `accounts` | User identity, authentication, profiles, and platform-level access |
| `schools` | Schools, memberships, branding, invitations, and tenant context |
| `academics` | Academic years, terms, classes, subject offerings, teacher assignments, and progression |
| `courses` | Learning materials, self-study documents, and subject learning experiences |
| `assessments` | Assessment definitions, submissions, grade entries, categories, calculations, and publication |
| `lessons` | Lesson plans, AI drafting, review workflow, versions, and PDF output |
| `attendance` | Calendars, closures, daily records, summaries, and corrections |
| `reports` | Term-report snapshots, approvals, comparisons, bulk generation, and exports |
| `guardians` | Guardian-student relationships and parent portal views |
| `communications` | Templates, preferences, queued messages, delivery attempts, email, and SMS adapters |
| `finance` | Fee structures, charges, ledgers, payments, reconciliation, and receipts |
| `analytics` | Read-only aggregates, trends, risk signals, and AI-assisted narratives |
| `audit` | Append-oriented records of consequential user and system actions |

Existing apps should not be renamed merely for cosmetic consistency. Boundaries can be introduced gradually, with compatibility migrations and imports, when a phase actually needs them.

## Request and tenancy flow

1. Django authenticates the user.
2. Tenant middleware or an explicit school selector resolves the active school from the session and URL context.
3. The system verifies an active `SchoolMembership` for that user and school.
4. Views and services receive the active school explicitly.
5. School-scoped managers or service functions filter every query by that school.
6. Object-level authorization verifies both tenant ownership and role capability.
7. Consequential operations execute in a transaction and append an audit event.

Do not rely on subdomains alone for authorization. A subdomain or school slug selects context; membership and object ownership grant access.

## Data ownership strategy

Use a shared PostgreSQL database with tenant-scoped rows. `School` is the root ownership boundary. Prefer a direct `school_id` on high-value and frequently queried records even when school can be inferred through several relationships. This makes constraints, indexes, debugging, and audit queries clearer.

Required safeguards include:

- composite uniqueness scoped by school where names or codes may repeat;
- database indexes beginning with `school_id` for common tenant queries;
- validation preventing cross-school foreign-key combinations;
- service-level query APIs requiring an explicit school;
- negative tests for every sensitive endpoint;
- PostgreSQL row-level security considered later as defense in depth, not as the first or only control.

## Service-layer rule

Views should coordinate HTTP concerns, not contain grade, attendance, report, or payment logic. Put consequential workflows into domain services with explicit inputs and transactional boundaries, for example:

```python
publish_term_report(*, actor, school, report_id)
import_gradebook(*, actor, school, offering_id, term_id, workbook)
record_payment_callback(*, provider, payload, signature)
```

Services must validate tenant ownership and authorization even if the calling view already performed checks.

## Asynchronous work

Introduce a background job system before communication, bulk PDFs, or payment integration. Appropriate jobs include:

- grade-sheet parsing after upload;
- bulk report-card generation;
- outbound email and SMS;
- payment reconciliation;
- AI generation and narrative analysis;
- scheduled reminders and early-warning evaluation.

Jobs must be idempotent, retry-safe, tenant-aware, observable, and unable to publish high-impact AI output without the required approval.

## External integration boundaries

Use internal interfaces so providers can change without rewriting business workflows:

- `SmsGateway` for Hubtel, Arkesel, and a development console adapter;
- `PaymentGateway` for supported Mobile Money/payment aggregators;
- `EmailGateway` for SMTP or a transactional email provider;
- `AiProvider` for generation, grading suggestions, and summaries;
- `DocumentRenderer` for report cards, lesson notes, receipts, and transcripts;
- `FileStorage` for local development and production object storage.

Persist provider request IDs, normalized states, attempts, and sanitized error details. Never treat a browser redirect as proof of payment.

## Deployment direction

### Development

- SQLite may remain temporarily for local compatibility during the first migration branch.
- Use environment variables for secrets and provider configuration.
- Provide console/fake adapters for email, SMS, payments, and AI tests.

### Production

- PostgreSQL database.
- Managed object storage for uploads and generated documents.
- Web process plus background worker and scheduler.
- Redis or another supported job broker if required by the selected queue.
- HTTPS, secure cookies, restricted `ALLOWED_HOSTS`, error monitoring, structured logs, and automated backups.

## Migration strategy

1. Add nullable school relationships and create a designated legacy school.
2. Backfill existing users and records into that school using a reversible data migration.
3. Add membership records corresponding to current Student and Teacher roles.
4. Audit for orphaned or ambiguous records.
5. Make required ownership fields non-null and add tenant-scoped constraints.
6. Replace global-role checks and unscoped queries incrementally.
7. Switch production configuration to PostgreSQL only after migration rehearsal and backup/restore testing.

Never edit or discard the existing SQLite database as part of schema design. Treat it as migration input until its data has been inventoried and backed up.
