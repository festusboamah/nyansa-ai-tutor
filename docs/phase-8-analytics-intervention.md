# Phase 8: Analytics and intervention

## Metric authority

Analytics does not maintain a second grade, attendance, or report ledger. It calculates views from authoritative records on request:

- Subject assessment trends use grade entries that are both `PUBLISHED` and administrator `APPROVED`.
- Class and school academic averages use published term-report snapshots.
- Attendance percentages use submitted attendance records and Phase 4 instructional-day calculations.
- Enrollment counts use active class enrollments.

Every metric response includes its academic-year/term period and a human-readable source label. Missing records display as unavailable rather than zero.

## Authorization

School administrators can view school-wide, class, subject, signal, and intervention data only for their active school. Teachers can view a class when they are its class teacher or have a subject assignment in that class and term. Offering drill-down additionally requires assignment to that offering or responsibility for the class. Tenant and assignment checks are repeated at every drill-down route.

Students and guardians do not receive staff risk labels. Their existing report, attendance, and ledger views remain the appropriate external records.

## Early-warning rules

Administrators configure school-owned thresholds for:

- academic average below a percentage;
- attendance below a percentage; and
- missing published, approved grade entries at or above a count.

Evaluation stores only the explainable signal: observed value, threshold policy, source, period, evidence counts/record reference, and status. It does not copy full source records. Signals automatically resolve when the source metric recovers and reopen when the rule becomes true again.

Authorized staff can acknowledge a signal by creating an intervention plan, assign it to active school staff, and record a completion outcome. Completing the remaining active intervention resolves the signal while preserving its evidence and action history.

## Narrative summaries

Narratives freeze the exact metrics used to create the text. The default `grounded-template` generator is deterministic and makes no causal claims. Schools may opt into Claude-assisted drafting with:

```env
ANALYTICS_AI_NARRATIVES=True
ANALYTICS_AI_MODEL=claude-sonnet-4-5
```

The AI prompt receives aggregate metrics only, requires explicit period and sources, prohibits student names and inferred causes, and asks for human review. AI generation never creates risk signals, alters grades, attendance, reports, or payments, and never approves its own text. An administrator must explicitly approve every draft before external sharing.

## Recovery and interpretation

- If a metric looks wrong, inspect the displayed source and period first; correct the authoritative record through its existing audited workflow.
- Re-evaluate warning policies after corrections. Existing signals resolve or reopen rather than being silently deleted.
- If AI generation fails, leave AI drafting disabled or retry later; deterministic narrative drafting and all metrics remain available.
- Do not treat a warning signal as a diagnosis. It is a transparent prompt for professional review and documented support.
