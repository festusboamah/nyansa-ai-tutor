# Repository Audit: App Classification

Phase 0 deliverable. Classifies every Django app against the boundary in [`product-boundary.md`](product-boundary.md). Produced by reading each app's models, cross-app imports, and tests — not by assumption. Nothing described here as "extract" or "needs decoupling" has been touched; this is a map for future phases, not a change log.

Shared infrastructure (`schools`: `School`, `SchoolMembership` tenancy) underlies every app below and is out of scope for the boundary question — every retained and extracted app keeps depending on it.

## Retain and strengthen (teaching-learning core)

| App | Purpose | Size | Coupling notes |
|---|---|---|---|
| `academics` | Academic years, terms, classes, enrollments, subject-teacher assignments | ~310 LOC, 6 files | No coupling to the extract-side apps except one cosmetic `/attendance/` URL string in a notification link. Structural backbone for all other apps. |
| `courses` | Subjects, learning materials, Self-Study Hub | ~838 LOC, 12 files | `courses/study_ai.py` calls Claude directly for PDF summarization and document-grounded Q&A. No shed-side coupling. |
| `quizzes` | Quizzes, exams, badges, assignments | ~1021 LOC, 12 files | `ai_quiz_generator.py`, `ai_grading.py`, `assignment_ai.py` — all Claude-based. FK depends on `courses.Subject` only. |
| `gradebook` | Grade schemes, categories, assessments, grade entry with review workflow, spreadsheet import, immutable revisions | ~2360 LOC, 13 files, 829-line test suite | Largest and best-tested app. No coupling to `attendance`/`finance`/`guardians`. **Boundary nuance**: under the new model, Suku360 owns the *authoritative* grade record; Nyansa's gradebook becomes the source of *approved evidence* contributed to it. That redefinition is Phase 6 (Suku360 Integration) work — the entry/review/audit machinery itself is unaffected and stays as-is. |
| `analytics` | Early-warning risk signals, AI-narrative snapshots | ~900 LOC, 10 files | **Decoupled.** No longer imports `attendance` or `reports`. `academic_average` and the risk signal formerly named `LOW_ATTENDANCE` (now `LOW_SUBMISSION_RATE`) are computed directly from `gradebook.GradeEntry`/`Assessment` — a normalized average of published+approved entry scores, and the percentage of expected assessments with any recorded entry, respectively. `MISSING_GRADES` was already gradebook-only. Clean dependency: only `academics` and `gradebook`. |
| `dashboard` | Teacher/report AI helpers (`lesson_ai.py`, `ai_reports.py`) | not deep-audited | Teacher Copilot (Pillar C) material; revisit alongside Phase 5 (Teacher Copilot 2.0). |
| `mastery` | Curriculum taxonomy (`Strand`/`Topic`) and assessment-level mastery evidence (Phase 3, Pillar D) | ~350 LOC, 8 files | Depends only on `academics` and `gradebook` (reads `GradeEntry`/`Assessment`, adds a nullable `Assessment.topic` FK). No shed-side coupling. Mirrors `analytics`' percentage-normalization approach rather than importing it, to avoid new cross-app coupling for a ~5-line helper. |

## Extract / hand off later (institutional record-keeping)

Nothing in this section is removed now. These apps stay deployed and functional; they're frozen for *new* scope (see [`AGENTS.md`](../AGENTS.md)) pending the Suku360 integration contract (roadmap Phase 6).

