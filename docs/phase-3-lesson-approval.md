# Phase 3 — Lesson-Plan Approval

Phase 3 wraps Nyansa's existing AI lesson-note generator in a school-scoped academic approval workflow. Generation remains unchanged: AI produces the first draft, and the teacher remains responsible for its content. The new workflow adds editing, accountable review, permanent versions, and controlled handling of approved material.

## Lifecycle

Lesson notes use four states:

- **Draft:** editable by the author and ready for submission.
- **Pending Review:** locked against teacher editing while a school administrator reviews it.
- **Sent Back:** editable by the author after reviewer feedback.
- **Approved:** immutable until a school administrator explicitly reopens it with a reason.

An author can submit Draft or Sent Back content. A reviewer can approve or send back only Pending Review content. Sending a plan back requires a comment. Reopening an Approved plan also requires a reason and returns it to Sent Back; the author must then save a new version and resubmit.

## Version history

The completed AI response becomes version 1. Every teacher revision creates another `LessonNoteVersion` with:

- a full snapshot of instructional metadata and generated daily content;
- sequential version number;
- required revision reason;
- author membership and timestamp.

Existing lesson notes created before this phase receive their first snapshot when they are first submitted. Version records reject updates and deletion through the model and are read-only in Django administration.

The current lesson note remains the efficient operational record. Approved-content protection is also enforced by the model: changes to instructional fields or status are rejected once approved unless the administrator uses the explicit reopen transition. Reopening never alters the approved version snapshot.

## Review conversation and decisions

`LessonNoteEvent` retains submissions, revisions, approvals, returns, reopenings, and free-form comments with actor and timestamp. Events are immutable and appear chronologically in both teacher and reviewer interfaces.

The teacher and any active school administrator may comment. Other teachers, students, and users from another school cannot view or participate in the conversation.

## Notifications

Submitting a plan creates an in-app notification for every active school administrator. Approval, return, reopening, and administrator comments notify the author through their active teacher membership. Teacher comments notify active school administrators.

Notifications are tenant-scoped, link to the appropriate author or reviewer view, and can be marked read. They intentionally remain in the database rather than relying on email delivery for workflow correctness.

## Authorization boundaries

- Teacher pages filter by the active school and the authenticated author.
- Only the note's author membership can revise or submit it.
- Reviewer queues and decisions require the active School Admin membership.
- Reviewer lookups require the lesson note's subject to belong to the active school.
- Version, event, and notification actors are school memberships rather than global user roles.

## Operational behavior

- PDF download continues to use the current lesson content.
- Pending and approved plans remain visible to their authors.
- Approved plans can be reopened only through the recorded administrator action.
- Notification creation participates in the same database transaction as the state transition.

## Deferred

- Email or SMS mirrors of in-app notifications.
- Department-head and headteacher multi-stage approval policies.
- Side-by-side visual differences between versions.
- Bulk approval and curriculum-wide template libraries.
