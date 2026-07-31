from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import Assessment, GradeEntry, GradeImportBatch, GradeImportRow


@transaction.atomic
def confirm_grade_import(*, batch, confirmed_by, publish=False):
    batch = GradeImportBatch.objects.select_for_update().select_related("assessment").get(pk=batch.pk)
    if batch.status != GradeImportBatch.Status.PREVIEW:
        raise ValidationError("This import batch has already been processed.")
    if batch.error_count:
        raise ValidationError("Correct every workbook error before confirming the import.")
    if batch.assessment.status == Assessment.Status.CLOSED:
        raise ValidationError("Closed assessments cannot receive imported grades.")
    rows = list(batch.rows.select_related("student").filter(status=GradeImportRow.Status.VALID))
    if not rows:
        raise ValidationError("The workbook does not contain any scores to import.")
    target_status = GradeEntry.Status.PUBLISHED if publish else GradeEntry.Status.DRAFT
    entries = []
    for row in rows:
        entry = GradeEntry.objects.select_for_update().filter(
            assessment=batch.assessment, student=row.student
        ).first()
        entry = entry or GradeEntry(
            school=batch.school, assessment=batch.assessment, student=row.student
        )
        entry.score = row.score
        entry.recorded_by = confirmed_by
        entry.source = GradeEntry.Source.IMPORT
        entry.status = target_status
        entry.full_clean()
        entries.append(entry)
    for entry in entries:
        entry.save()
    for row in rows:
        row.status = GradeImportRow.Status.IMPORTED
    GradeImportRow.objects.bulk_update(rows, ["status"])
    batch.status = GradeImportBatch.Status.CONFIRMED
    batch.confirmed_by = confirmed_by
    batch.confirmed_at = timezone.now()
    batch.full_clean()
    batch.save(update_fields=["status", "confirmed_by", "confirmed_at"])
    return batch, len(entries)
