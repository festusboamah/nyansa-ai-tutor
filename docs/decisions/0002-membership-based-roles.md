# ADR 0002: Membership-based school roles

- Status: Accepted
- Date: 2026-07-31
- Owner: Project maintainer
- Related requirements: IDN-001, IDN-002, IDN-003, IDN-004

## Context

The current `User.role` field assigns one global Student or Teacher role. Multi-school use requires roles to be scoped to a school, and the roadmap adds School Admin and Parent/Guardian.

## Decision

Keep `User` as the global authentication identity and introduce `SchoolMembership` for school, role, status, and school-specific identifiers. School permissions derive from an active membership. Platform operator privileges remain separate from school memberships.

The existing `User.role` field remains during a compatibility period, is backfilled into memberships for the designated legacy school, and is removed only after all application checks use memberships.

## Consequences

- A person can participate in more than one school without duplicate login identities.
- Role checks must include active school context.
- Forms, URLs, templates, and tests must migrate away from `user.is_teacher()` and `user.is_student()` gradually.
- Invitation, suspension, and membership lifecycle behavior become explicit product workflows.

## Alternatives considered

- **Add more global roles to `User`:** Does not support different roles across schools and encourages cross-tenant mistakes.
- **One user account per school:** Creates duplicate identities and poor guardian/teacher experiences.
- **Django groups alone:** Useful for capability mapping but insufficient as the tenant membership record.
