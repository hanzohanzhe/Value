# Build VALUE methodology documents

The authoritative chapters and edition are in `docs/methodology/`. These tools assemble both languages, render the mathematics and produce Word and standalone HTML. The website consumes their generated output.

Use Python with `requirements.txt` and Node with this directory's `package.json`. Install these document-building dependencies in a separate environment; they are independent of the model runtime. The tested document tools use python-docx 1.2.0, lxml 6.1.1, MathJax 3.2.2, marked 17.0.5 and sharp 0.35.4. PDF conversion also needs a Word-compatible renderer such as LibreOffice and fonts for Chinese text and mathematics.

From the repository root, after preparing those dependencies:

```sh
export VALUE_METHODOLOGY_SOURCE="$PWD/docs/methodology"
export VALUE_METHODOLOGY_WORK="$PWD/work/methodology-build"
export VALUE_DOCUMENT_DIR="$PWD/work/methodology-documents"
python3 scripts/methodology/assemble.py
node scripts/methodology/render_math.cjs zh
node scripts/methodology/render_math.cjs en
python3 scripts/methodology/build_document.py zh
python3 scripts/methodology/build_document.py en
```

The assembler requires the nine chapter IDs in `edition.json`. Intermediate JSON, mathematical SVG/PNG and other build files belong in `VALUE_METHODOLOGY_WORK`. Offline HTML embeds its formula images and can be read without a network connection.

Convert each final DOCX to PDF and inspect all rendered pages, including formulas and tables. Check that the Chinese and English mathematical definitions, tables and numerical values match the reviewed source. Record the six final documents in `docs/methodology/artifacts.json` with their filename, language, format, bytes, SHA256 and review result; a successful conversion alone is not a content or layout review.

Then synchronize the reviewed set and build the website:

```sh
python3 website/sync_methodology.py --source docs/methodology --build "$VALUE_METHODOLOGY_WORK" --documents "$VALUE_DOCUMENT_DIR"
python3 website/build.py
python3 website/check_site.py
```

The synchronizer checks the declared edition and approved file hashes, replaces the methodology asset set, and copies only referenced formula SVGs. It does not search old output directories. Refresh the overall source manifest after all changes, then run `scripts/check_publication_scope.py` before preparing an upload.

Generator scripts are Apache-2.0; methodology prose and generated documents retain CC BY 4.0.
