"""Print source-related paragraphs from a DOCX without modifying the document."""

from __future__ import annotations

import argparse
import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree


WORD = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def paragraphs(path: Path) -> list[str]:
    with zipfile.ZipFile(path) as archive:
        root = ElementTree.fromstring(archive.read("word/document.xml"))
    rows = []
    for paragraph in root.iter(WORD + "p"):
        text = "".join(node.text or "" for node in paragraph.iter(WORD + "t")).strip()
        if text:
            rows.append(text)
    return rows


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("document", type=Path)
    parser.add_argument(
        "--pattern",
        default=(
            r"ERA5|ECMWF|ENTSO|Elexon|National Grid|NESO|BEIS|DESNZ|REPD|"
            r"renewable energy planning|interconnector|demand data|weather data|"
            r"wind profile|solar profile|data source|source of data|cost data"
        ),
    )
    parser.add_argument("--context", type=int, default=1)
    parser.add_argument("--limit", type=int, default=250)
    parser.add_argument("--start", type=int)
    parser.add_argument("--end", type=int)
    args = parser.parse_args()
    values = paragraphs(args.document)
    if args.start is not None or args.end is not None:
        start = max((args.start or 1) - 1, 0)
        end = min(args.end or len(values), len(values))
        for index in range(start, end):
            print(f"[{index + 1}] {values[index]}")
        return
    expression = re.compile(args.pattern, re.IGNORECASE)
    emitted: set[int] = set()
    count = 0
    for index, value in enumerate(values):
        if not expression.search(value):
            continue
        for target in range(max(0, index - args.context), min(len(values), index + args.context + 1)):
            if target in emitted:
                continue
            print(f"[{target + 1}] {values[target]}")
            emitted.add(target)
            count += 1
            if count >= args.limit:
                return
        print("---")


if __name__ == "__main__":
    main()
