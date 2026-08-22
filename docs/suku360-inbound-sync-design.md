# Design: Suku360 Inbound Context Sync

**Status: design only — nothing in this document is implemented.** This is the inbound half of Phase 6 ("Suku360 integration"): how Suku360 would push school/class/subject/teacher/learner context *into* Nyansa. The outbound half (Nyansa exposing approved evidence/mastery/risk-signal data *to* Suku360) is already shipped — see `integrations/` app and `docs/delivery-roadmap.md` Phase 6. This document is necessarily speculative in places, since no real Suku360 API exists to integrate against yet; every open question is called out explicitly rather than silently assumed.

## 1. Why this is scoped as design-only

Unlike every other feature built this session, there's no way to verify inbound sync end-to-end without a real Suku360 counterpart — the outbound API could be built and tested completely self-contained (Nyansa is both producer and, via tests, consumer), but inbound sync's whole point is receiving payloads shaped by a system that doesn't exist in this repository. Writing speculative model/view code against a guessed contract risks building the wrong thing twice. This document instead maps out the concrete decisions that *can* be made now — which Nyansa models correspond to which Suku360 concepts, what's missing to make that mapping idempotent, what the ownership rules must be — so that when a real contract exists, implementation is a matter of filling in a known shape, not inventing one under time pressure.

## 2. Ownership boundary this design must respect

From `docs/product-boundary.md`, Pillar E, verbatim:

> **Pillar E — Suku360 Integration:** Roster/context sync from Suku360 and approved learning evidence/mastery summaries back to Suku360, without duplicating institutional authority.

And the ownership table's relevant rows:

| Domain | Nyansa AI | Suku360 |
|---|---|---|
| Admissions/staff administration | Does not own | Owns |
| Attendance | Consumes context | Owns official attendance |
| Official grades | Contributes approved evidence | Owns authoritative grade/result record |

**Inference, not a direct quote** (the doc doesn't state roster-sync directionality in these exact words, but it follows from the above plus the doc's own North Star — *"Suku360 runs the school. Nyansa AI helps the school teach — and helps the learner learn."*): once a school/class/subject/teacher/learner record is Suku360-sourced, **Suku360 is the sole source of truth for it**. Nyansa mirrors it, never independently originates or edits it after sync. This is the single governing rule the rest of this design follows.

## 3. What gets synced — mapping table

| Suku360 concept | Nyansa model | Notes |
|---|---|---|
| Institution | `schools.School` | Already exists; needs a new external-id field (§5) |
| Academic year | `academics.AcademicYear` | `school`, `name`, `start_date`/`end_date`, `is_current` |
| Term | `academics.Term` | `academic_year`, `name`, `order`, `start_date`/`end_date` |
| Class/stream | `academics.SchoolClass` | `school`, `academic_year`, `name`, `capacity`, `class_teacher` |
| Staff member | `schools.SchoolMembership` (role `TEACHER`/`SCHOOL_ADMIN`) + `accounts.User` | See §6 for account-creation approach |
| Learner | `schools.SchoolMembership` (role `STUDENT`) + `accounts.User` + `schools.StudentProfile` | Mirrors `schools/roster_import.py`'s existing upsert-by-identifier shape |
| Class roll | `academics.ClassEnrollment` | `school_class`, `student` (a `SchoolMembership`), `status` |
| Subject-in-class-in-term | `academics.SubjectOffering` | `school`, `school_class`, `subject`, `term` — needs `courses.Subject` to exist first |
| Teacher-subject assignment | `academics.TeacherAssignment` | `offering`, `teacher`, `is_lead` |

**Deliberately NOT synced:** `courses.Subject`/`courses.Enrollment`. Exploration confirmed these are a separate, older, looser concept — `Subject` has no uniqueness constraint on `(school, name)` (just an index, duplicates are structurally possible today), and `Enrollment.student` is a direct FK to `User`, not `SchoolMembership`, breaking the mediation pattern every other roster model uses. `academics.SubjectOffering` is the "official," Suku360-mappable subject-in-class-in-term structure; `courses.Subject`/`Enrollment` is how a *student* self-manages what they're studying inside Nyansa's own learning workspace (Pillar B) and should stay entirely Nyansa-local, unaffected by institutional sync. If this distinction turns out to be unwanted in practice, unifying them is a separate, larger modeling decision — not assumed here.

**Never synced, by design, regardless of future scope:** anything in `mastery`, `tutor`, `quizzes`, `analytics`, `gradebook`'s entry/review data, `dashboard` — all Nyansa-owned teaching/learning/intelligence data per Pillar A–D. Sync only ever touches roster/context (§3's table), never learning activity or evidence.

