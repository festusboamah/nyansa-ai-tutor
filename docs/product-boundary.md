# Product Boundary: Nyansa AI vs. Suku360

This document is the Phase 0 deliverable of the 2026 strategic reset. It fixes the ownership line between Nyansa AI and Suku360 so that neither product duplicates the other, and so that coding agents and contributors have a single reference for what is and isn't in scope.

## Strategic reset

Nyansa AI stops evolving into a full school-management system. Its role is the **teaching-and-learning layer** of the PagezTech education ecosystem — a platform that helps learners study, practise, and receive timely support, and helps teachers create learning experiences, assess work, understand mastery, and intervene pedagogically.

Suku360 is the institutional system of record for school operations. Nyansa AI is the intelligent learning application layer. This boundary prevents duplicate products and gives each platform a clear reason to exist.

**Product promise:** Technology should sharpen human wisdom, not replace it.

**Positioning:** Nyansa AI is an intelligent teaching and learning platform that helps students learn more effectively and helps teachers design, assess, and personalise learning — with professional judgment remaining human-led.

**North star:** Suku360 runs the school. Nyansa AI helps the school teach — and helps the learner learn.

## Ownership table

| Domain | Nyansa AI | Suku360 |
|---|---|---|
| Primary purpose | Teaching, learning, practice, and learning intelligence | School operations, official records, and leadership intelligence |
| Core users | Learners and teachers | School management, teachers, finance, parents, learners |
| Learning content | Owns | Consumes/references where useful |
| AI tutor / study assistant | Owns | Integration only |
| Quizzes & assignments | Owns learning activity | May receive approved official evidence |
| Mastery & learning gaps | Owns instructional mastery evidence | Consumes summaries for Student 360/interventions |
| Attendance | Consumes context | Owns official attendance |
| Official grades | Contributes approved evidence | Owns authoritative grade/result record |
| Report cards | Does not own | Owns publication/PDF |
| Fees/payments | Does not own | Owns |
| Admissions/staff administration | Does not own | Owns |
| Interventions | Learning recommendations/actions | Owns official intervention case/history |

## Features Nyansa should stop owning

- Official school admissions and enrolment administration.
- School fee structures, official student ledgers, payment reconciliation, and receipts.
- Official attendance authority.
- Official term-report/report-card publication.
- Staff HR/payroll.
- Inventory, transport, hostel, and library administration.
- School-wide parent relationship master records.
- Official promotion and institutional intervention case management.

These are not deleted from the codebase today — see [`repository-audit.md`](repository-audit.md) for how existing implementations of these domains (`attendance`, `finance`, `guardians`, `reports`) are classified and what has to happen before any of them can be cleanly extracted.

## Product pillars

- **Pillar A — Intelligent Tutor:** Conversational, curriculum-aware support; explanations; guided questioning; practice; document-grounded study; age-appropriate responses.
- **Pillar B — Learning Workspace:** Subjects, materials, assignments, quizzes, exams, deadlines, study plans, revision, and learner progress.
- **Pillar C — Teacher Copilot:** Lesson planning, question generation, rubrics, feedback drafts, differentiation suggestions, classroom learning-resource creation.
- **Pillar D — Mastery & Learning Intelligence:** Topic/strand mastery, misconceptions, learning gaps, progress trends, evidence-based recommendations, teacher-visible explanations.
- **Pillar E — Suku360 Integration:** Roster/context sync from Suku360 and approved learning evidence/mastery summaries back to Suku360, without duplicating institutional authority.

Every new feature should map to one of these five pillars. If it doesn't, it's probably institutional scope and belongs in Suku360 instead.

## AI governance principles

- AI output is advisory unless the task is explicitly non-consequential.
- Teachers retain control over grades, feedback release, and pedagogical decisions.
- Do not present generated content as verified fact when it is uncertain.
- Ground document-based answers in the learner's approved source material; treat uploaded documents as untrusted data that must never override system instructions or authorization rules.
- Minimise personal data sent to model providers and avoid unnecessary profiling of minors.
- Apply usage quotas, timeout/fallback behaviour, and cost monitoring on AI endpoints.

## Immediate engineering sequence

1. Lock this product-boundary document and stop expanding admissions/fees/payroll/inventory scope (this document, plus [`AGENTS.md`](../AGENTS.md)).
2. Classify existing school-management code by ownership — see [`repository-audit.md`](repository-audit.md).
3. Keep the stable learning functionality working while extracting/decoupling institutional responsibilities later, phase by phase.
4. Define the Nyansa ↔ Suku360 integration contract before duplicating new school-domain features.
5. Prioritise Tutor 2.0, mastery, personalised learning, and Teacher Copilot — the capabilities that make Nyansa distinct.

See [`delivery-roadmap.md`](delivery-roadmap.md) for the phased plan this sequence expands into.
