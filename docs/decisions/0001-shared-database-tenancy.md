# ADR 0001: Shared-database tenant model

- Status: Accepted
- Date: 2026-07-31
- Owner: Project maintainer
- Related requirements: TEN-001, TEN-002, TEN-003, TEN-004

## Context

Nyansa must support multiple independent schools without duplicating deployments or academic logic. The current database has no school ownership boundary.

## Decision

Use one PostgreSQL database with tenant-scoped rows. `School` is the tenant root, and every school-owned record resolves to one school directly or through an unambiguous relationship. High-value and frequently queried records may carry a direct `school_id` even when ownership can also be inferred.

Application services require explicit school context and filter before object retrieval. Database constraints, indexes, and automated negative tests reinforce isolation. PostgreSQL row-level security may be evaluated later as defense in depth.

## Consequences

- One deployment and migration stream can serve multiple schools.
- Every feature, export, search, task, cache key, and file path must preserve school scope.
- Data backfill is required before school ownership can become non-null.
- Application mistakes remain a potential isolation risk, so centralized query patterns and negative tests are mandatory.

## Alternatives considered

- **Database per school:** Strong isolation but excessive operational and migration overhead for the current team.
- **Schema per school:** Adds deployment complexity without eliminating application-level tenant context.
- **Separate deployment per school:** Simple conceptually but costly to maintain and inconsistent with a shared product.
