# VALUE website

Python 3.12+ standard library builds this bilingual static site:

```sh
python3 build.py
python3 check_site.py
```

The existing routes form one journey: Home (`/`), Get started (`community/`), Install (`docs/value/`), Data (`data/`), Methodology (`methodology/`), Develop (`docs/`). The three journey pages and four task labels live only in `journey.pages(w)`; `content.py` retains the research and release pages; `build.py` owns navigation, layout and generation. `static/` contains build inputs and `dist/` is generated output.

Full installer downloads remain pending. Linux candidate installation and scoped user tasks have been checked; Windows and macOS native acceptance, signing and notarisation remain pending. Model runs occur on the user's computer.

VALUE software uses Apache-2.0. Documentation uses CC BY 4.0; teaching data uses CC0; third-party materials retain their own terms. Research citation is recommended.

## Methodology integration

The main repository owns `docs/methodology/` source manuscripts and `website/` website source. This Site checkout is deployment staging. `edition.json` and `artifacts.json` in `docs/methodology/` identify the reviewed edition and its six downloadable artifacts.

```sh
python3 sync_methodology.py --source ../docs/methodology --build <rendered-work-dir> --documents <six-files-dir>
```

The synchronizer requires matching nine-chapter IDs and continuous numbering, referenced formula SVGs, and the approved SHA256/size of six bilingual document files. It replaces the entire chapter and asset input sets without merging older editions. It does not render documents, run the model, build the website or deploy.

The reviewed 0.4 edition dated 2026-10-08 (VALUE 0.7.0-alpha.1 implementation basis 2026-10-08) is imported with nine chapters in each language and six enabled document downloads. Their language, format, bytes and SHA256 entries are retained in the source artifacts manifest. No external work-directory source is required to rebuild an already imported website.

Deployments preserve the existing owner-private Site audience. Opening public access is a separate release step.

Website generators and synchronization scripts use Apache-2.0; website prose and methodology use CC BY 4.0. Website build Python 3.12+ is separate from the Full installer’s bundled Python 3.10 runtime; users do not need to install Python or Node to run Full.
