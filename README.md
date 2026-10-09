# VALUE

*Variable renewable electricity Allocation, Load-enabled excess-generation Utilisation, and system Evolution*

VALUE connects half-hourly power-system operation with annual investment to study generation, storage, networks and asset evolution in one modelling workspace.

**[Download VALUE](https://github.com/hanzohanzhe/Value/releases/tag/value-2026-10-09-a1) · [Website](https://value.ac/en/) · [Methodology](https://value.ac/en/methodology/) · [User guide](docs/USER_GUIDE.md)**

Current application: **0.7.0-alpha.1**. Full installer batch: **2026-10-09-a1**.

## Get started

1. Download the Full package for Windows, Linux, macOS Intel or Apple Silicon. Extract it and run the included installer, choosing a new, empty directory.
2. Start VALUE and open the local address shown by the launcher.
3. Open **Learn → VALUE 101**, create a Study and run a one-day teaching task. View its outputs in **Results**.

Full packages include Python, Node.js, scientific dependencies and two VALUE 101 teaching packs. Model runs take place on your computer. The interface defaults to English and also supports Chinese.

Linux has passed offline installation, a 48-period VALUE 101 run and shutdown checks. Windows and macOS packages are experimental; native installation acceptance, signing and notarisation remain pending. See the [installation guide and platform requirements](https://value.ac/en/docs/value/) and [acceptance records](https://value.ac/en/releases/).

## Choose your task

| Your task | Start here |
| --- | --- |
| Reproduce from existing data | [VALUE 101 and reference comparisons](https://value.ac/en/community/#reproduce) |
| Add your new data | [Build your own model](docs/BUILD_YOUR_OWN_MODEL_101.md) |
| Edit a module | [Module developer guide](docs/MODULE_DEVELOPER_101.md) |
| Add a new function to VALUE | [Extension workflow](https://value.ac/en/community/#extend) |

## Methodology and research data

[Methodology 0.4.1](https://value.ac/en/methodology/) describes VALUE 0.7.0-alpha.1, with an implementation and data basis of 9 October 2026. English and Chinese editions are available as web pages, Word, PDF and offline HTML.

Select research inputs to match your methodology profile:

| Profile | Data |
| --- | --- |
| Corrected (default) | [GBP1 public2, R029 public2 and the GBP1 public2 23-zone research suite](https://github.com/hanzohanzhe/Value/releases/tag/value-data-2026-10-09) |
| Doctoral reproduction | [GBP1 public1](https://github.com/hanzohanzhe/Value/releases/tag/value-data-2026-10-04) |

Import research inputs through **Data** and follow each package's provenance and licence terms. The [data guide](https://value.ac/en/data/) explains package selection and limitations. Scientific conclusions depend on the configuration, inputs and study horizon.

## Run from source

Use Python 3.10, Node.js 22.13.0 or later, and npm 11.16.0. From the repository root:

```sh
python3.10 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements/value-all-py310.lock
python -m pip install -e .
python scripts/install_synthetic_pack.py --value-101-only
npm ci --ignore-scripts
npm run build
```

On Windows, create the environment with your Python 3.10 interpreter and activate it with `.venv\Scripts\activate`.

Run `python -m backend.server` and `npm run start` in two terminals, using the same environment and data directory. Open <http://127.0.0.1:8800>.

The frozen source release is `source-2026-10-09`; the Python package version is `0.7.0a1`. See the [release map](docs/release/release-map.json) for the source and installer relationship. The static website source lives in [`website/`](website/).

## Licence and citation

Software: **[Apache-2.0](LICENSE)**. Author-written documentation: **CC BY 4.0**. Synthetic teaching data: **CC0**. Third-party components and research data retain their own terms; see [LICENSING.md](LICENSING.md).

Research, teaching and commercial use are welcome under the applicable licences. If VALUE supports your research, please use [CITATION.cff](CITATION.cff) to cite it.
