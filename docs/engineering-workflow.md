# Engineering Workflow

## Before implementation

1. Reference one or more requirement IDs from `product-requirements.md`.
2. Confirm the affected tenant boundary and user roles.
3. Record a new architecture decision when the change is difficult to reverse or affects multiple modules.
4. Define acceptance tests, including denied cross-school cases.
5. Plan data migration and rollback before changing persistent models.

## Branch and review scope

Prefer small, dependency-ordered changes. A typical feature pull request should contain one coherent vertical slice: model and migration, service logic, authorization, interface, tests, and documentation. Avoid combining unrelated formatting or refactoring with tenancy or finance changes.

## Coding conventions

- Keep HTTP coordination in views and business rules in domain services.
- Pass `actor` and `school` explicitly to consequential service functions.
- Use `transaction.atomic()` for multi-record state changes.
- Use named choices or enums for workflow states; validate transitions centrally.
- Use decimal types for money and define currency explicitly.
- Store timezone-aware timestamps; present them in the school's timezone.
- Derive totals and percentages from authoritative records unless a documented snapshot is required.
- Place external providers behind adapters with deterministic fakes for tests.
- Never place provider calls directly inside model `save()` methods or signals.

## Test layers

### Unit tests

Cover calculations, state transitions, validation, provider normalization, and role capability rules.

### Service tests

Cover transactions, audit events, idempotency, and cross-school relationship rejection.

### Request tests

Cover authentication, active membership, assigned-resource restrictions, form choice scoping, file downloads, exports, and safe not-found behavior.

### Workflow tests

Cover teacher grade import, lesson review, attendance correction, report publication, guardian access, and payment callbacks from beginning to end.

### Regression tests

Capture existing quiz, assignment, grading, lesson-note, transcript, and AI-assisted workflows before changing their data relationships.

## Migration checklist

- Back up the database and media.
- Measure null, duplicate, and orphaned records affected by the migration.
- Add schema in an expand/backfill/contract sequence.
- Make data migrations deterministic and safe to rerun where possible.
- Test forwards and backwards migration on a copy of representative data.
- Verify counts and key totals before and after migration.
- Avoid long locks when deploying against production PostgreSQL.
- Do not modify the checked-in SQLite database merely to generate migrations.

## Pull request checklist

- [ ] Requirement IDs and acceptance criteria are linked.
- [ ] School ownership is explicit for every new record.
- [ ] Role and assignment-level authorization are tested.
- [ ] Cross-school negative tests are included.
- [ ] Consequential changes create audit events.
- [ ] Background jobs are tenant-aware, retry-safe, and idempotent.
- [ ] User uploads and exports are validated and authorized.
- [ ] AI output has a human approval path where required.
- [ ] Migrations and rollback considerations are documented.
- [ ] User-facing mobile, accessibility, empty, error, and loading states are handled.
- [ ] Documentation and architecture decisions are updated.

## Release checklist

- Run the full automated test suite against the supported database.
- Apply migrations to staging and verify record counts.
- Test tenant isolation using two seeded schools.
- Exercise critical workflows with external providers in sandbox mode.
- Verify background workers, scheduled jobs, storage, email, and monitoring.
- Confirm backup completion and restoration instructions.
- Publish release notes with migration and configuration changes.
- Monitor errors, queue depth, notification failures, and payment exceptions after deployment.

## Local setup baseline

The repository includes pinned direct dependencies in `requirements.txt` and a safe configuration template in `.env.example`. Dependency upgrades should be reviewed deliberately, tested in a clean environment, and recorded in release notes when they affect runtime behavior.
