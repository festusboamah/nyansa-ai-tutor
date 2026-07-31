from io import BytesIO

from django.template.loader import render_to_string
from xhtml2pdf import pisa


def render_report_pdf(report):
    html = render_to_string("reports/report_pdf.html", {"report": report, "data": report.snapshot})
    output = BytesIO()
    result = pisa.CreatePDF(html, dest=output, encoding="utf-8")
    if result.err:
        raise RuntimeError("The report PDF could not be generated.")
    return output.getvalue()

