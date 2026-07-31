# Phase 2A — Gradebook Foundation

Phase 2A introduces the common academic record that later manual-entry, spreadsheet, quiz, assignment, and reporting workflows will share. It does not remove the legacy grading path yet; adapters and user-facing workflows will migrate incrementally so existing tutor behavior remains available.

## Delivered domain

- `GradeScheme` belongs to one school and academic year and moves through Draft, Active, and Archived states.
- `AssessmentCategory` defines an ordered percentage weight inside a scheme. Codes are unique within each scheme.
- `Assessment` belongs to a subject offering and category, records a positive maximum score, and moves through Draft, Published, and Closed states.
- `GradeEntry` records one student's score for one assessment, its source (`ONLINE`, `MANUAL`, or `IMPORT`), its recorder, and Draft or Published status.

The model deliberately keeps raw evidence separate from calculated results. A percentage is derived from each raw score and maximum score; a term result is calculated on demand from published entries rather than copied into another mutable field.

## Scheme activation

Schemes may be prepared in Draft state. The activation service locks the target scheme and requires:

- at least one category;
- category weights totaling exactly `100.00%`;
- the scheme and academic year to share the same school.

Activating a scheme archives any other active scheme for the same school and academic year. This provides one authoritative configuration while retaining historical definitions.

## Weighted calculation

For each category, the calculator averages published entry percentages. It then applies the category weights. Categories without published evidence are omitted and the available weights are proportionally normalized, matching Nyansa's legacy behavior. The result includes both the effective weight and category breakdown so future interfaces can make incomplete evidence visible.

Example: coursework weighted at 40% with an average of 80%, and an exam weighted at 60% with an average of 50%, produces `62.00%`.

## Isolation and integrity rules

- Schemes, years, assessments, offerings, categories, entries, and memberships must remain within one school tenant.
- An assessment category must come from the offering's academic year.
- A grade recipient must be an active student enrollment in the assessment's class.
- A recorder must be a teacher or school administrator in the same school.
- Scores cannot be negative or exceed the assessment maximum.
- A student can have only one entry for an assessment.
- Draft entries never contribute to a published weighted result.

These model rules are validated before service-level writes. Database constraints additionally enforce uniqueness and indexed tenant/student publication queries.

## Deferred to the next Phase 2 slices

- Teacher-facing roster entry and review pages.
- Spreadsheet template download, upload, validation preview, and atomic confirmation.
- Immutable import batches and row-level audit history.
- Adapters that copy or synchronize legacy quiz and assignment evidence.
- Publication permissions and full workflow notifications.
