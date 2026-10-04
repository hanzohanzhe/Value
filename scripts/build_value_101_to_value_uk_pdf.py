"""Build an expanded VALUE 101 guide without changing the original PDF."""

from __future__ import annotations

import argparse
import hashlib
import io
import tempfile
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as pdf_canvas
from reportlab.platypus import (
    HRFlowable,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from build_value_101_pdf import (
    BLUE,
    MUTED,
    PALE_BLUE,
    RULE,
    add_markdown,
    draw_any_page,
    make_styles,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE = ROOT / "output" / "pdf" / "VALUE_101_guide.pdf"
DEFAULT_OUTPUT = ROOT / "output" / "pdf" / "VALUE_101_TO_VALUE_UK_guide.pdf"
SOURCE = ROOT / "docs" / "tutorial" / "VALUE_101_TO_VALUE_UK.md"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_supplement(output: Path) -> None:
    styles = make_styles()
    doc = SimpleDocTemplate(
        str(output),
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=23 * mm,
        bottomMargin=20 * mm,
        title="From VALUE 101 to VALUE-UK",
        author="Hanzhe Xing",
        subject="Preparing research data and modules for a full VALUE-UK Study",
        creator="VALUE documentation build",
    )
    story: list[object] = [
        Spacer(1, 18 * mm),
        Paragraph("VALUE", styles["small"]),
        Spacer(1, 5 * mm),
        Paragraph("From VALUE 101 to VALUE-UK", styles["h1"]),
        Paragraph(
            "A practical route from the teaching system to a complete British research Study",
            styles["body"],
        ),
        HRFlowable(width="100%", thickness=2, color=BLUE, spaceBefore=6, spaceAfter=18),
        Table(
            [
                [Paragraph("Starting point", styles["small"]), Paragraph("A completed VALUE 101 one-day Run", styles["body"])],
                [Paragraph("Main task", styles["small"]), Paragraph("Install a validated VALUE-UK Data Pack and save a research Study", styles["body"])],
                [Paragraph("Full clock", styles["small"]), Paragraph("17,520 half-hours per complete model year", styles["body"])],
                [Paragraph("Method changes", styles["small"]), Paragraph("Versioned Module bundles or declared extensions", styles["body"])],
                [Paragraph("Scientific boundary", styles["small"]), Paragraph("Claims follow the selected data, modules, parameters and validation", styles["body"])],
            ],
            colWidths=[38 * mm, 117 * mm],
            style=TableStyle(
                [
                    ("BACKGROUND", (0, 0), (0, -1), PALE_BLUE),
                    ("BOX", (0, 0), (-1, -1), 0.5, RULE),
                    ("INNERGRID", (0, 0), (-1, -1), 0.35, RULE),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                    ("TOPPADDING", (0, 0), (-1, -1), 7),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ]
            ),
        ),
        Spacer(1, 12 * mm),
        Paragraph("Companion to the unchanged VALUE 101 guide", styles["small"]),
        Paragraph("Hanzhe Xing | 25 August 2026", styles["small"]),
        PageBreak(),
        Spacer(1, 10 * mm),
    ]
    add_markdown(story, SOURCE, styles, doc.width, skip_title=True)
    doc.build(story, onFirstPage=draw_any_page, onLaterPages=draw_any_page)


def merge(base: Path, supplement: Path, output: Path) -> None:
    writer = PdfWriter()
    base_pages = len(PdfReader(str(base)).pages)
    for source in (base, supplement):
        for page in PdfReader(str(source)).pages:
            writer.add_page(page)
    width, height = A4
    for index, page in enumerate(writer.pages):
        overlay_buffer = io.BytesIO()
        overlay = pdf_canvas.Canvas(overlay_buffer, pagesize=A4)
        overlay.setFillColor(colors.white)
        overlay.rect(width - 37 * mm, 6.5 * mm, 18 * mm, 6 * mm, stroke=0, fill=1)
        overlay.setFillColor(MUTED)
        overlay.setFont("Value101Sans", 8)
        overlay.drawRightString(width - 20 * mm, 9.5 * mm, str(index + 1))
        if index > base_pages:
            overlay.setStrokeColor(RULE)
            overlay.setLineWidth(0.5)
            overlay.line(20 * mm, height - 15 * mm, width - 20 * mm, height - 15 * mm)
            overlay.drawString(20 * mm, height - 12 * mm, "VALUE 101")
            overlay.drawRightString(width - 20 * mm, height - 12 * mm, "VALUE-UK migration companion")
        overlay.save()
        overlay_buffer.seek(0)
        page.merge_page(PdfReader(overlay_buffer).pages[0])
    writer.add_metadata(
        {
            "/Title": "VALUE 101 and VALUE-UK guide",
            "/Author": "Hanzhe Xing",
            "/Subject": "Teaching VALUE 101 and preparing a full VALUE-UK Study",
            "/Creator": "VALUE documentation build",
        }
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".tmp.pdf")
    with temporary.open("wb") as handle:
        writer.write(handle)
    temporary.replace(output)


def build(base: Path, output: Path) -> None:
    if not base.is_file():
        raise FileNotFoundError(f"Original VALUE 101 guide not found: {base}")
    before = sha256(base)
    with tempfile.TemporaryDirectory(prefix="value-uk-guide-") as folder:
        supplement = Path(folder) / "value-uk-supplement.pdf"
        build_supplement(supplement)
        merge(base, supplement, output)
    after = sha256(base)
    if before != after:
        raise RuntimeError("The original VALUE 101 guide changed during the expanded build")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", type=Path, default=DEFAULT_BASE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    build(args.base.resolve(), args.output.resolve())
    print(args.output.resolve())


if __name__ == "__main__":
    main()
