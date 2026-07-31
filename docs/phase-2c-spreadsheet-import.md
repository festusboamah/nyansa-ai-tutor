# Phase 2C — Spreadsheet Grade Import

Phase 2C adds a controlled Excel workflow for teachers who already maintain marks offline. It uses the same `GradeEntry` records and validation rules as manual entry, so imported evidence cannot bypass school, roster, score, or publication controls.

## Teacher workflow

1. Open an assigned assessment roster and download its `.xlsx` template.
2. Enter scores in the blue Score column. Identity columns are protected.
3. Upload the completed workbook, limited to 2 MB.
4. Review every roster row and any validation errors before grades exist.
5. Correct errors in Excel and upload a new batch, or confirm a valid batch as Draft or Published.

Confirmation is atomic. If validation fails before or during confirmation, no grade from that batch is written.

## Workbook contract

The workbook contains two sheets:

- **Instructions** identifies the school, assessment, class, subject, and maximum score and explains the workflow.
- **Grade Roster** contains the server-issued student record ID, school identifier, display name, and editable score.

The roster freezes its header, enables filtering, protects identity columns, unlocks only score cells, and applies Excel decimal validation from zero through the assessment maximum. The server remains authoritative and repeats every validation during upload.

Uploads are rejected when they are unreadable, oversized, structurally complex, missing required sheets, bound to another school or assessment, have changed headers, or contain extra rows. Row validation detects missing, duplicate, unknown, or inactive students; formulas; non-finite values; and scores outside the allowed range. Blank scores are explicitly skipped rather than treated as zero.

## Audit records

`GradeImportBatch` records the tenant, assessment, original filename, uploader, row totals, validation outcome, confirmation operator, and timestamps. `GradeImportRow` preserves the submitted student identifier and score, normalized score, row outcome, and error message.

Confirmed rows move to Imported state. The resulting grade entry records `IMPORT` as its source and the confirming teacher as recorder. A confirmed batch cannot be replayed.

Uploaded workbook binaries are not retained. This reduces exposure of student information while the normalized audit evidence remains available for operational review.

## Authorization and concurrency

- Download, upload, preview, and confirmation all require the active Teacher membership.
- The teacher must be assigned to the assessment's subject offering.
- A teacher can preview and confirm only batches they uploaded.
- Confirmation locks the batch and existing grade rows inside one transaction, preventing replay and partial persistence.
- A closed assessment cannot accept an upload or confirmation.

## Deferred

- Correction and deletion history for individual grades.
- School-administrator review and approval queues.
- Downloadable error workbooks.
- Legacy quiz and assignment synchronization.
