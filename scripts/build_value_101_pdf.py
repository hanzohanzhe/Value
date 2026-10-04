"""Build the English VALUE 101 handout from its checked Markdown sources."""

from __future__ import annotations

import argparse
import html
import io
import re
from pathlib import Path

import reportlab
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as pdf_canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    ListFlowable,
    ListItem,
    PageBreak,
    Paragraph,
    Preformatted,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from pypdf import PdfReader, PdfWriter


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "output" / "pdf" / "VALUE_101_guide.pdf"
REPORTLAB_FONTS = Path(reportlab.__file__).resolve().parent / "fonts"
pdfmetrics.registerFont(TTFont("Value101Sans", str(REPORTLAB_FONTS / "Vera.ttf")))
pdfmetrics.registerFont(TTFont("Value101Sans-Bold", str(REPORTLAB_FONTS / "VeraBd.ttf")))
NAVY = colors.HexColor("#111B35")
BLUE = colors.HexColor("#2557D6")
TEAL = colors.HexColor("#147D75")
PALE_BLUE = colors.HexColor("#EEF3FF")
PALE_GREY = colors.HexColor("#F4F6F8")
INK = colors.HexColor("#18202A")
MUTED = colors.HexColor("#556170")
RULE = colors.HexColor("#D4DAE4")


def draw_page(canvas: object, doc: object, *, header: bool) -> None:
    canvas.saveState()
    width, height = A4
    if header:
        canvas.setStrokeColor(RULE)
        canvas.setLineWidth(0.5)
        canvas.line(20 * mm, height - 15 * mm, width - 20 * mm, height - 15 * mm)
        canvas.setFont("Value101Sans", 8)
        canvas.setFillColor(MUTED)
        canvas.drawString(20 * mm, height - 12 * mm, "VALUE 101")
        canvas.drawRightString(width - 20 * mm, height - 12 * mm, "Teaching diagnostic")
    canvas.setStrokeColor(RULE)
    canvas.line(20 * mm, 14 * mm, width - 20 * mm, 14 * mm)
    canvas.setFont("Value101Sans", 8)
    canvas.setFillColor(MUTED)
    canvas.drawString(20 * mm, 9.5 * mm, "Local guide | http://127.0.0.1:8800")
    canvas.drawRightString(width - 20 * mm, 9.5 * mm, str(doc.page))
    canvas.restoreState()


def draw_any_page(canvas: object, doc: object) -> None:
    draw_page(canvas, doc, header=False)


def stamp_headers(output: Path) -> None:
    """Apply one consistent header after layout so content cannot hide it."""

    reader = PdfReader(str(output))
    writer = PdfWriter()
    page_count = len(reader.pages)
    for index, page in enumerate(reader.pages):
        if 0 < index < page_count - 1:
            overlay_buffer = io.BytesIO()
            overlay_canvas = pdf_canvas.Canvas(overlay_buffer, pagesize=A4)
            width, height = A4
            overlay_canvas.setStrokeColor(RULE)
            overlay_canvas.setLineWidth(0.5)
            overlay_canvas.line(20 * mm, height - 15 * mm, width - 20 * mm, height - 15 * mm)
            overlay_canvas.setFont("Value101Sans", 8)
            overlay_canvas.setFillColor(MUTED)
            overlay_canvas.drawString(20 * mm, height - 12 * mm, "VALUE 101")
            overlay_canvas.drawRightString(width - 20 * mm, height - 12 * mm, "Local teaching and annual workflow")
            overlay_canvas.save()
            overlay_buffer.seek(0)
            page.merge_page(PdfReader(overlay_buffer).pages[0])
        writer.add_page(page)
    if reader.metadata:
        writer.add_metadata({str(key): str(value) for key, value in reader.metadata.items() if value is not None})
    temporary = output.with_suffix(".stamped.pdf")
    with temporary.open("wb") as handle:
        writer.write(handle)
    temporary.replace(output)


