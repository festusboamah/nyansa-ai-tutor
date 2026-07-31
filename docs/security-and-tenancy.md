# Security and Data Isolation

Multi-tenancy changes every authorization assumption in Nyansa. A correct role check is insufficient if the requested object belongs to a different school.

## Non-negotiable invariants

1. Every school-owned object resolves to one school.
2. Every school request has an authenticated user, active membership, active school context, and allowed capability.
3. Object lookup includes school scope before returning either data or an existence signal.
4. Exports, search, autocomplete, background jobs, file downloads, and APIs follow the same isolation rules as HTML views.
5. Consequential changes are audited.

## Authorization model

Use role-based capabilities scoped to a `SchoolMembership`. Avoid scattered checks such as `if user.role == "TEACHER"`. Centralize capabilities such as:

- `school.manage_members`
- `academics.manage_calendar`
- `grades.enter`
- `grades.publish`
- `lessons.submit`
- `lessons.approve`
- `attendance.mark`
- `reports.approve`
- `finance.manage`
- `communications.send`

Assignment-level checks remain necessary. A teacher with `grades.enter` can act only on assigned subject offerings unless granted broader authority.

## Tenant query rules

- Require an explicit `school` argument in school-owned services and query helpers.
- Scope the first database lookup; do not fetch by ID and check ownership afterward.
- Avoid unscoped default managers in views, forms, serializers, tasks, and admin actions.
- Filter form choice fields by active school and actor permissions.
- Include the school in cache keys, filenames, job payloads, and uniqueness constraints.
- Reject cross-school foreign keys even when each referenced object exists independently.
- Do not trust a hidden `school_id` submitted by a browser; derive school from verified context.

## Required negative test matrix

For each sensitive resource, test that a user from School A cannot:

- list School B records;
- retrieve a known School B identifier;
- create a School A record referencing School B data;
- update or delete a School B record;
- download a School B file or generated PDF;
- discover School B data through search, counts, validation errors, exports, or background-job results;
- gain access by changing a URL slug, form field, session value, or request parameter.

Run these checks for administrators as well as teachers, students, and guardians. A School Admin is not a platform superuser.

## Sensitive data

Nyansa will process children's academic records, attendance, contact details, and family financial information. Apply data minimization and collect only what supports a defined school workflow.

- Store secrets only in environment-backed secret management.
- Encrypt transport with HTTPS and use secure, HTTP-only cookies in production.
- Protect school stamps, signatures, report cards, receipts, and uploaded student work with private storage and authorized download views.
- Avoid sensitive details in URLs, logs, analytics events, SMS bodies, and exception traces.
- Redact provider credentials and payment payloads from logs.
- Define retention and deletion processes before onboarding production schools.
- Document consent and legal responsibilities with qualified Ghanaian privacy counsel before production deployment.

## AI safety and governance

- AI output is untrusted input: validate its structure and escape it before rendering.
- Teachers approve final assessment judgments and lesson content.
- Authorized staff approve official reports and externally shared narratives.
- Prompts should minimize personal data and use internal identifiers where possible.
- Record model/provider, workflow type, timestamp, and human decision for consequential AI suggestions.
- Provide a non-AI path when the provider is unavailable.
- Never use AI to autonomously alter payment records, attendance, access permissions, promotion status, or published grades.

## File and spreadsheet safety

- Validate extension, MIME type, size, and content before processing uploads.
- Store uploads outside directly executable/static paths.
- Treat spreadsheet formulas as untrusted and avoid formula execution during import.
- Escape exported cells beginning with formula-control characters when user content may be included.
- Stage imported grades and show a validation preview before committing.
- Scan or quarantine uploaded files when the deployment environment supports it.

## Payment security

- Verify callback signatures using provider documentation and secrets.
- Enforce idempotency using provider transaction/event identifiers.
- Reconcile server-to-server; do not trust client redirects or screenshots.
- Store normalized states while retaining limited provider references for investigation.
- Apply payments inside database transactions and prevent double allocation.
- Require explicit, audited adjustments and refunds.

## Operational controls before production

- PostgreSQL backup schedule plus a successful restoration drill.
- Separate development, staging, and production credentials and databases.
- Restricted Django admin access with multi-factor authentication at the identity/provider layer where available.
- Dependency and security update process.
- Central error monitoring without leaking student data.
- Incident response contacts and a tenant notification procedure.
- Rate limits for login, password reset, invitations, exports, AI requests, and message sending.
