"""Build the VALUE implementation methodology from its maintained Markdown."""

from __future__ import annotations

import argparse
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import HRFlowable, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from build_value_101_pdf import BLUE, MUTED, PALE_BLUE, RULE, add_markdown, make_styles


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs" / "methodology" / "VALUE_METHODOLOGY.md"
DEFAULT_OUTPUT = ROOT / "output" / "pdf" / "VALUE_Methodology.pdf"


def draw_page(canvas: object, doc: object) -> None:
    canvas.saveState()
    width, height = A4
    if doc.page > 1:
        canvas.setStrokeColor(RULE)
        canvas.setLineWidth(0.5)
        canvas.line(20 * mm, height - 15 * mm, width - 20 * mm, height - 15 * mm)
        canvas.setFont("Value101Sans", 8)
        canvas.setFillColor(MUTED)
        canvas.drawString(20 * mm, height - 12 * mm, "VALUE")
        canvas.drawRightString(width - 20 * mm, height - 12 * mm, "Implementation methodology")
    canvas.setStrokeColor(RULE)
    canvas.line(20 * mm, 14 * mm, width - 20 * mm, 14 * mm)
    canvas.setFont("Value101Sans", 8)
    canvas.setFillColor(MUTED)
    canvas.drawString(20 * mm, 9.5 * mm, "VALUE 0.7.0-alpha.1 | 9 October 2026")
    canvas.drawRightString(width - 20 * mm, 9.5 * mm, str(doc.page))
    canvas.restoreState()


def build(output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    styles = make_styles()
    styles["body"].fontSize = 8.8
    styles["body"].leading = 12.5
    styles["body"].allowWidows = False
    styles["body"].allowOrphans = False
    styles["h2"].fontSize = 16
    styles["h2"].leading = 19
    for heading in ("h1", "h2", "h3"):
        styles[heading].keepWithNext = True
    doc = SimpleDocTemplate(
        str(output),
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=23 * mm,
        bottomMargin=20 * mm,
        title="VALUE methodology",
        author="Hanzhe Xing",
        subject="Executable methods, contracts and scientific boundaries of VALUE",
        creator="VALUE documentation build",
    )
    story: list[object] = [
        Spacer(1, 18 * mm),
        Paragraph("VALUE", styles["small"]),
        Spacer(1, 5 * mm),
        Paragraph("VALUE runtime implementation overview", styles["h1"]),
        Paragraph(
            "Executable market, storage, expansion, planning and fixed-zonal methods",
            styles["body"],
        ),
        HRFlowable(width="100%", thickness=2, color=BLUE, spaceBefore=6, spaceAfter=18),
        Table(
            [
                [Paragraph("Model clock", styles["small"]), Paragraph("30-minute UTC periods; fixed 365-day model year; 17,520 periods", styles["body"])],
                [Paragraph("Core market", styles["small"]), Paragraph("National bid at cost with current-period balancing", styles["body"])],
                [Paragraph("Annual chain", styles["small"]), Paragraph("PSM, expansion headroom, owner investment, planning and state transition", styles["body"])],
                [Paragraph("Network option", styles["small"]), Paragraph("Post-thesis fixed-zonal transport and pay-as-bid redispatch", styles["body"])],
                [Paragraph("Document boundary", styles["small"]), Paragraph("Edition 0.4.1; corrected profile by default; compatibility settings stated alongside", styles["body"])],
            ],
            colWidths=[38 * mm, 117 * mm],
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
        Paragraph("Hanzhe Xing", styles["small"]),
        Paragraph("Software methods reference, generated from the maintained source", styles["small"]),
        PageBreak(),
        Spacer(1, 8 * mm),
    ]
    add_markdown(story, SOURCE, styles, doc.width, skip_title=True)
    # Let heading keepWithNext bind to the following paragraph itself.
    # A nested one-paragraph KeepTogether can otherwise strand a heading.
    story = [
        item._content[0]
        if isinstance(item, KeepTogether)
        and len(item._content) == 1
        and isinstance(item._content[0], Paragraph)
        else item
        for item in story
    ]
    doc.build(story, onFirstPage=draw_page, onLaterPages=draw_page)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    arguments = parser.parse_args()
    build(arguments.output.resolve())
    print(arguments.output.resolve())


if __name__ == "__main__":
    main()
