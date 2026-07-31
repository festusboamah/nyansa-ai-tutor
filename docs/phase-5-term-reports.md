# Phase 5: Term reports

## Purpose

Term reports are official school records built from approved academic evidence. A generated report stores a complete snapshot of school identity, policy, subject results, attendance, comparison data, and calculation time. Later changes to grades, calendars, branding, or thresholds do not silently alter a reviewed or published report.

## Calculation rules

- Only grade entries that are both `PUBLISHED` and `APPROVED` contribute.
- Each assessment score is converted to a percentage.
- Percentages are averaged within their assessment category.
- Available category averages are weighted by the active grade scheme. If some categories have no approved evidence, available weights are normalized rather than treated as zero.
- Subject total is the resulting weighted percentage, rounded to two decimal places.
- Report total is the sum of subject totals with evidence.
- Report average is the total divided by the number of subjects with evidence.
- Pass/fail uses the snapshotted policy pass mark.
- Promotion defaults from the snapshotted promotion threshold and remains editable while the report is Draft or Sent Back.
- Position is optional. When enabled, descending averages use competition ranking: equal averages share a position and the following position is skipped.
- Attendance uses the Phase 4 instructional-day calendar through the term end date.
- Prior-term comparison uses the latest earlier published report for the same student and class.

## Workflow and permissions

Teachers assigned to a class or its subject offerings and school administrators can generate, edit, and submit reports. Only school administrators can approve, send back, publish, or reopen. Returning and reopening require reasons. Workflow events cannot be edited or deleted.

Generation refreshes only Draft and Sent Back records. Pending, Approved, and Published snapshots are skipped. A published report must be explicitly reopened, which increments its version, before source changes can be incorporated.

## PDF and bulk operation

Each report can be rendered as an A4 school-branded PDF. A class download streams a ZIP containing every published student PDF. Class generation runs as one atomic service operation, preventing partially generated classes if validation fails. For unusually large deployments, a background-job adapter can call the same service without changing report calculations or state rules.

## Recovery

If generation fails, correct the active grade scheme, approved grade evidence, enrollment, or calendar data and retry. Existing locked reports are not changed. Reopen a published report only when an authorized correction is required and record the reason.
