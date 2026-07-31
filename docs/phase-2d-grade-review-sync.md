# Phase 2D — Grade Review and Legacy Synchronization

Phase 2D closes the core gradebook accountability loop and begins migration of Nyansa's existing online academic evidence. It adds permanent change records, school-administrator decisions, and explicit adapters that teachers can run repeatedly without duplicating grades.

## Permanent grade history

All Phase 2 grade-writing workflows now use one transactional service: manual roster entry, corrections, spreadsheet confirmation, and legacy synchronization. Each initial write or material change creates a `GradeEntryRevision` containing:

- previous and new score;
- previous and new publication state;
- previous and new source;
- change type and required reason;
- responsible school membership and timestamp.

Revision rows reject updates and deletion through the model and are read-only in Django administration. Repeating a write with the same score, state, and source is a no-op and creates no redundant history.

Published corrections cannot be made through the bulk roster screen. Teachers use the correction page and provide a permanent reason. Draft entries may still be refined in the roster before publication.

## Administrator review

Published grades enter Pending Review. A school administrator can:

- **Approve** the grade, locking it against teacher correction; or
- **Return** it with a required note, allowing the assigned teacher to correct and resubmit it.

Every decision creates an immutable `GradeReviewDecision`. The grade retains its current decision, reviewer, note, and time for efficient queues, while the decision table preserves the full sequence. A corrected published grade returns to Pending Review automatically.

The review queue is tenant-scoped and available only to the active School Admin membership. Teacher correction pages remain restricted to teachers assigned to the assessment offering.

## Legacy links and synchronization

A teacher may optionally link a new unified assessment to one existing quiz or assignment from the same subject. The teacher makes the offering choice explicitly because a legacy subject can serve more than one class or term.

### Quiz policy

For each actively enrolled student, synchronization averages all scored attempts for the linked quiz. That percentage is normalized to the unified assessment maximum. This preserves the averaging behavior used by the legacy weighted-grade calculation.

### Assignment policy

For each actively enrolled student, synchronization uses the latest teacher-finalized submission. Its score is normalized from the submission maximum to the unified assessment maximum.

Both adapters create Published entries with source `ONLINE` and a synchronization revision. Repeating synchronization with unchanged legacy results creates no new grade or revision. If an approved grade would change, the entire transaction stops until an administrator returns it.

Synchronization is an explicit teacher action from the assessment roster. Existing quiz-taking and assignment-grading behavior is unchanged.

## Integrity rules

- A unified assessment can link to either a quiz or assignment, never both.
- The linked legacy item and offering must share a subject.
- Only active students enrolled in the offering class are synchronized.
- Closed assessments reject synchronization.
- Reviewers must be administrators in the grade's school.
- Grade recorders must be teachers or administrators in the same school.
- All multi-student synchronization and import operations remain atomic.

## Deferred

- Automatic event-driven synchronization after online grading.
- Student and guardian views backed exclusively by the unified gradebook.
- Multi-stage department-head or headteacher approval policies.
- Bulk review decisions and report-card publication snapshots.
