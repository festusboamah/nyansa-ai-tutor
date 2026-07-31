# Phase 2B — Teacher Gradebook

Phase 2B exposes the generalized gradebook through a teacher-facing workflow. It is designed for schools where students may not sign in: an assigned teacher can create assessment records and enter an entire class roster manually.

## Delivered workflow

1. A teacher opens Gradebook and sees only subject offerings explicitly assigned to their active school membership.
2. The teacher opens an offering to review its assessments or create one.
3. Assessment creation offers only categories from the active grade scheme for the offering's school and academic year.
4. The teacher opens an assessment roster containing active student memberships with active class enrollments.
5. Entered scores can be saved as Draft or Published. Existing rows are updated rather than duplicated.
6. Closed assessments remain visible but cannot be edited.

The pages are linked from both the primary teacher navigation and teacher dashboard. Wide roster tables scroll horizontally on narrow screens, while action controls stack for touch use.

## Authorization boundaries

- A school membership with the Teacher role is required for every gradebook page.
- Offering and assessment lookups require an explicit `TeacherAssignment` for the active membership.
- URL identifiers cannot be used to open another teacher's unassigned offering or another school's assessment.
- Student and administrator memberships cannot enter through the teacher workflow.
- All grade writes use the active school and active teacher membership supplied by server-side request context.

## Atomic score entry

Every submitted non-blank score is converted to a decimal and validated against the common `GradeEntry` rules before any database write occurs. If one roster row is invalid, no row from that submission is saved. This avoids partial publication and gives the teacher row-specific feedback while retaining all submitted values on screen.

Blank fields do not delete existing evidence. Deletion and explicit score clearing require a separate audited workflow and are intentionally deferred.

## Verification

Workflow tests cover assigned-offering visibility, unauthorized teacher access, student denial, active-scheme assessment creation, atomic invalid submissions, draft-to-published updates, source and recorder attribution, and closed-assessment protection.

## Deferred

- Spreadsheet template download, preview, and confirmed batch import.
- Import-batch and row-level audit records.
- Assessment editing and explicit grade deletion/correction history.
- School-administrator grade review and approval queues.
- Legacy quiz and assignment adapters.
