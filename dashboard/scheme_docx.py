from io import BytesIO

from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.oxml import OxmlElement


def add_curriculum_sources(document, data):
    if data.get("curriculum_warning"):
        document.add_paragraph(data["curriculum_warning"])
    sources = data.get("curriculum_sources", [])
    for filename in dict.fromkeys(s["filename"] for s in sources):
        pages = ", ".join(str(s["page"]) for s in sources if s["filename"] == filename)
        document.add_paragraph(f"Curriculum reference: {filename}. PDF pages: {pages}.")


def build_scheme_of_learning_docx(scheme, scheme_data):
    document = Document()
    section = document.sections[0]
    section.page_width, section.page_height = Inches(11.69), Inches(8.27)
    section.left_margin = section.right_margin = Inches(.5)
    section.top_margin = section.bottom_margin = Inches(.5)
    document.styles["Normal"].font.size = Pt(10)
    document.styles["Normal"].font.name = "Arial"
    document.styles["Heading 1"].font.color.rgb = RGBColor(0, 0, 0)
    yearly = getattr(scheme, "plan_type", "TERMLY") == "YEARLY"
    document.add_heading(f"{'Yearly' if yearly else 'Termly'} Scheme of Learning {scheme.subject.name}", level=1)
    document.add_paragraph(f"Class: {scheme.class_level}    Academic year: {getattr(scheme, 'academic_year', '')}    {scheme.term}")
    weeks = (scheme_data or {}).get("weeks", [])
    if yearly:
        fields = ("week", "term_1", "term_2", "term_3")
        headers = ("Week", "First Term", "Second Term", "Third Term")
        widths = (.55, 3.38, 3.38, 3.38)
    elif weeks and "strand" in weeks[0]:
        fields = ("week", "strand", "sub_strand", "content_standard", "indicators", "resources")
        headers = ("Week", "Strand", "Sub-Strand", "Content Standard", "Indicators", "Resources")
        widths = (.55, 1.4, 1.4, 2.35, 3.1, 1.89)
    else:
        fields, headers, widths = ("week", "topic"), ("Week", "Topic"), (.6, 10.09)
    table = document.add_table(rows=1, cols=len(fields))
    table.style = "Table Grid"
    table.autofit = False
    for column, width in zip(table.columns, widths):
        column.width = Inches(width)
    for cell, header, width in zip(table.rows[0].cells, headers, widths):
        cell.text = header
        cell.width = Inches(width)
    table.rows[0]._tr.get_or_add_trPr().append(OxmlElement("w:tblHeader"))
    for week in weeks:
        for cell, field, width in zip(table.add_row().cells, fields, widths):
            cell.text = str(week.get(field, ""))
            cell.width = Inches(width)
    add_curriculum_sources(document, scheme_data or {})
    buffer = BytesIO()
    document.save(buffer)
    buffer.seek(0)
    return buffer
