# VALUE website

Python 3.12+ standard library builds this bilingual static site:

```sh
python3 build.py
python3 check_site.py
```

The existing routes form one journey: Home (`/`), Get started (`community/`), Install (`docs/value/`), Data (`data/`), Methodology (`methodology/`), Develop (`docs/`). The three journey pages and four task labels live only in `journey.pages(w)`; `content.py` retains the research and release pages; `build.py` owns navigation, layout and generation. `static/` contains build inputs and `dist/` is generated output.

Full candidate archives are available from GitHub Releases. Linux offline installation and the four short user tasks have passed. Windows and macOS are experimental candidates, with native acceptance and signing/notarisation scheduled for subsequent release work. The improved application frontend is under code review; its accepted changes will ship in a new software release. Model runs occur on the user's computer.

VALUE software uses Apache-2.0. Documentation uses CC BY 4.0; teaching data uses CC0; third-party materials retain their own terms. Research citation is recommended.

## Methodology integration

The main repository owns `docs/methodology/` source manuscripts and `website/` website source. This Site checkout is deployment staging. `edition.json` and `artifacts.json` in `docs/methodology/` identify the reviewed edition and its six downloadable artifacts.

```sh
python3 sync_methodology.py --source ../docs/methodology --build <rendered-work-dir> --documents <six-files-dir>
```

The synchronizer requires matching nine-chapter IDs and continuous numbering, referenced formula SVGs, and the approved SHA256/size of six bilingual document files. It replaces the entire chapter and asset input sets without merging older editions. It does not render documents, run the model, build the website or deploy.

The reviewed 0.3 edition dated 2026-10-04 (basis 2026-10-02) provides nine chapters in each language and six document downloads. The website presents each document by filename, language and format. The source artifacts manifest retains integrity records for release checks. Imported chapters and assets are included in this repository for rebuilding the website.

The current public Site provides the installation, data and methodology pages. The earlier Site is retained as a private archive. Website copy updates can be published independently of the application release.

Website generators and synchronization scripts use Apache-2.0; website prose and methodology use CC BY 4.0. Website build Python 3.12+ is separate from the Full installer’s bundled Python 3.10 runtime; Full users run the included platform installer to prepare Python and Node.