def inline_markup(value: str) -> str:
    value = value.replace("→", "->")
    tokens: dict[str, str] = {}

    def protect(pattern: str, replacement: callable) -> None:
        nonlocal value

        def store(match: re.Match[str]) -> str:
            key = f"@@TOKEN{len(tokens)}@@"
            tokens[key] = replacement(match)
            return key

        value = re.sub(pattern, store, value)

    protect(
        r"\[([^\]]+)\]\(([^)]+)\)",
        lambda match: f'<link href="{html.escape(match.group(2), quote=True)}" color="#2557D6">{html.escape(match.group(1))}</link>',
    )
    protect(
        r"`([^`]+)`",
        lambda match: f'<font name="Value101Sans" color="#173A73">{html.escape(match.group(1))}</font>',
    )
    protect(
        r"\*\*([^*]+)\*\*",
        lambda match: f'<font name="Value101Sans-Bold">{html.escape(match.group(1))}</font>',
    )
    value = html.escape(value)
    for key, replacement in tokens.items():
        value = value.replace(key, replacement)
    return value


def paragraphs(lines: list[str]) -> list[tuple[str, object]]:
    blocks: list[tuple[str, object]] = []
    index = 0
    buffer: list[str] = []

    def flush() -> None:
        if buffer:
            blocks.append(("paragraph", " ".join(item.strip() for item in buffer)))
            buffer.clear()

    while index < len(lines):
        raw = lines[index].rstrip()
        stripped = raw.strip()
        if not stripped:
            flush()
            index += 1
            continue
        if re.match(r"^```[^`]*$", stripped):
            flush()
            index += 1
            code_lines: list[str] = []
            while index < len(lines) and lines[index].strip() != "```":
                code_lines.append(lines[index].rstrip())
                index += 1
            if index < len(lines):
                index += 1
            blocks.append(("code", "\n".join(code_lines)))
            continue
        if stripped.startswith("|") and index + 1 < len(lines) and re.match(r"^\s*\|?\s*:?-+", lines[index + 1]):
            flush()
            rows: list[list[str]] = []
            while index < len(lines) and lines[index].strip().startswith("|"):
                row = [cell.strip() for cell in lines[index].strip().strip("|").split("|")]
                rows.append(row)
                index += 1
            if len(rows) >= 2:
                rows.pop(1)
            blocks.append(("table", rows))
            continue
        heading = re.match(r"^(#{1,3})\s+(.+)$", stripped)
        if heading:
            flush()
            blocks.append((f"h{len(heading.group(1))}", heading.group(2)))
            index += 1
            continue
        numbered = re.match(r"^\d+\.\s+(.+)$", stripped)
        if numbered:
            flush()
            items: list[str] = []
            while index < len(lines):
                match = re.match(r"^\s*\d+\.\s+(.+)$", lines[index])
                if not match:
                    break
                items.append(match.group(1))
                index += 1
            blocks.append(("numbered", items))
            continue
        bullet = re.match(r"^-\s+(.+)$", stripped)
        if bullet:
            flush()
            items = []
            while index < len(lines):
                match = re.match(r"^\s*-\s+(.+)$", lines[index])
                if not match:
                    break
                items.append(match.group(1))
                index += 1
            blocks.append(("bullets", items))
            continue
        buffer.append(stripped)
        index += 1
    flush()
    return blocks


