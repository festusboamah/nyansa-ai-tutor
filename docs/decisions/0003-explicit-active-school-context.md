# ADR 0003: Explicit active-school context

- Status: Proposed
- Date: 2026-07-31
- Owner: Project maintainer
- Related requirements: TEN-002, TEN-003, TEN-004

## Context

Requests need a deterministic school context. Users may eventually belong to multiple schools, and a school slug or subdomain cannot by itself grant access.

## Decision

Resolve the active school from a verified membership selection stored in the authenticated session. School-branded URLs may include the school slug for clarity, but the session membership and requested object ownership remain authoritative.

Views pass the resolved school explicitly into domain services. Missing, inactive, or mismatched context is denied by default. Users with multiple memberships receive a school switcher; users with one active membership may be selected automatically.

This ADR remains proposed until URL strategy and pilot-school branding requirements are confirmed.

## Consequences

- Local development does not require wildcard DNS.
- The user experience supports multi-school teachers and guardians.
- Session switching must be protected against arbitrary school identifiers.
- Background jobs cannot rely on request state and must carry a verified school identifier explicitly.

## Alternatives considered

- **Subdomain-only context:** Useful for branding but not authorization and harder for local development.
- **School ID in every URL:** Explicit but noisy and vulnerable if code treats it as authorization.
- **One school fixed at login:** Simple but blocks convenient multi-school membership.
