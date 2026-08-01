from io import BytesIO

from django.template.loader import render_to_string
from xhtml2pdf import pisa


def render_receipt_pdf(receipt):
    html = render_to_string("finance/receipt_pdf.html", {"receipt": receipt, "data": receipt.snapshot})
    output = BytesIO()
    result = pisa.CreatePDF(html, dest=output, encoding="utf-8")
    if result.err:
        raise RuntimeError("The receipt PDF could not be generated.")
    return output.getvalue()

