import unicodedata
import logging
from typing import Dict, Any

from .base import BaseRenderer

logger = logging.getLogger(__name__)


class PDFRenderer(BaseRenderer):
    """Render a document spec to PDF bytes using reportlab."""

    # Characters that LLMs routinely emit but that fall outside Helvetica's
    # WinAnsi glyph set, causing ReportLab to render them as black boxes (■).
    _PDF_CHAR_MAP = str.maketrans({
        '–': '-',    # en dash
        '—': '-',    # em dash
        '―': '-',    # horizontal bar
        '‘': "'",    # left single quotation mark
        '’': "'",    # right single quotation mark
        '‚': ',',    # single low-9 quotation mark
        '“': '"',    # left double quotation mark
        '”': '"',    # right double quotation mark
        '„': '"',    # double low-9 quotation mark
        '…': '...', # horizontal ellipsis
        ' ': ' ',   # non-breaking space
        '­': '',    # soft hyphen
        '•': '*',   # bullet
        '−': '-',   # minus sign
        '×': 'x',   # multiplication sign
        '÷': '/',   # division sign
    })

    # Unicode ranges that are emoji or emoji-modifier codepoints.
    # Characters in these ranges have no Helvetica glyph and no useful ASCII
    # decomposition, so they are stripped silently rather than shown as '?'.
    _EMOJI_RANGES = (
        (0x2194, 0x2199),  # arrows
        (0x2300, 0x23FF),  # Misc Technical (clocks, hourglasses, etc.)
        (0x2600, 0x27BF),  # Misc Symbols + Dingbats
        (0x2B00, 0x2BFF),  # Misc Symbols and Arrows
        (0xFE00, 0xFE0F),  # Variation Selectors (emoji presentation VS-16 etc.)
        (0x1F000, 0x1FAFF),  # Mahjong/Domino tiles through Symbols Extended-A
        (0xE0000, 0xE01FF),  # Tags (used in flag emoji sequences)
    )
    # Zero-width joiners and similar invisible connectors used in emoji sequences
    _EMOJI_JOINERS = frozenset([0x200D, 0x20E3, 0xFE0F])

    @classmethod
    def _is_emoji(cls, cp: int) -> bool:
        if cp in cls._EMOJI_JOINERS:
            return True
        return any(lo <= cp <= hi for lo, hi in cls._EMOJI_RANGES)

    @staticmethod
    def _sanitize_pdf_text(text: str) -> str:
        text = text.translate(PDFRenderer._PDF_CHAR_MAP)
        result = []
        for ch in text:
            cp = ord(ch)
            if cp <= 0x00FF:
                result.append(ch)
            elif PDFRenderer._is_emoji(cp):
                pass  # strip silently — no Helvetica glyph, no useful decomposition
            else:
                normalized = unicodedata.normalize('NFKD', ch)
                ascii_part = normalized.encode('ascii', 'ignore').decode('ascii')
                result.append(ascii_part or '?')
        return ''.join(result)

    def render(self, spec: Dict[str, Any]) -> bytes:
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.platypus import Image as RLImage
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        from reportlab.lib import colors

        top_margin    = self._get('pdf', 'margins', 'top',    default=2) * cm
        bottom_margin = self._get('pdf', 'margins', 'bottom', default=2) * cm
        left_margin   = self._get('pdf', 'margins', 'left',   default=2.5) * cm
        right_margin  = self._get('pdf', 'margins', 'right',  default=2.5) * cm

        import io
        pagesize = (
            landscape(A4)
            if self._pdf_should_use_landscape(spec, A4, left_margin)
            else A4
        )
        buf = io.BytesIO()
        doc = SimpleDocTemplate(
            buf, pagesize=pagesize,
            topMargin=top_margin, bottomMargin=bottom_margin,
            leftMargin=left_margin, rightMargin=right_margin,
        )
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            "DocTitle", parent=styles["Title"],
            fontSize=self._get('pdf', 'typography', 'title_size', default=18),
            spaceAfter=self._get('pdf', 'typography', 'title_space_after', default=12),
        )
        h1_style = ParagraphStyle(
            "DocH1", parent=styles["Heading1"],
            fontSize=self._get('pdf', 'typography', 'heading1_size', default=14),
            spaceAfter=self._get('pdf', 'typography', 'heading1_space_after', default=6),
        )
        bullet_style = ParagraphStyle(
            "DocBullet", parent=styles["BodyText"],
            leftIndent=self._get('pdf', 'typography', 'bullet_indent', default=20),
            bulletIndent=self._get('pdf', 'typography', 'bullet_marker_indent', default=10),
        )

        s = self._sanitize_pdf_text
        story = []
        story.append(Paragraph(s(spec.get("title", "Document")), title_style))

        meta_line = self._build_meta_line(spec)
        if meta_line:
            story.append(Paragraph(s(meta_line), styles["Italic"]))
        story.append(Spacer(1, 0.5 * cm))

        for section in spec.get("sections", []):
            if section.get("heading"):
                story.append(Paragraph(s(section["heading"]), h1_style))
            if section.get("body"):
                story.append(Paragraph(s(section["body"]), styles["BodyText"]))
                story.append(Spacer(1, 0.3 * cm))
            for point in section.get("bullet_points") or []:
                story.append(Paragraph(f"• {s(point)}", bullet_style))
            if section.get("bullet_points"):
                story.append(Spacer(1, 0.3 * cm))
            table_data = section.get("table")
            if table_data and len(table_data) > 0:
                tbl = self._build_pdf_table(
                    table_data=table_data,
                    styles=styles,
                    available_width=doc.width,
                )
                story.append(tbl)
                story.append(Spacer(1, 0.3 * cm))
            chart_data = section.get("chart")
            if chart_data:
                try:
                    from .chart_image import render_chart_to_png

                    png_bytes = render_chart_to_png(chart_data, width_px=500, height_px=280)
                    img_buf = io.BytesIO(png_bytes)
                    story.append(RLImage(img_buf, width=500, height=280))
                    story.append(Spacer(1, 0.4 * cm))
                except Exception as exc:
                    logger.warning("Chart rendering failed for PDF section: %s", exc)

        doc.build(story)
        return buf.getvalue()

    def _pdf_should_use_landscape(self, spec: Dict[str, Any], portrait_pagesize, horizontal_margin: float) -> bool:
        portrait_width = portrait_pagesize[0] - (2 * horizontal_margin)
        threshold = self._get('pdf', 'table', 'landscape_threshold_cols', default=7)
        for section in spec.get("sections", []):
            table_data = section.get("table")
            if not table_data:
                continue
            normalized_rows = self._normalize_table_rows(table_data)
            if normalized_rows and len(normalized_rows[0]) >= threshold:
                return True
            if self._estimate_table_width(table_data) > portrait_width:
                return True
        return False

    def _build_pdf_table(self, table_data, styles, available_width: float):
        from reportlab.lib import colors
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.pdfbase.pdfmetrics import stringWidth
        from reportlab.platypus import Paragraph, Table, TableStyle

        font_body        = self._get('pdf', 'fonts',  'body',        default='Helvetica')
        font_header      = self._get('pdf', 'fonts',  'header',      default='Helvetica-Bold')
        color_header_bg  = self._get('pdf', 'colors', 'header_bg',   default='#4472C4')
        color_header_text = self._get('pdf', 'colors', 'header_text', default='white')
        color_alt_row    = self._get('pdf', 'colors', 'alt_row_bg',  default='#EBF0FA')
        color_grid       = self._get('pdf', 'colors', 'grid',        default='grey')
        cell_padding     = self._get('pdf', 'table',  'cell_padding', default=8)

        normalized_rows = self._normalize_table_rows(table_data)
        column_count = len(normalized_rows[0]) if normalized_rows else 0
        font_size = self._resolve_table_font_size(column_count)

        body_style = ParagraphStyle(
            "DocTableBody",
            parent=styles["BodyText"],
            fontName=font_body,
            fontSize=font_size,
            leading=font_size + 2,
            wordWrap="CJK",
        )
        header_text_color = (
            colors.HexColor(color_header_text)
            if color_header_text.startswith('#')
            else getattr(colors, color_header_text, colors.white)
        )
        header_style = ParagraphStyle(
            "DocTableHeader",
            parent=body_style,
            fontName=font_header,
            textColor=header_text_color,
        )

        col_widths = self._compute_pdf_col_widths(
            normalized_rows=normalized_rows,
            available_width=available_width,
            font_size=font_size,
            string_width=stringWidth,
            font_body=font_body,
            font_header=font_header,
            cell_padding=cell_padding,
        )
        wrapped_rows = [
            [
                Paragraph(self._sanitize_pdf_text(str(cell)), header_style if row_idx == 0 else body_style)
                for cell in row
            ]
            for row_idx, row in enumerate(normalized_rows)
        ]

        tbl = Table(
            wrapped_rows,
            colWidths=col_widths,
            repeatRows=1,
            splitByRow=1,
            hAlign="LEFT",
        )
        grid_color = (
            colors.HexColor(color_grid)
            if color_grid.startswith('#')
            else getattr(colors, color_grid, colors.grey)
        )
        tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(color_header_bg)),
            ("TEXTCOLOR", (0, 0), (-1, 0), header_text_color),
            ("FONTNAME", (0, 0), (-1, 0), font_header),
            ("FONTSIZE", (0, 0), (-1, -1), font_size),
            ("GRID", (0, 0), (-1, -1), 0.5, grid_color),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor(color_alt_row)]),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), cell_padding / 2),
            ("RIGHTPADDING", (0, 0), (-1, -1), cell_padding / 2),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        return tbl

    def _estimate_table_width(self, table_data) -> float:
        from reportlab.pdfbase.pdfmetrics import stringWidth

        font_body    = self._get('pdf', 'fonts', 'body',   default='Helvetica')
        font_header  = self._get('pdf', 'fonts', 'header', default='Helvetica-Bold')
        cell_padding = self._get('pdf', 'table', 'cell_padding', default=8)
        font_size    = self._get('pdf', 'table', 'font_size',    default=9)

        normalized_rows = self._normalize_table_rows(table_data)
        widths = self._compute_pdf_col_widths(
            normalized_rows=normalized_rows,
            available_width=None,
            font_size=font_size,
            string_width=stringWidth,
            font_body=font_body,
            font_header=font_header,
            cell_padding=cell_padding,
        )
        return sum(widths)

    def _resolve_table_font_size(self, column_count: int) -> int:
        if column_count >= 8:
            return self._get('pdf', 'table', 'min_font_size', default=7)
        if column_count >= 6:
            return self._get('pdf', 'table', 'font_size_many_cols', default=8)
        return self._get('pdf', 'table', 'font_size', default=9)

    def _compute_pdf_col_widths(self, normalized_rows, available_width, font_size: int, string_width,
                                font_body: str = 'Helvetica', font_header: str = 'Helvetica-Bold',
                                cell_padding: int = 8):
        if not normalized_rows:
            return []

        column_count = len(normalized_rows[0])
        widths = []
        min_width   = self._get('pdf', 'table', 'min_col_width',  default=42)
        max_col_ratio = self._get('pdf', 'table', 'max_col_ratio', default=0.28)
        max_width = available_width * max_col_ratio if available_width else None

        for col_idx in range(column_count):
            widest = 0.0
            for row_idx, row in enumerate(normalized_rows):
                font_name = font_header if row_idx == 0 else font_body
                cell_text = row[col_idx]
                widest = max(widest, string_width(cell_text, font_name, font_size))
            padded = widest + cell_padding
            if max_width is not None:
                padded = min(padded, max_width)
            widths.append(max(min_width, padded))

        if available_width and sum(widths) > available_width:
            scale = available_width / sum(widths)
            widths = [max(min_width, width * scale) for width in widths]

            if sum(widths) > available_width:
                even_width = available_width / column_count
                widths = [even_width] * column_count
            else:
                widths[-1] += available_width - sum(widths)

        return widths
