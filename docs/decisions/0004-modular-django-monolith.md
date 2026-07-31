# ADR 0004: Modular Django monolith

- Status: Accepted
- Date: 2026-07-31
- Owner: Project maintainer
- Related requirements: QLT-002, QLT-003

## Context

The roadmap adds several domains, but the project is currently a compact Django application maintained as one codebase. Premature service separation would add deployment, consistency, and debugging costs.

## Decision

Continue as a modular Django monolith. Establish explicit app and service-layer boundaries while sharing one transactional PostgreSQL database. Use background workers for slow or retryable work such as bulk PDFs, AI calls, notifications, imports, and payment reconciliation.

Extract an independent service only when measured scale, security isolation, deployment cadence, or failure containment provides a concrete benefit.

## Consequences

- Cross-domain transactions remain straightforward.
- One test and deployment pipeline covers the product.
- Module ownership and service boundaries must be enforced through conventions and reviews rather than network boundaries.
- Background processing becomes a required production component before later roadmap phases.

## Alternatives considered

- **Microservices immediately:** Adds operational burden and distributed consistency problems without current scale evidence.
- **Keep all logic in existing views:** Avoids new files temporarily but makes authorization, testing, and reuse unsafe as complexity grows.
