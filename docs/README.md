# Nyansa Project Documentation

This directory is the implementation guide for Nyansa's evolution from an AI tutoring platform into a multi-tenant school management system for Ghanaian schools.

## Start here

1. [Product Vision](product-vision.md) — the problem, users, principles, and product boundaries.
2. [Product Requirements](product-requirements.md) — functional requirements and acceptance criteria.
3. [System Architecture](architecture.md) — target components, tenancy approach, and integration boundaries.
4. [Domain Model](domain-model.md) — proposed entities, relationships, ownership, and lifecycle rules.
5. [Security and Data Isolation](security-and-tenancy.md) — non-negotiable authorization and privacy controls.
6. [Delivery Roadmap](delivery-roadmap.md) — dependency-ordered phases, milestones, and definition of done.
7. [Engineering Workflow](engineering-workflow.md) — development, testing, migration, and review conventions.
8. [Architecture Decisions](decisions/README.md) — decisions that require a durable record.
9. [Phase 0 Baseline Audit](baseline-audit.md) — current record counts, integrity observations, and migration implications.
10. [Phase 1A Multi-Tenancy](phase-1a-multitenancy.md) — delivered tenant models, compatibility strategy, and migration rehearsal.
11. [Phase 1B Academic Structure](phase-1b-academic-structure.md) — academic years, terms, classes, offerings, and assignments.

12. [Phase 2A Gradebook Foundation](phase-2a-gradebook-foundation.md) — configurable weights, common assessments, grade sources, and publication-aware results.
13. [Phase 2B Teacher Gradebook](phase-2b-teacher-gradebook.md) — assigned-offering assessment management and atomic roster grade entry.
14. [Phase 2C Spreadsheet Grade Import](phase-2c-spreadsheet-import.md) — protected roster templates, validation previews, atomic confirmation, and import audit records.
15. [Phase 2D Grade Review and Legacy Sync](phase-2d-grade-review-sync.md) — immutable correction history, administrator decisions, and idempotent legacy adapters.
16. [Phase 3 Lesson-Plan Approval](phase-3-lesson-approval.md) — versioned drafts, review decisions, comments, notifications, and approved-content locking.
17. [Phase 4 Attendance and Calendar](phase-4-attendance-calendar.md) — derived instructional days, mobile registers, audited corrections, and summaries.

## Document status

These documents describe the intended target system. They are not evidence that a feature has already been implemented. Each page distinguishes the current baseline from proposed work where relevant.

The source roadmap is `Nyansa Future Roadmap.docx`, prepared in 2026. Product decisions in this directory refine that roadmap without replacing its central principle: **wrap the existing academic engine; do not rebuild it.**

## Shared vocabulary

- **School:** The tenant and primary data-isolation boundary.
- **School membership:** A user's role and status within a school.
- **Academic year:** A school's named instructional year, containing terms.
- **Term:** A dated reporting and attendance period.
- **Class:** A cohort such as Basic 5 or JHS 2 for a particular academic year.
- **Subject offering:** A subject taught to a class in a term or academic year by assigned teachers.
- **Assessment:** Any graded activity, including assignments, tests, projects, group work, quizzes, and examinations.
- **Term report:** The approved snapshot used to produce a student's official report card.
- **School administrator:** A school-scoped operational role; it is distinct from Django's platform superuser.
- **Parent/guardian:** A user linked to one or more students through an explicit relationship.

## Documentation maintenance

Update the relevant document in the same pull request whenever a change affects domain terminology, user-visible behavior, tenancy rules, integrations, or a recorded architecture decision. Requirements should use stable IDs so tests and pull requests can refer to them.
- [Phase 5 term reports](phase-5-term-reports.md)
