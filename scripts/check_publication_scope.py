#!/usr/bin/env python3
"""Read-only VALUE publication gate; stdlib only, never imports model code.

Run after website/build.py and the final source-manifest refresh:
  python3 scripts/check_publication_scope.py --root . --report /tmp/scope.json

The report is internal review evidence. Paths are repository-relative. Exit 0
passes, 1 rejects a candidate, 2 means the root/config could not be loaded.
PDF text review is delegated to the artifact review manifest, never inferred
from a successful checksum. HTML text and DOCX XML text are inspected here.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import zipfile
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from xml.etree import ElementTree

PRIVATE_MARKER = re.compile(r"value[-_]single|SDX_VALUE_ENGINE|Electrace", re.I)
CHAPTER_IDS = ["introduction", "datasets", "core_weather", "core",
               "national_alternatives", "r029_cem", "transmission",
               "optional_modules", "appendix"]
READABLE_SUFFIXES = {".html", ".htm", ".md", ".txt", ".json", ".xml",
                     ".svg", ".css", ".js", ".mjs", ".csv"}
CODE_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".mjs", ".cjs"}


class ScopeError(ValueError):
    pass


class VisibleHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.hidden += 1
        if not self.hidden:
            # Also review accessible descriptions and linked filenames.
            self.parts.extend(value for key, value in attrs
                              if key in {"alt", "title", "aria-label", "href"}
                              and value)

    def handle_endtag(self, tag):
        if tag in {"script", "style"} and self.hidden:
            self.hidden -= 1

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def html_text(value):
    parser = VisibleHTML()
    parser.feed(value)
    return "".join(parser.parts)


def file_digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def numbered_markdown(value, number):
    """The one permitted generation change: automatic top-level numbering."""
    lines = []
    for line in value.splitlines():
        if line.startswith("# "):
            line = "# " + str(number) + " " + re.sub(r"^\d+[. ]*", "", line[2:])
        lines.append(line)
    return "\n".join(lines).strip() + "\n"


class Review:
    def __init__(self, root, config):
        self.root = Path(root).resolve()
        self.config = config
        self.errors = []
        self.checks = []
        self.scanned = set()

    def path(self, relative, kind="file"):
        if not isinstance(relative, str) or not relative or "\\" in relative:
            raise ScopeError("Invalid relative path")
        pure = PurePosixPath(relative)
        if pure.is_absolute() or any(p in {".", ".."} for p in relative.split("/")):
            raise ScopeError(f"Path escapes scope or is non-canonical: {relative}")
        current = self.root
        for part in pure.parts:
            current = current / part
            if current.is_symlink():
                raise ScopeError(f"Symlink is not allowed: {relative}")
        if not current.resolve().is_relative_to(self.root):
            raise ScopeError(f"Path escapes repository: {relative}")
        exists = current.is_dir() if kind == "directory" else current.is_file()
        if not exists:
            raise ScopeError(f"Missing {kind}: {relative}")
        return current

    def json(self, relative):
        return json.loads(self.path(relative).read_text(encoding="utf-8"))

    def require(self, condition, message):
        if not condition:
            raise ScopeError(message)

    def check(self, name, action):
        before = len(self.errors)
        try:
            detail = action()
        except (ScopeError, OSError, ValueError, KeyError, TypeError,
                zipfile.BadZipFile, ElementTree.ParseError) as error:
            self.errors.append({"check": name, "message": str(error)})
            detail = None
        self.checks.append({"name": name, "passed": len(self.errors) == before,
                            "detail": detail})

    def scan(self, relative):
        if relative in self.scanned:
            return
        path = self.path(relative)
        self.scanned.add(relative)
        self.require(not PRIVATE_MARKER.search(path.name),
                     f"Private product filename: {relative}")
        if path.suffix.lower() == ".pdf":
            return  # Explicit review delegation; no PDF parser dependency.
        if path.suffix.lower() == ".docx":
            with zipfile.ZipFile(path) as archive:
                parts = []
                for name in archive.namelist():
                    if name.endswith(".xml"):
                        xml = ElementTree.fromstring(archive.read(name))
                        parts.append("".join(xml.itertext()))
                text = "\n".join(parts)
        elif path.suffix.lower() in READABLE_SUFFIXES:
            text = path.read_text(encoding="utf-8")
            if path.suffix.lower() in {".html", ".htm"}:
                text = html_text(text)
        else:
            return
        self.require(not PRIVATE_MARKER.search(text),
                     f"Private product marker in publication text: {relative}")

    def record(self, record, prefix=""):
        relative = str(PurePosixPath(prefix) / record["path"]) if prefix else record["path"]
        # Validate the unjoined component too: joining must not hide an escape.
        self.require(isinstance(record["path"], str), "Record path must be text")
        self.require(not PurePosixPath(record["path"]).is_absolute(), "Absolute record path")
        self.require(".." not in record["path"].split("/"), "Record path escapes prefix")
        path = self.path(relative)
        self.require(isinstance(record.get("bytes"), int) and not isinstance(record["bytes"], bool),
                     f"Missing integer bytes: {relative}")
        self.require(path.stat().st_size == record["bytes"], f"Byte count mismatch: {relative}")
        self.require(file_digest(path) == record.get("sha256"), f"SHA256 mismatch: {relative}")
        return relative

    def source_manifest(self):
        data = self.json(self.config["source_manifest"])
        included = data["include"]
        records = data["files"]
        self.require(isinstance(included, list) and all(isinstance(p, str) for p in included),
                     "Manifest include must be a list of paths")
        paths = [r["path"] for r in records]
        self.require(len(set(included)) == len(included), "Duplicate included source path")
        self.require(len(set(paths)) == len(paths), "Duplicate source file record")
        self.require(self.config["source_manifest"] in included,
                     "Source manifest must include itself as a publication path")
        self.require(set(included) - {self.config["source_manifest"]} == set(paths),
                     "Manifest include and file records differ (self hash excluded)")
        for relative in included:
            self.check("source_path:" + relative, lambda p=relative: str(self.path(p).relative_to(self.root)))
            if Path(relative).suffix.lower() in CODE_SUFFIXES:
                self.check("source_name:" + relative,
                           lambda p=relative: self.require(not PRIVATE_MARKER.search(Path(p).name),
                                                          f"Private source filename: {p}"))
        for record in records:
            self.check("source_hash:" + str(record.get("path")), lambda r=record: self.record(r))
        return {"files": len(records), "code_content_scanned": False}

    def edition(self):
        relative = self.config["methodology_root"] + "/edition.json"
        data = self.json(relative)
        self.require(self.config["chapter_ids"] == CHAPTER_IDS,
                     "Configured chapter IDs must equal the nine VALUE chapters")
        self.require(data["chapterIDs"] == CHAPTER_IDS, "Edition contains mixed, missing or reordered chapters")
        for field, cfg in [("edition", "edition"), ("date", "revision_date"),
                           ("basis", "scientific_basis_date")]:
            self.require(data[field] == self.config[cfg], f"Edition {field} mismatch")
        return {"edition": data["edition"], "date": data["date"], "basis": data["basis"]}

    def chapters(self, language):
        exports = self.json(self.config["chapter_exports"][language])
        self.require(isinstance(exports, list), "Chapter export must be an array")
        self.require([c["id"] for c in exports] == CHAPTER_IDS,
                     f"{language} generated chapter IDs differ from VALUE-only allowlist")
        self.require(all(type(c["number"]) is int for c in exports)
                     and [c["number"] for c in exports] == list(range(1, 10)),
                     f"{language} chapter numbers must be consecutive 1..9")
        for number, item in enumerate(exports, 1):
            relative = f'{self.config["methodology_root"]}/{language}/{item["id"]}.md'
            source = self.path(relative).read_text(encoding="utf-8")
            self.require(item["markdown"] == numbered_markdown(source, number),
                         f"Generated markdown diverges from source: {relative}")
            self.require(not PRIVATE_MARKER.search(source), f"Private product in chapter: {relative}")
            self.require(not PRIVATE_MARKER.search(item["markdown"]), "Private product in generated markdown")
            self.require(not PRIVATE_MARKER.search(html_text(item["html"])), "Private product in generated chapter HTML")
        return {"chapters": 9, "language": language, "numbering_only_change": True}

    def products(self):
        allowed = self.config["site_products"]
        self.require(allowed == ["value"], "Product allowlist must contain only value")
        site = self.json(self.config["site_config"])
        generated = self.json(self.config["generated_products"])
        self.require([p["id"] for p in site["products"]] == allowed, "Unexpected website product")
        self.require([p["id"] for p in generated] == allowed, "Unexpected generated website product")
        for field, cfg in [("methodology_edition", "edition"),
                           ("methodology_revision_date", "revision_date"),
                           ("evidence_date", "scientific_basis_date")]:
            self.require(site[field] == self.config[cfg], f"Website {field} mismatch")
        edition = self.json(self.config["methodology_root"] + "/edition.json")
        for language in ("zh", "en"):
            relative = f"website/dist/{language}/methodology/index.html"
            page = self.path(relative).read_text(encoding="utf-8")
            visible = re.sub(r"\s+", " ", html_text(page)).strip()
            for field in ("revision", "basisLabel"):
                label = re.sub(r"\s+", " ", edition[field][language]).strip()
                self.require(bool(label) and label in visible,
                             f"Generated methodology {field} label mismatch: {relative}")
        return {"products": allowed, "methodology_config_matches": True,
                "generated_revision_and_basis_labels_match": True}

    def artifacts(self):
        manifest = self.json(self.config["artifact_manifest"])
        expected = self.config["expected_artifacts"]
        records = manifest["files"]
        self.require(manifest.get("review", {}).get("status") == "passed",
                     "Methodology artifact document review has not passed")
        self.require(len(expected) == 6, "Exactly six methodology artifacts required")
        self.require(len(records) == 6, "Artifact review manifest must contain exactly six files")
        self.require(len({r["path"] for r in records}) == 6, "Duplicate methodology artifact record")
        self.require({r["path"] for r in records} == {r["path"] for r in expected},
                     "Artifact files differ from explicit six-file allowlist")
        lookup = {r["path"]: r for r in records}
        for item in expected:
            record = lookup[item["path"]]
            self.require(record.get("render_review") == "passed",
                         f"Artifact render review has not passed: {item['path']}")
            self.require(all(record.get(k) == item[k] for k in ("language", "format")),
                         f"Artifact language/format mismatch: {item['path']}")
            relative = self.record(record, self.config["artifact_prefix"])
            self.scan(relative)
        return {"files": 6, "pdf_text_review": "passed artifact review manifest, based on full-page document review",
                "pdf_text_parsed_by_this_checker": False}

    def published_text(self):
        count = 0
        for relative in self.config["published_text_roots"]:
            base = self.path(relative, "directory")
            for path in sorted(base.rglob("*")):
                rel = path.relative_to(self.root).as_posix()
                self.require(not path.is_symlink(), f"Publication symlink: {rel}")
                if path.is_file():
                    self.check("published_text:" + rel, lambda p=rel: self.scan(p))
                    count += 1
        return {"files_inspected": count, "source_tool_code_scanned": False}

    def run(self):
        self.check("source_manifest", self.source_manifest)
        self.check("edition", self.edition)
        for language in ("zh", "en"):
            self.check("chapters:" + language, lambda l=language: self.chapters(l))
        self.check("website_products_and_version", self.products)
        self.check("methodology_artifacts", self.artifacts)
        self.check("published_text", self.published_text)
        return {"schema_version": "value.publication-scope-report/v1",
                "passed": not self.errors, "read_only": True, "model_started": False,
                "checks": self.checks, "errors": self.errors}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--config", default="publication-scope.json")
    parser.add_argument("--report", required=True, help="Internal JSON report output path")
    args = parser.parse_args()
    try:
        loader = Review(args.root, {})
        config = loader.json(args.config)
        loader.require(config.get("schema_version") == "value.publication-scope/v1",
                       "Unsupported publication-scope configuration")
        report = Review(args.root, config).run()
        status = 0 if report["passed"] else 1
    except (OSError, ValueError, TypeError, KeyError) as error:
        report = {"schema_version": "value.publication-scope-report/v1", "passed": False,
                  "read_only": True, "model_started": False, "checks": [],
                  "errors": [{"check": "configuration", "message": str(error)}]}
        status = 2
    destination = Path(args.report)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"passed": report["passed"], "errors": len(report["errors"]),
                      "report": str(destination)}, ensure_ascii=False))
    return status


if __name__ == "__main__":
    sys.exit(main())
