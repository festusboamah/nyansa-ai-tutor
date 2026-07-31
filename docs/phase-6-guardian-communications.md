# Phase 6: Guardian portal and communications

## Guardian authorization

Guardian access is granted only through an active `GuardianLink`. Each link joins one parent membership to one student membership in the same school and records relationship type, primary-contact status, a school-held consent or verification reference, authorizing administrator, and timestamps. Names, email addresses, phone numbers, and surnames never imply access.

Only active school administrators can authorize, reactivate, or revoke links. Revocation removes portal access immediately while retaining authorization history. A guardian can have several linked students, and a student can have several guardians.

## Portal

The mobile-responsive guardian portal lists only students available through active links. For each child it shows derived attendance summaries and published term reports. Draft, pending, returned, and merely approved reports are excluded. Report PDF access repeats the link check on every request.

## Communication outbox

Web workflows enqueue `MessageIntent` records and do not contact providers directly. Each intent stores tenant, recipient, optional linked student, rendered safe content, destination, business reference, status, retry time, and a school-scoped SHA-256 idempotency key. Repeating the same template, recipient, and business event returns the existing intent.

Run the worker with:

```powershell
python manage.py process_messages --limit 50
```

Successful and failed sends create immutable `DeliveryAttempt` records. Failures use bounded exponential retry and stop after three attempts. Operators can inspect recent status and errors in the school communications dashboard.

## Channels and privacy

- Email uses Django's configured email backend.
- SMS uses the replaceable Arkesel gateway configured by `ARKESEL_API_KEY`, `ARKESEL_SENDER_ID`, and `ARKESEL_SMS_ENDPOINT`.
- Guardians can opt out of email or SMS independently and must provide a phone number before enabling SMS.
- SMS templates marked as containing sensitive information are rejected.
- Built-in report and attendance SMS notices reveal no score, attendance status, fee balance, or other sensitive record. They direct the guardian to the authenticated portal.
- Portal access is independent of notification preferences.

## Event coverage

Publishing a report queues report notices for actively linked guardians. Submitting an absent or excused attendance record queues a privacy-safe attendance notice. Administrators can queue school-event email messages. A balance template and event type are ready for the Phase 7 ledger to call through the same `enqueue_guardian_event` service.

## Recovery

Provider failures never change the underlying report or attendance record. Correct gateway credentials or provider availability, then allow the worker to retry due intents. Because business events are idempotent, replaying publication or queue logic does not create duplicate messages. Delivery history is retained for audit.