def make_styles() -> dict[str, ParagraphStyle]:
    sample = getSampleStyleSheet()
    return {
        "body": ParagraphStyle(
            "Value101Body",
            parent=sample["BodyText"],
            fontName="Value101Sans",
            fontSize=9.2,
            leading=13.2,
            textColor=INK,
            spaceAfter=6,
            alignment=TA_LEFT,
        ),
        "h1": ParagraphStyle(
            "Value101Title",
            parent=sample["Title"],
            fontName="Value101Sans-Bold",
            fontSize=29,
            leading=33,
            textColor=NAVY,
            alignment=TA_LEFT,
            spaceAfter=8,
        ),
        "h2": ParagraphStyle(
            "Value101H2",
            parent=sample["Heading2"],
            fontName="Value101Sans-Bold",
            fontSize=17,
            leading=21,
            textColor=NAVY,
            spaceBefore=14,
            spaceAfter=7,
            keepWithNext=True,
        ),
        "h3": ParagraphStyle(
            "Value101H3",
            parent=sample["Heading3"],
            fontName="Value101Sans-Bold",
            fontSize=12.5,
            leading=16,
            textColor=BLUE,
            spaceBefore=10,
            spaceAfter=5,
            keepWithNext=True,
        ),
        "small": ParagraphStyle(
            "Value101Small",
            parent=sample["BodyText"],
            fontName="Value101Sans",
            fontSize=8.2,
            leading=11,
            textColor=MUTED,
        ),
        "table": ParagraphStyle(
            "Value101Table",
            parent=sample["BodyText"],
            fontName="Value101Sans",
            fontSize=7.6,
            leading=10.2,
            textColor=INK,
        ),
        "table_header": ParagraphStyle(
            "Value101TableHeader",
            parent=sample["BodyText"],
            fontName="Value101Sans-Bold",
            fontSize=7.6,
            leading=10.2,
            textColor=colors.white,
        ),
        "code": ParagraphStyle(
            "Value101Code",
            parent=sample["Code"],
            fontName="Value101Sans",
            fontSize=8.2,
            leading=11.2,
            textColor=INK,
            backColor=PALE_GREY,
            borderColor=RULE,
            borderWidth=0.5,
            borderPadding=7,
            spaceBefore=3,
            spaceAfter=8,
        ),
    }