## 4. What's missing today to make this idempotent

Confirmed by direct inspection: **no model in this codebase has an external-id field.** A repo-wide search for `external_id`/`sso`/`source_system` matches nothing but prose in docs. `School.slug` is Nyansa's own human-chosen identifier (validated, unique, but chosen at Nyansa onboarding time, not provided by Suku360) — safe to use as a *display* identifier, unsafe to use as the sync join key, since nothing stops a school's Nyansa slug and Suku360 ID from having no relationship to each other.

`SchoolMembership.identifier` ("optional school-specific staff, student, or guardian identifier") looks tempting to reuse but shouldn't be — it already means "the school's own internal ID for this person" (e.g. a student ID number a school assigns), a different concept from "Suku360's system ID for this person." Conflating them would make the field ambiguous the moment a school's own ID scheme and Suku360's ID scheme diverge (they will — Suku360 IDs are almost certainly UUIDs or a proprietary scheme, not the same string a school prints on a report card).

**What this design recommends adding, when this is actually built:** a `suku360_id` (`CharField`, unique per model, indexed) field on `School`, `SchoolMembership`, `SchoolClass`, `courses` is excluded per §3, `academics.SubjectOffering` (composite entities like offerings might not need their own external id if they can be resolved by their four FK components + Suku360's class/subject/term ids — an open question, see §9). Every sync write becomes `Model.objects.update_or_create(suku360_id=..., defaults={...})` — the same upsert shape `schools/roster_import.py::import_student_roster` already uses (there, keyed on `identifier`; here, keyed on the new field), not a new pattern.

## 5. Auth: reuse `IntegrationCredential`, but it needs two changes first

The outbound API's `integrations.IntegrationCredential` (one SHA-256-hashed bearer token per school, `OneToOneField`) is the natural mechanism to reuse — but as it stands today it can't safely support inbound writes for two concrete reasons:

1. **No scope field.** `IntegrationCredential` is a bare active/inactive token — whatever a view built with it chooses to allow, it allows. Read (outbound evidence) and write (inbound roster mutation) are very different risk levels; the same unscoped token authorizing both is a real hazard (a leaked outbound-API token, meant only for a reporting integration, would also be able to rewrite the school's roster). **Recommendation:** add a `scope` field (e.g. `CharField` choices `READ`/`WRITE`, or a `permissions` `JSONField`/M2M if finer-grained control is ever needed) and change `school` from `OneToOneField` to `ForeignKey` so a school can hold separate read and write credentials.
2. **No actor of record.** `authenticate_request` resolves only a `School`, never a person — fine for read-only GETs, not fine for writes. Nearly every mutation-producing model in this codebase requires a `SchoolMembership` actor (`created_by`, `recorded_by`, `changed_by` — `PROTECT`ed FKs in `GradeEntryRevision`, `TopicRevision`, `RemediationPlan`, etc.). Inbound sync needs the same. **Recommendation:** either (a) each school provisions a real `SchoolMembership` (role `SCHOOL_ADMIN`, `portal_access_enabled=False`) representing "the Suku360 sync process" and `IntegrationCredential` gains an `acting_as` FK to it, or (b) sync-created audit rows get a dedicated nullable "system actor" allowance — (a) is preferable since it requires no special-casing of every existing service function's `actor` parameter, at the cost of one extra `SchoolMembership` row per school.

## 6. Account creation for synced people

`accounts.User` has no external-id field either, and `username` (not `email`) is the actual unique login identifier (`email` is plain, non-unique `AbstractUser.email`). `schools/roster_import.py` already solves "create a Nyansa account for a person who hasn't logged in yet" for bulk student CSV import: `user.set_unusable_password()` plus `_unique_username(school, id)` (slugifies `f"{school.slug}-{id}"`, appends a numeric suffix on collision). This is the pattern to reuse verbatim for sync-created teachers/students — an account exists, has no usable password, and the person authenticates through whatever real channel (invitation email, SSO, a future Suku360-brokered login) actually gets built later. This design does not attempt to solve authentication/SSO between the two systems — that's explicitly a separate decision.

## 7. Suggested API contract shape

**One batch endpoint, not many small REST resources** — `POST /api/v1/sync/roster/`, mirroring `gradebook.GradeImportBatch`'s "stage a whole batch, process atomically, report per-row outcome" shape rather than the outbound API's per-resource GET style, because a periodic/nightly institutional sync naturally arrives as one bulk push, not scattered single-entity calls:

```
POST /api/v1/sync/roster/
Authorization: Bearer <write-scoped token>

{
  "academic_year": {"suku360_id": "...", "name": "2026/2027", "start_date": "...", "end_date": "...", "is_current": true},
  "terms": [{"suku360_id": "...", "name": "Term 1", "order": 1, "start_date": "...", "end_date": "..."}],
  "classes": [{"suku360_id": "...", "name": "Basic 6", "capacity": 35}],
  "staff": [{"suku360_id": "...", "role": "TEACHER", "first_name": "...", "last_name": "..."}],
  "learners": [{"suku360_id": "...", "class_suku360_id": "...", "first_name": "...", "last_name": "...", "date_of_birth": "..."}],
  "subject_offerings": [{"class_suku360_id": "...", "subject_name": "...", "term_suku360_id": "..."}],
  "teacher_assignments": [{"offering_ref": "...", "teacher_suku360_id": "...", "is_lead": true}]
}
```

Response, mirroring `GradeImportBatch`'s `row_count`/`valid_count`/`error_count` shape:

```json
{
  "batch_id": 42,
  "status": "COMPLETED",
  "created": {"classes": 3, "staff": 12, "learners": 340, ...},
  "updated": {"classes": 1, ...},
  "errors": [{"row": "learners[17]", "detail": "class_suku360_id does not match any known class"}]
}
```

This is illustrative, not a committed schema — the real field names/nesting depend entirely on Suku360's actual API, which doesn't exist yet from Nyansa's side of the integration.

## 8. Idempotency and audit trail

Mirror `gradebook.GradeImportBatch`/`GradeImportRow` — the heavier of the two existing bulk-ingest patterns, and the right one here because sync is a **repeated, unattended, machine-to-machine** push (no human "preview then confirm" step like `roster_import.py`'s session-based CSV flow), so the audit trail has to be persisted at write time, not held in a session:

- A `SyncBatch` row per inbound push: `school`, `credential` (which `IntegrationCredential` authenticated it), `status` (`PROCESSING`/`COMPLETED`/`FAILED`), `received_at`, counts.
- A `SyncRecord` row per entity touched: `batch`, `entity_type`, `suku360_id`, `nyansa_object_id` (nullable, generic FK or per-type FK), `action` (`CREATED`/`UPDATED`/`UNCHANGED`/`ERROR`), `error` text.

Every write inside a batch happens via `update_or_create(suku360_id=..., defaults={...})`, wrapped in one `@transaction.atomic` per batch (matching `confirm_grade_import`'s convention) — a partially-bad batch either fails and reports which rows errored (nothing partially applied), or succeeds and reports what changed, never a silent partial mutation.

## 9. Conflict rules and open questions

- **Once a record has a `suku360_id`, its Suku360-sourced fields become read-only in every Nyansa UI that could otherwise edit them** (`school_onboarding`, `curriculum_view` doesn't touch roster so it's unaffected, `people_directory`, class/teacher-assignment admin screens). This needs its own follow-up design once real field-level ownership is known — which fields on a synced `School`/`SchoolMembership` Nyansa is still allowed to manage locally (e.g. a teacher's Nyansa-side notification preferences) versus fields Suku360 owns outright (their name, their role) is not fully answerable without the real contract.
- **What happens to a Nyansa-local `SchoolMembership`/`SchoolClass` that predates sync being turned on for a school?** (Every school onboarded before Suku360 integration exists has no `suku360_id` on anything.) A first sync for an existing school needs a reconciliation strategy — best-effort matching by name/identifier, or requiring a manual one-time link-up — not designed here.
- **Deletion/deactivation semantics** — if Suku360 marks a learner withdrawn, does Nyansa deactivate the `SchoolMembership` (`status=SUSPENDED`), or something softer? Given `ClassEnrollment.status` already has a `TRANSFERRED`/`COMPLETED` option, a sync-driven status change plausibly maps there, but this needs the real Suku360 event vocabulary to design properly.
- **Whether `SubjectOffering`/`TeacherAssignment` need their own `suku360_id`** or can always be resolved from their FK components (class + subject + term, already unique together) plus a Suku360-side subject-name string — leaving them without a dedicated id would simplify the model but makes renaming a subject on the Suku360 side harder to reconcile. Left open.

## 10. Explicit non-goals

- No code, migration, or model change in this pass — this document only.
- No SSO/authentication bridge between Nyansa and Suku360 accounts (§6) — a person's Nyansa login and Suku360 identity are only linked via `suku360_id` on the roster record, not via any shared credential system.
- No attempt to sync `courses.Subject`/`Enrollment`, or anything in `mastery`/`tutor`/`quizzes`/`analytics`/`gradebook`'s entry data (§3).
- No committed API schema — §7's payload shape is illustrative only, pending a real Suku360 contract.