| App | Purpose | Size | Extraction risk |
|---|---|---|---|
| `attendance` | Calendar policy, attendance sessions/records, immutable revisions | ~1438 LOC, 12 files | **Clean.** No other app imports from it — `analytics` was the one reverse dependent and has since been decoupled (see above). Lowest-risk extraction candidate. |
| `finance` | Fee structures, charges, Paystack Mobile Money payments, receipts, reconciliation | ~1488 LOC, 13 files | **Clean.** No reverse dependents. External integration: `finance/gateways.py` (`PaystackGateway`). |
| `guardians` | Guardian-student links and authorization | ~492 LOC, 11 files | **Clean.** No reverse dependents; only reads `ClassEnrollment` for display. Smallest app in this group. |
| `reports` | Term-report workflow (draft → approve → publish) and grade/promotion snapshotting | ~1530 LOC, 12 files | **Interface defined.** `reports/services.py` now calls `gradebook.evidence.active_scheme_for`/`category_evidence` — a read-only "approved evidence" interface — instead of importing `GradeEntry`/`GradeScheme` from `gradebook.models` directly. `reports → communications` (used in `transition_report` for report-review/publish notifications) remains untouched — both are extract-side apps, so that coupling isn't a boundary issue and stays as-is. |
| `communications` | Notification inbox, templated email/SMS (Arkesel), delivery-attempt audit trail | ~1263 LOC, 20 files | **Boundary resolved, now for every keep-side caller.** `academics`/`gradebook`/`quizzes`/`dashboard` no longer import `communications` at all. `academics/signals.py` keeps only its own bookkeeping (`remember_previous_class_teacher`); the notification receivers that used to live there now live in `communications/receivers.py`, connected directly to `academics.models.TeacherAssignment`/`SchoolClass`'s own `post_save`/`post_delete` signals, and to `quizzes.models.AssignmentSubmission`'s `post_save` the same way. `gradebook/history.py` fires two domain-event signals (`gradebook.signals.grade_entry_published`, `grade_review_decided`); `dashboard/lesson_workflow.py` fires two more (`dashboard.signals.lesson_note_needs_review`, `lesson_note_author_notified`) instead of calling `communications` directly — `communications/receivers.py` subscribes to all of them and builds the same notifications as before. Dependency direction is `communications → academics`/`gradebook`/`quizzes`/`dashboard` (extract-side depending on core, the correct direction) rather than the reverse. |

## What this means for sequencing

- `attendance`, `finance`, `guardians` can be extracted with the least engineering risk once the Suku360 contract exists — no code elsewhere needs to change first.
- `reports` and `communications` no longer have pre-extraction blockers: the "approved evidence" interface (`gradebook.evidence`) and the notification boundary (`communications` subscribing to `academics`/`gradebook` events instead of the reverse) both now exist. Extracting either app to a separate service is now a matter of moving the code and standing up the actual Suku360 API contract (Phase 6) — not an internal-coupling problem.
- `analytics` no longer needs any pre-extraction work — it was rebuilt on gradebook learning-activity evidence directly, clearing the way for Phase 3 (Mastery Engine) to build on top of it.

## Decision (2026-08): extraction to a separate service — evaluated and rejected

The Suku360 integration contract named above as the extraction blocker is now built (Phase 6 — roster sync, SSO, Premium gating, the evidence channel, both credential handoffs automated). With that precondition satisfied, a real technical extraction (a separate deployable project with its own database) was evaluated for `attendance`/`finance`/`guardians`/`reports`/`communications` and rejected as disproportionate — checked directly, not assumed:

- `attendance`, `finance`, and `guardians` hold **direct database foreign keys into Nyansa's core, actively-developed tenancy models** — `schools.School`, `schools.SchoolMembership`, `academics.Term`, `academics.SchoolClass` (e.g. `finance.Charge.student` → `schools.SchoolMembership`, `attendance.AttendanceSession.term` → `academics.Term`). The "clean" verdicts in the table above describe the absence of *reverse* dependents (keep-side apps importing extract-side code) — they don't describe FK independence, which doesn't exist here. A standalone project would need either a second Suku360-style sync integration (duplicating School/SchoolMembership/Term/SchoolClass into a second database) or rewriting every FK-based query in ~1,437 lines of app code into external-id lookups plus API calls. Both are new, ongoing operational surface for a feature set explicitly not being grown.
- The business direction (see `docs/delivery-roadmap.md` Phase 6) is freeze-for-existing-users, not-marketed-to-new-customers — already true in practice, verified directly: neither the public landing page (`templates/home.html`, already repositioned around the 5-pillar AI-tutoring boundary) nor the actual signup flow (`templates/billing/plans.html`) mentions any of these five apps.
- `config/context_processors.py`'s import of `reports.models.TermReport` (for the admin nav badge) is a normal same-codebase import, not a problem — it would only need addressing if a real technical extraction were revisited later.

**Decision: these five apps stay exactly where they are** — same codebase, same deployment, same database — continuing to serve any existing users, with no further investment or new-customer marketing (already the reality; no code changes were needed to make it so).