def table_flowable(rows: list[list[str]], styles: dict[str, ParagraphStyle], width: float) -> Table:
    columns = max(len(row) for row in rows)
    normalized = [row + [""] * (columns - len(row)) for row in rows]
    content = [[
        Paragraph(inline_markup(cell), styles["table_header"] if row_index == 0 else styles["table"])
        for cell in row
    ] for row_index, row in enumerate(normalized)]
    if columns == 2:
        widths = [width * 0.30, width * 0.70]
    elif columns == 3:
        widths = [width * 0.19, width * 0.33, width * 0.48]
    else:
        widths = [width / columns] * columns
    table = Table(content, colWidths=widths, repeatRows=1, hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Value101Sans-Bold"),
        ("BACKGROUND", (0, 1), (-1, -1), colors.white),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PALE_GREY]),
        ("GRID", (0, 0), (-1, -1), 0.35, RULE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return table


def add_markdown(
    story: list[object],
    path: Path,
    styles: dict[str, ParagraphStyle],
    content_width: float,
    *,
    skip_title: bool = False,
) -> None:
    page_starts = {
        "The 30-minute route",
        "4. Save and run",
        "If something goes wrong",
    }
    for kind, value in paragraphs(path.read_text("utf-8").splitlines()):
        if kind == "h1" and skip_title:
            continue
        if kind in {"h2", "h3"} and value in page_starts:
            space = 25 * mm if value == "4. Save and run" else 12 * mm
            story.extend([PageBreak(), Spacer(1, space)])
        if kind in {"h1", "h2", "h3"}:
            story.append(Paragraph(inline_markup(str(value)), styles[kind]))
        elif kind == "paragraph":
            story.append(KeepTogether([Paragraph(inline_markup(str(value)), styles["body"])]))
        elif kind == "table":
            story.append(table_flowable(value, styles, content_width))
            story.append(Spacer(1, 7))
        elif kind == "code":
            story.append(Preformatted(str(value).replace("→", "->"), styles["code"]))
        elif kind in {"numbered", "bullets"}:
            items = [ListItem(Paragraph(inline_markup(item), styles["body"]), leftIndent=8) for item in value]
            list_kwargs = {
                "bulletType": "1" if kind == "numbered" else "bullet",
                "leftIndent": 20,
                "bulletFontName": "Value101Sans",
                "bulletFontSize": 8.5,
                "bulletColor": BLUE,
                "spaceAfter": 6,
            }
            list_kwargs["start"] = "1" if kind == "numbered" else "-"
            story.append(ListFlowable(items, **list_kwargs))


def build(output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    styles = make_styles()
    doc = SimpleDocTemplate(
        str(output),
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=23 * mm,
        bottomMargin=20 * mm,
        title="VALUE 101 guide",
        author="Hanzhe Xing",
        subject="A first teaching run in the VALUE power-system modelling workbench",
        creator="VALUE documentation build",
    )
    story: list[object] = [
        Spacer(1, 15 * mm),
        Paragraph("VALUE", ParagraphStyle("Wordmark", parent=styles["small"], fontName="Value101Sans-Bold", fontSize=11, leading=13, textColor=BLUE, spaceAfter=10)),
        Paragraph("VALUE 101", styles["h1"]),
        Paragraph("A first run in the VALUE power-system modelling workbench", ParagraphStyle("Subtitle", parent=styles["body"], fontSize=15, leading=20, textColor=MUTED, spaceAfter=16)),
        HRFlowable(width="100%", thickness=2, color=BLUE, spaceBefore=4, spaceAfter=16),
        Table(
            [[Paragraph("Time", styles["small"]), Paragraph("About 30 minutes", styles["body"])],
             [Paragraph("System", styles["small"]), Paragraph("Synthetic single-node market, 2025 and 2026", styles["body"])],
             [Paragraph("Short route", styles["small"]), Paragraph("48 half-hours, production PSM only", styles["body"])],
             [Paragraph("Complete route", styles["small"]), Paragraph("2025 and 2026, 17,520 half-hours per year, PSM-CEM", styles["body"])],
             [Paragraph("Boundary", styles["small"]), Paragraph("Synthetic teaching data. Not a Great Britain benchmark.", styles["body"])],
             [Paragraph("Local address", styles["small"]), Paragraph('<link href="http://127.0.0.1:8800" color="#2557D6">http://127.0.0.1:8800</link>', styles["body"])]],
            colWidths=[35 * mm, 120 * mm],
            style=TableStyle([
                ("BACKGROUND", (0, 0), (0, -1), PALE_BLUE),
                ("BOX", (0, 0), (-1, -1), 0.5, RULE),
                ("INNERGRID", (0, 0), (-1, -1), 0.35, RULE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]),
        ),
        Spacer(1, 12 * mm),
        Paragraph("Prepared for local teaching and demonstration", styles["small"]),
        Paragraph("Hanzhe Xing | 25 August 2026", styles["small"]),
        PageBreak(),
        Spacer(1, 12 * mm),
    ]
    add_markdown(
        story,
        ROOT / "docs" / "tutorial" / "VALUE_101.md",
        styles,
        doc.width,
        skip_title=True,
    )
    quick_styles = make_styles()
    quick_styles["body"].fontSize = 8.5
    quick_styles["body"].leading = 11.2
    quick_styles["body"].spaceAfter = 4
    quick_styles["h2"].fontSize = 14
    quick_styles["h2"].leading = 17
    quick_styles["h2"].spaceBefore = 8
    quick_styles["h2"].spaceAfter = 4
    quick_styles["h3"].fontSize = 11
    quick_styles["h3"].leading = 14
    story.extend([
        PageBreak(),
        Spacer(1, 25 * mm),
        Paragraph("Quick card", styles["h1"]),
        Paragraph("Keep this page beside the laptop during a teaching session.", styles["body"]),
        HRFlowable(width="100%", thickness=1.5, color=TEAL, spaceAfter=10),
    ])
    add_markdown(
        story,
        ROOT / "docs" / "tutorial" / "VALUE_101_QUICK_CARD.md",
        quick_styles,
        doc.width,
        skip_title=True,
    )
    doc.build(story, onFirstPage=draw_any_page, onLaterPages=draw_any_page)
    stamp_headers(output)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    build(args.output.resolve())
    print(args.output.resolve())


if __name__ == "__main__":
    main()
