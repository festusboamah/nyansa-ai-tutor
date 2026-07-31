# Phase 0 Baseline Audit

- Audit date: 2026-07-31
- Database engine: SQLite
- Purpose: Establish a non-sensitive migration baseline before multi-tenancy work.

## Current record counts

| Record | Count |
|---|---:|
| Users | 3 |
| Students | 2 |
| Teachers | 1 |
| Subjects | 2 |
| Enrollments | 2 |
| Materials | 2 |
| Study documents | 4 |
| Quizzes | 6 |
| Quiz submissions | 9 |
| Assignments | 2 |
| Assignment submissions | 1 |
| Lesson notes | 4 |
| Media files | 7 |

Counts are a point-in-time development snapshot, not production analytics.

## Integrity observations

- No users have an unknown role.
- No duplicate subject enrollments were found.
- No quiz submissions are missing a score.
- No graded assignment submission is missing its grading timestamp.
- One lesson note has empty generated content. The Phase 1 migration must preserve it and treat it as an incomplete legacy draft rather than deleting it.

## Baseline verification

- Django system check: passed with no issues.
- Automated tests: 18 passed.
- Migration drift check: required before Phase 1 changes.
- A local, ignored backup was created with the SQLite database, media directory, SHA-256 database hash, and JSON manifest.

## Migration implications

The current dataset is small enough for a straightforward expand/backfill/contract migration, but the procedure must remain production-safe:

1. Create one designated legacy `School`.
2. Create school memberships for all three existing users from their current roles.
3. Assign both existing subjects and their related academic records to the legacy school.
4. Preserve all uploaded media paths.
5. Preserve the incomplete lesson note as a draft-compatible legacy record.
6. Re-run this audit and reconcile counts after every migration rehearsal.

## Reproduce the audit

```powershell
python manage.py baseline_audit
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\backup_project.ps1
```

Stop write traffic before taking a filesystem copy of SQLite. Production PostgreSQL backups will require a database-native backup and restoration procedure rather than this development script.
