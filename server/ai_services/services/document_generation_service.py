"""
Document Generation Service

Renders a structured JSON document specification into binary document bytes using
native Python libraries. No external API calls — all rendering is local.

Supported formats: pdf (reportlab), docx (python-docx), xlsx (openpyxl), pptx (python-pptx).
These libraries are available in the 'files' dependency profile.

Spec schema expected from the LLM:
  {
    "title": str,
    "sections": [
      {
        "heading": str,
        "body": str,                    # optional paragraph text
        "table": [[str, ...]],          # optional; first row = header
        "bullet_points": [str, ...]     # optional
      }
    ],
    "metadata": {"author": str, "date": str}
  }
"""

import io
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

MIME_TYPES: Dict[str, str] = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}


class DocumentRenderer:
    """Render a document spec dict to bytes in the requested format."""

    def render(self, spec: Dict[str, Any], fmt: str) -> bytes:
        fmt = fmt.lower()
        if fmt == "pdf":
            return self._render_pdf(spec)
        if fmt == "docx":
            return self._render_docx(spec)
        if fmt == "xlsx":
            return self._render_xlsx(spec)
        if fmt == "pptx":
            return self._render_pptx(spec)
        raise ValueError(f"Unsupported document format: {fmt!r}. Supported: pdf, docx, xlsx, pptx")

    # ------------------------------------------------------------------
    # PDF — reportlab
    # ------------------------------------------------------------------

    def _render_pdf(self, spec: Dict[str, Any]) -> bytes:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        from reportlab.lib import colors

        buf = io.BytesIO()
        doc = SimpleDocTemplate(
            buf, pagesize=A4,
            topMargin=2 * cm, bottomMargin=2 * cm,
            leftMargin=2.5 * cm, rightMargin=2.5 * cm,
        )
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle("DocTitle", parent=styles["Title"], fontSize=18, spaceAfter=12)
        h1_style = ParagraphStyle("DocH1", parent=styles["Heading1"], fontSize=14, spaceAfter=6)
        bullet_style = ParagraphStyle("DocBullet", parent=styles["BodyText"], leftIndent=20, bulletIndent=10)

        story = []
        story.append(Paragraph(spec.get("title", "Document"), title_style))

        meta = spec.get("metadata", {})
        meta_parts = []
        if meta.get("author"):
            meta_parts.append(f"Author: {meta['author']}")
        if meta.get("date"):
            meta_parts.append(f"Date: {meta['date']}")
        if meta_parts:
            story.append(Paragraph("  |  ".join(meta_parts), styles["Italic"]))
        story.append(Spacer(1, 0.5 * cm))

        for section in spec.get("sections", []):
            if section.get("heading"):
                story.append(Paragraph(section["heading"], h1_style))
            if section.get("body"):
                story.append(Paragraph(section["body"], styles["BodyText"]))
                story.append(Spacer(1, 0.3 * cm))
            for point in section.get("bullet_points") or []:
                story.append(Paragraph(f"• {point}", bullet_style))
            if section.get("bullet_points"):
                story.append(Spacer(1, 0.3 * cm))
            table_data = section.get("table")
            if table_data and len(table_data) > 0:
                # Ensure all cells are strings
                safe_data = [[str(cell) for cell in row] for row in table_data]
                tbl = Table(safe_data, repeatRows=1)
                tbl.setStyle(TableStyle([
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4472C4")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#EBF0FA")]),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]))
                story.append(tbl)
                story.append(Spacer(1, 0.3 * cm))

        doc.build(story)
        return buf.getvalue()

    # ------------------------------------------------------------------
    # DOCX — python-docx
    # ------------------------------------------------------------------

    def _render_docx(self, spec: Dict[str, Any]) -> bytes:
        from docx import Document
        from docx.enum.text import WD_ALIGN_PARAGRAPH

        doc = Document()
        title_para = doc.add_heading(spec.get("title", "Document"), level=0)
        title_para.alignment = WD_ALIGN_PARAGRAPH.CENTER

        meta = spec.get("metadata", {})
        meta_parts = []
        if meta.get("author"):
            meta_parts.append(f"Author: {meta['author']}")
        if meta.get("date"):
            meta_parts.append(f"Date: {meta['date']}")
        if meta_parts:
            p = doc.add_paragraph()
            run = p.add_run("  |  ".join(meta_parts))
            run.italic = True
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER

        doc.add_paragraph()

        for section in spec.get("sections", []):
            if section.get("heading"):
                doc.add_heading(section["heading"], level=1)
            if section.get("body"):
                doc.add_paragraph(section["body"])
            for point in section.get("bullet_points") or []:
                doc.add_paragraph(point, style="List Bullet")
            table_data = section.get("table")
            if table_data and len(table_data) > 1:
                headers = table_data[0]
                rows = table_data[1:]
                tbl = doc.add_table(rows=1 + len(rows), cols=len(headers))
                tbl.style = "Table Grid"
                hdr_cells = tbl.rows[0].cells
                for i, h in enumerate(headers):
                    hdr_cells[i].text = str(h)
                    hdr_cells[i].paragraphs[0].runs[0].bold = True
                for r_idx, row in enumerate(rows):
                    for c_idx, val in enumerate(row):
                        tbl.rows[r_idx + 1].cells[c_idx].text = str(val)
                doc.add_paragraph()

        buf = io.BytesIO()
        doc.save(buf)
        return buf.getvalue()

    # ------------------------------------------------------------------
    # XLSX — openpyxl
    # ------------------------------------------------------------------

    def _render_xlsx(self, spec: Dict[str, Any]) -> bytes:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment

        wb = Workbook()
        wb.remove(wb.active)  # Remove the default blank sheet

        header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
        alt_fill = PatternFill(start_color="EBF0FA", end_color="EBF0FA", fill_type="solid")

        # Summary sheet
        ws = wb.create_sheet("Summary")
        ws["A1"] = spec.get("title", "Document")
        ws["A1"].font = Font(size=16, bold=True)
        meta = spec.get("metadata", {})
        meta_parts = []
        if meta.get("author"):
            meta_parts.append(f"Author: {meta['author']}")
        if meta.get("date"):
            meta_parts.append(f"Date: {meta['date']}")
        if meta_parts:
            ws["A2"] = "  |  ".join(meta_parts)
            ws["A2"].font = Font(italic=True)
        ws.column_dimensions["A"].width = 80

        row = 4
        for section in spec.get("sections", []):
            if section.get("heading"):
                ws.cell(row=row, column=1, value=section["heading"]).font = Font(bold=True, size=12)
                row += 1
            if section.get("body"):
                ws.cell(row=row, column=1, value=section["body"])
                row += 1
            for point in section.get("bullet_points") or []:
                ws.cell(row=row, column=1, value=f"• {point}")
                row += 1
            row += 1

        # Data sheets — one per section that has a table
        for idx, section in enumerate(spec.get("sections", [])):
            table_data = section.get("table")
            if not table_data or len(table_data) < 1:
                continue
            sheet_name = (section.get("heading") or f"Sheet{idx + 1}")[:31]
            ws_data = wb.create_sheet(sheet_name)
            for r_idx, tbl_row in enumerate(table_data):
                for c_idx, val in enumerate(tbl_row):
                    cell = ws_data.cell(row=r_idx + 1, column=c_idx + 1, value=str(val))
                    if r_idx == 0:
                        cell.font = Font(bold=True, color="FFFFFF")
                        cell.fill = header_fill
                        cell.alignment = Alignment(horizontal="center")
                    elif r_idx % 2 == 0:
                        cell.fill = alt_fill
            # Auto-fit column widths
            for col in ws_data.columns:
                max_len = max((len(str(c.value or "")) for c in col), default=10)
                ws_data.column_dimensions[col[0].column_letter].width = min(max_len + 4, 50)

        buf = io.BytesIO()
        wb.save(buf)
        return buf.getvalue()

    # ------------------------------------------------------------------
    # PPTX — python-pptx
    # ------------------------------------------------------------------

    def _render_pptx(self, spec: Dict[str, Any]) -> bytes:
        from pptx import Presentation
        from pptx.util import Inches, Pt
        from pptx.dml.color import RGBColor

        prs = Presentation()
        prs.slide_width = Inches(13.33)
        prs.slide_height = Inches(7.5)

        # Title slide
        title_layout = prs.slide_layouts[0]
        slide = prs.slides.add_slide(title_layout)
        slide.shapes.title.text = spec.get("title", "Document")
        meta = spec.get("metadata", {})
        meta_parts = []
        if meta.get("author"):
            meta_parts.append(meta["author"])
        if meta.get("date"):
            meta_parts.append(meta["date"])
        if len(slide.placeholders) > 1 and meta_parts:
            slide.placeholders[1].text = "  |  ".join(meta_parts)

        # Content slides — one per section
        content_layout = prs.slide_layouts[1]
        blank_layout = prs.slide_layouts[6]
        for section in spec.get("sections", []):
            slide = prs.slides.add_slide(content_layout)
            slide.shapes.title.text = section.get("heading", "")
            tf = slide.placeholders[1].text_frame
            tf.clear()

            body = section.get("body", "")
            if body:
                p = tf.paragraphs[0]
                p.text = body
                p.font.size = Pt(14)

            for point in section.get("bullet_points") or []:
                p = tf.add_paragraph()
                p.text = point
                p.level = 1
                p.font.size = Pt(13)

            # Tables go on their own slide
            table_data = section.get("table")
            if table_data and len(table_data) > 1:
                tbl_slide = prs.slides.add_slide(blank_layout)
                rows = len(table_data)
                cols = len(table_data[0])
                tbl = tbl_slide.shapes.add_table(
                    rows, cols,
                    Inches(0.5), Inches(1.5),
                    Inches(12.33), Inches(min(rows * 0.4 + 0.5, 5.5)),
                ).table
                for r, row in enumerate(table_data):
                    for c, val in enumerate(row):
                        cell = tbl.cell(r, c)
                        cell.text = str(val)
                        if r == 0:
                            cell.text_frame.paragraphs[0].font.bold = True
                            cell.text_frame.paragraphs[0].font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
                            cell.fill.solid()
                            cell.fill.fore_color.rgb = RGBColor(0x44, 0x72, 0xC4)

        buf = io.BytesIO()
        prs.save(buf)
        return buf.getvalue()
