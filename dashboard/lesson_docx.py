from io import BytesIO

from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.oxml import OxmlElement


def _add_table(document, rows, header=None):
    table = document.add_table(rows=0, cols=2 if header is None else len(header))
    table.style = "Table Grid"
    table.autofit = False
    widths = (2, 8.69) if header is None else (1.05, 2.3, 4.5, 2.84)
    for column, width in zip(table.columns, widths):
        column.width = Inches(width)
    if header:
        cells = table.add_row().cells
        for index, text in enumerate(header):
            cells[index].text = str(text)
            cells[index].width = Inches(widths[index])
        table.rows[0]._tr.get_or_add_trPr().append(OxmlElement("w:tblHeader"))
    for row in rows:
        cells = table.add_row().cells
        for index, text in enumerate(row):
            cells[index].text = "" if text is None else str(text)
            cells[index].width = Inches(widths[index])
    return table


def build_lesson_note_docx(note, lesson_data):
    """Builds a .docx reproducing the GES weekly-lesson-plan layout, from the
    same LessonNote fields the PDF export reads."""
    document = Document()
    section = document.sections[0]
    section.page_width, section.page_height = Inches(11.69), Inches(8.27)
    section.left_margin = section.right_margin = Inches(.5)
    section.top_margin = section.bottom_margin = Inches(.5)
    document.styles["Normal"].font.size = Pt(10)
    document.styles["Normal"].font.name = "Arial"
    document.styles["Normal"].paragraph_format.space_after = Pt(2)
    for style in ("Title", "Heading 1", "Heading 2"):
        document.styles[style].font.color.rgb = RGBColor(0, 0, 0)
    document.add_heading(f"{note.subject.name}: {note.strand_topic}", level=1)

    _add_table(document, [
        ("Teacher Name", note.display_teacher_name),
        ("Class", note.class_level),
        ("Class Size", note.class_size or "-"),
        ("Duration", note.duration or "-"),
        ("Subject", note.subject.name),
        ("Reference", note.reference or "-"),
        ("Week", note.week_label),
        ("Week Ending", note.week_ending.strftime("%b %d, %Y")),
        ("Strand", note.strand_topic),
        ("Sub-Strand", note.sub_strand or "-"),
        ("Content Standard", note.content_standard or "-"),
        ("Indicator", note.learning_indicator),
        ("Performance Indicator(s)", note.performance_indicator or "-"),
        ("Core Competencies", note.core_competencies or "-"),
        ("Teaching/Learning Resources", note.resources or "-"),
    ])

    document.add_heading("Daily Lesson Breakdown", level=2)
    days = (lesson_data or {}).get("days", [])
    _add_table(
        document,
        [(day.get("day", ""), day.get("starter", ""), day.get("main", ""), day.get("reflection", "")) for day in days],
        header=("Day / Date", "Phase 1: Starter", "Phase 2: Main", "Phase 3: Reflection"),
    )

    from .scheme_docx import add_curriculum_sources
    add_curriculum_sources(document, lesson_data or {})
    document.add_heading("Headteacher Vetting", level=2)
    vetting = _add_table(document, [
        ("Headteacher Name", note.reviewed_by.user.get_full_name() or note.reviewed_by.user.username if note.date_vetted and note.reviewed_by else "________________________"),
        ("Date Vetted", note.date_vetted.strftime("%d/%m/%Y") if note.date_vetted else "________________________"),
        ("Headteacher Signature", "________________________"),
        ("Remarks", "________________________________________________"),
    ])
    for row in vetting.rows[:-1]:
        for cell in row.cells:
            for paragraph in cell.paragraphs:
                paragraph.paragraph_format.keep_with_next = True

    buffer = BytesIO()
    document.save(buffer)
    buffer.seek(0)
    return buffer
