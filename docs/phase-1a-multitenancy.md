# Phase 1A: Multi-Tenant Foundation

## Delivered scope

- `School` tenant model with branding, contact, timezone, lifecycle, and stable slug fields.
- `SchoolMembership` linking a global user identity to one school-scoped role.
- School Admin, Teacher, Student, and Parent/Guardian membership roles.
- Active-school resolution through a verified session selection.
- Automatic selection when a user has exactly one active membership.
- Tenant-aware forms and query filters across existing academic workflows.
- Explicit school ownership for subjects and standalone study documents.
- Expand/backfill/constrain migration sequence for legacy data.
- Django admin support for schools and memberships.
- Tenant isolation and membership resolution tests.

## Compatibility strategy

The existing global `User.role` remains temporarily available. During migration, each existing user receives an active membership in `Nyansa Legacy School` using the equivalent Student or Teacher role. Existing subjects and study documents are assigned to the same school. Downstream quizzes, assignments, materials, enrollments, submissions, and lesson notes inherit the tenant boundary through their subject relationships.

New authorization work should use `request.school_membership`. The global role helpers remain only to keep existing screens operational while role checks migrate incrementally.

## Active-school behavior

- No authenticated user: no school context.
- Exactly one active membership: the school is selected automatically and stored in the session.
- Multiple active memberships: no implicit choice; the future school switcher must call the verified selection service.
- Invalid, suspended, or cross-user selection: denied and removed from session context.
- Missing school context: school-scoped query helpers return no records.

## Ownership introduced in this slice

`Subject.school` and `StudyDocument.school` are required after the backfill. Existing academic records deriving from `Subject` are now scoped through `subject__school` in views and forms.

Later Phase 1 slices will introduce academic years, terms, classes, class enrollment, subject offerings, and teacher assignments. Those structures will replace remaining global-role assumptions and provide finer assignment-level permissions.

## Migration rehearsal

Run migrations against a copy, never the working SQLite file:

```powershell
Copy-Item .\db.sqlite3 .\tmp\phase-1a-rehearsal.sqlite3
$env:NYANSA_SQLITE_PATH = (Resolve-Path .\tmp\phase-1a-rehearsal.sqlite3).Path
python manage.py migrate
python manage.py baseline_audit
Remove-Item Env:\NYANSA_SQLITE_PATH
```

Expected legacy-data results:

- One school with slug `nyansa-legacy`.
- One active membership for every existing user.
- No subject or study document without a school.
- All pre-migration record counts preserved.
