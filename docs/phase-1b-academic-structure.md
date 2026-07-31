# Phase 1B: Academic Structure

This slice introduces school-scoped academic years, ordered terms, annual classes, class enrollment, subject offerings, and teacher assignments. Database constraints prevent duplicate current years, terms, class names, enrollments, offerings, and teacher assignments. Model validation rejects cross-school combinations before they can become academic records.

The structures are additive: existing enrollments and assessments remain operational while later slices connect them to subject offerings and class rosters.

## Phase 1C administration

School administrators now have a tenant-scoped dashboard and creation workflows for academic years, terms, classes, subject offerings, and teacher assignments. Every relationship field is filtered to the active school, and non-administrator memberships are denied access.

## Phase 1D membership management

The administrator workspace includes a school-scoped people directory, email invitations for all four membership roles, secure hashed invitation tokens, acceptance by matching authenticated email, and activation/suspension controls. Administrators cannot alter another school's memberships or suspend their own active administrator membership.
