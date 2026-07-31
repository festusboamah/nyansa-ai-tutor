# Phase 4 — Attendance and School Calendar

Phase 4 introduces one authoritative daily register per class and school date. It derives instructional days from school configuration rather than storing a manually typed “days open” number, giving later report cards and analytics a reproducible attendance source.

## Instructional calendar

Every school has one `SchoolCalendarPolicy`. Its weekday set defaults to Monday through Friday and may include any unique combination from Monday through Sunday. School administrators also maintain `SchoolClosure` ranges for a specific term, with a retained name, type, creator, and timestamp.

The calendar service deterministically enumerates dates from the term start through the requested end boundary, includes configured weekdays, and excludes every date covered by a holiday or closure. Overlapping closure ranges do not double-subtract a day. Changing the weekday policy or closure list immediately changes derived totals; no student record stores a copied days-open value.

Closure dates must remain inside the term and within the same school tenant. Only the active School Admin membership can change calendar settings.

## Daily register

An `AttendanceSession` represents one regular register for a class and date. A database constraint prevents duplicate sessions for the same class and date. Submission requires:

- an instructional date within the selected term;
- the class and term to share a school and academic year;
- an active teacher assigned through a subject offering or as class teacher, or a school administrator;
- exactly one status for every active student enrollment;
- Present, Absent, or Excused as the only accepted values.

Validation completes before records are committed. Missing students, unknown values, unauthorized actors, closures, weekends, and duplicate submissions therefore create no partial register.

The responsive register presents each student as a touch-friendly row with three status controls. Present is preselected to support rapid normal-day marking, while teachers explicitly review exceptions before submitting.

## Corrections

Submitted registers cannot be resubmitted or silently edited. An authorized teacher or administrator uses the correction workflow, selects a different status, and provides a required reason.

Each correction creates an immutable `AttendanceRevision` containing the previous status, new status, reason, actor membership, and timestamp. Revision records reject updates and deletion through the model and are read-only in Django administration.

## Summaries

Class summaries display Present, Absent, Excused, derived days open, and the attendance percentage for each active student. The percentage is:

`Present submitted sessions / derived instructional days × 100`

The interface states the period boundary used for the calculation. Counts include only submitted sessions for the selected class and term. Excused days remain visible but do not count as Present under the current policy.

## Authorization boundaries

- Teachers see classes where they are the class teacher or have a term subject assignment.
- School administrators see all classes in their active school.
- Class, term, session, record, closure, and membership lookups remain tenant-scoped.
- Students cannot access operational attendance screens.
- A teacher cannot open or mutate an unassigned class by changing a URL identifier.

## Deferred

- Guardian and student attendance views.
- Configurable late or half-day statuses.
- Bulk correction approval policies.
- Attendance alerts and communication delivery.
- Report-card attendance snapshots, delivered in Phase 5.
