from io import BytesIO
from pathlib import Path

from django.conf import settings
from django.template.loader import render_to_string
from xhtml2pdf import pisa

from .services import report_subject_sort_key


def _media_link_callback(uri, _rel):
    if uri.startswith(settings.MEDIA_URL):
        return str(Path(settings.MEDIA_ROOT) / uri.removeprefix(settings.MEDIA_URL))
    return uri


def _available_file_url(field):
    if not field or not field.name or not field.storage.exists(field.name):
        return ""
    return field.url


def render_report_pdf(report):
    html = render_to_string("reports/report_pdf.html", {
        "report": report, "data": report.snapshot, "school": report.school,
        "school_logo_url": _available_file_url(report.school.logo),
        "school_stamp_url": _available_file_url(report.school.official_stamp),
        "headteacher_signature_url": _available_file_url(report.school.headteacher_signature),
    })
    output = BytesIO()
    result = pisa.CreatePDF(
        html, dest=output, encoding="utf-8", link_callback=_media_link_callback
    )
    if result.err:
        raise RuntimeError("The report PDF could not be generated.")
    return output.getvalue()


def _render_template(template_name, context):
    html = render_to_string(template_name, context)
    output = BytesIO()
    result = pisa.CreatePDF(
        html, dest=output, encoding="utf-8", link_callback=_media_link_callback
    )
    if result.err:
        raise RuntimeError("The report PDF could not be generated.")
    return output.getvalue()


def build_class_report_rows(reports):
    reports = sorted(
        reports,
        key=lambda item: (
            -(item.average_score or 0),
            (item.student.user.get_full_name() or item.student.user.username).lower(),
        ),
    )
    subject_names = sorted({
        subject["subject"]
        for report in reports
        for subject in report.snapshot.get("subjects", [])
    }, key=report_subject_sort_key)
    rows, previous_average, previous_position = [], None, 0
    for index, report in enumerate(reports, 1):
        if previous_position == 0 or report.average_score != previous_average:
            previous_position = index
            previous_average = report.average_score
        scores = {
            subject["subject"]: subject.get("score")
            for subject in report.snapshot.get("subjects", [])
        }
        rows.append({
            "report": report,
            "name": report.student.user.get_full_name() or report.student.user.username,
            "identifier": report.student.identifier,
            "scores": [scores.get(subject) for subject in subject_names],
            "position": report.position or previous_position,
        })
    return subject_names, rows


def render_order_of_merit_pdf(*, school_class, term, reports):
    subjects, rows = build_class_report_rows(reports)
    return _render_template("reports/order_of_merit_pdf.html", {
        "school_class": school_class, "term": term, "subjects": subjects, "rows": rows,
    })


def render_promotion_list_pdf(*, school_class, term, reports):
    _, rows = build_class_report_rows(reports)
    return _render_template("reports/promotion_list_pdf.html", {
        "school_class": school_class, "term": term, "rows": rows,
    })

