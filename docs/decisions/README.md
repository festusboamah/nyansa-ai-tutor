# Architecture Decision Records

Architecture Decision Records (ADRs) capture decisions that are expensive to reverse, affect multiple modules, or establish a project-wide convention.

## Status values

- **Proposed:** Under review and not yet authoritative.
- **Accepted:** The implementation must follow the decision.
- **Superseded:** Replaced by a later ADR, which must be linked.
- **Rejected:** Considered but intentionally not selected.

## Naming

Use `NNNN-short-title.md`, beginning with `0001`. Never renumber accepted records.

## Template

```markdown
# ADR NNNN: Decision title

- Status: Proposed
- Date: YYYY-MM-DD
- Owners: Names or roles
- Related requirements: TEN-001, ...

## Context

What problem or constraint requires a durable decision?

## Decision

What will the project do?

## Consequences

What becomes easier, harder, required, or intentionally unsupported?

## Alternatives considered

What credible alternatives were evaluated and why were they not selected?
```

## Initial decisions to record before Phase 1

1. [ADR 0001: Shared-database tenant model](0001-shared-database-tenancy.md) - Accepted.
2. [ADR 0002: Membership-based school roles](0002-membership-based-roles.md) - Accepted.
3. [ADR 0003: Explicit active-school context](0003-explicit-active-school-context.md) - Proposed pending URL and branding validation.
4. [ADR 0004: Modular Django monolith](0004-modular-django-monolith.md) - Accepted.

Still required before the affected implementation phase:

- Academic structure and Ghanaian naming conventions.
- PostgreSQL hosting and migration approach.
- Background-job framework and broker.
- Private file-storage provider and access pattern.
- Gradebook integration strategy for existing Quiz and Assignment models.
- SMS and payment provider selection after sandbox evaluation.
