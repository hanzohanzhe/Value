# From VALUE 101 to VALUE-UK

VALUE 101 teaches the same Study, Data Pack, Module and Run contracts used by the full application. The teaching system is small enough to inspect, but its data are synthetic. A VALUE-UK Study uses the same execution path with a complete British dataset and a declared set of scientific modules.

The prepared VALUE-UK research suite is the shortest route from the teaching installation to the supplied British model. One non-executable ZIP installs the 25-role base Data Pack and the separate fixed-zonal Network Pack, then creates copperplate and zonal Study revisions. It does not start a Run. Researchers can also build their own Data Pack and Studies by following the role-mapping route later in this guide.

## What carries over

| Part | VALUE 101 | VALUE-UK |
| --- | --- | --- |
| Application | Local VALUE website and runtime | The same application and runtime |
| Data contract | 25 named input roles | The same 25 roles, populated with British research data |
| PSM | Registered bid-at-cost implementation | The same PSM, or another compatible PSM selected by the researcher |
| CEM | Investment, caps, planning and annual transition | The same annual chain, with research years and assumptions |
| Clock | Annual files are supplied, with a 48-period lesson option | 17,520 half-hours for every complete model year |
| Evidence | Bids, dispatch, storage, unused VRE and model records | The same evidence, plus annual cost, carbon, investment and planning results |
| Scientific claim | Teaching behaviour only | Limited to the installed data, modules, parameters and completed validation |

The 48-period lesson does not estimate annual income or investment. Use the complete annual route before interpreting storage recovery, system cost, carbon, investment or commissioning.

## What Check readiness resolves

`Check readiness` is not a cosmetic button. It validates the selected immutable Study revision, resolves exact Module versions, validates required data roles, units and chronology, verifies data and Module identities and hashes, estimates periods, disk, peak memory and runtime, and freezes the declared input snapshot. A required input that cannot be resolved blocks execution and returns the affected role and corrective action.

For a **single node** Study, the saved `data_pack_id` is already authoritative. Preflight validates and freezes that Data Pack, the selected Modules, parameters and run clock. It does not search for a separate Network Pack. Interconnectors remain boundary offers in the base Data Pack, and no internal transmission dataset is added.

For a **zonal** Study, the revision also declares the zonal System domain, network extension and `zonal_demand_mode`. Preflight must resolve one compatible installed Network Pack and verify its ID, manifest/hash, zones, cutsets, time-dependent ratings, zonal demand, spatial mapping and clock. It must state whether the base pack supplies national demand and the network pack supplies allocation shares, or the network pack supplies absolute zonal demand. The input snapshot retains both pack identities and hashes. VALUE must not silently choose another pack or fall back to copperplate.

Before checking, `Network pack: Check readiness to confirm` means the pack is **resolved during preflight** and is not yet confirmed. It does not mean missing, randomly selected or downloaded during the Run. Success displays `Network pack: <pack-id> · verified`; failure names the missing or incompatible role and its corrective action.

```text
Single node:
Saved Study → declared Data Pack → validate and freeze

Zonal:
Saved Study → declared base Data Pack
            → resolve compatible Network Pack
            → validate alignment
            → freeze both identities
```

## 1. Write down the Study before preparing files

Define the research question, first and final model years, national demand scenario, weather years, fleet date and policy assumptions. Decide whether the comparison keeps the PSM and CEM modules fixed or deliberately replaces one of them.

A clean first VALUE-UK Study normally uses the national single-node system domain. It represents the GB-wide electricity market without internal transmission constraints. Interconnectors remain external boundary offers. Add the fixed zonal transport and redispatch method only when the Study also has a compatible network Data Pack and the research question requires it.

Keep a short data note beside the Study. Record the source, download date, licence or access restriction, transformation script and unit for each source. These declarations become part of the Data Pack rather than informal notes stored elsewhere.

## 2. Build the VALUE-UK Data Pack

The Data Pack manifest binds each scientific role to a file. VALUE reads roles, not familiar filenames or absolute paths. A file called `demand.csv` has no meaning until the manifest binds it to `demand.real` or `demand.forecast` with its format, unit and checksum.

### The required groups

| Roles | Typical format | Required content |
| --- | --- | --- |
| `config.model_parameters` | JSON | Scenario assumptions and model parameters |
| `costs.capital` | JSON | CAPEX, fixed O&M, economic life and declared currency basis |
| `demand.forecast`, `demand.real` | CSV | One MWh value for every half-hour in every model year |
| `fleet.generators` | JSON | Operating assets, owners, technology, capacity, economics and storage characteristics |
| `profiles.vre_solar`, `profiles.vre_onshore`, `profiles.vre_offshore` | CSV | Half-hour availability for each renewable technology |
| `weather.solar`, `weather.wind` | NetCDF | Weather fields used by the selected weather method |
| `market.<country>.price` | CSV | Half-hour import offer prices for Belgium, France, Ireland, Netherlands and Norway |
| `market.<country>.profile` | CSV | Signed half-hour interconnector availability for the same boundaries (positive = import capacity offered day-ahead at the country's price under the corrected methodology, balancing stage only under the doctoral reproduction; negative = export capability) |
| `projects.repd`, `source.repd_raw` | CSV | Prepared planning records and the retained source records |
| `planning.success_rates` | CSV | Planning success assumptions |
| `planning.timelines` | JSON | Stage duration and completion assumptions |
| `policy.support` | JSON | Support-mechanism assumptions used by the selected modules |

### Clock and units

Each complete model year contains 17,520 half-hours. Demand and dispatched electricity use MWh per period. Generator power capacity uses MW. Storage records must distinguish charge or discharge power in MW from energy-pool capacity in MWh. Renewable profiles must use the availability convention expected by the selected PSM. Import profiles must retain their sign convention and boundary identity.

Do not repair a missing period by silently copying a neighbouring row. Reject duplicated periods, missing periods, non-finite values and a clock that changes between datasets. Leap-year treatment, daylight-saving conversion and timezone handling must be declared by the data preparation process.

### Asset and planning identity

An operating asset needs a stable ID, economic owner, technology, capacity and region. Storage also needs charge and discharge power, energy capacity, efficiency and its technology identity. Assets that enter through the planning pipeline must carry enough information to inherit CAPEX, fixed O&M and economic life when commissioned.

Keep the prepared REPD project table separate from the retained source extract. This makes technology mapping, date handling and planning probability choices auditable without changing the source record.

### Manifest records

Each binding declares at least its role, relative URI, format, SHA-256, unit where applicable, source locator, source version, access date, transformation version, licence, attribution and redistribution class. Use relative paths inside the bundle. Do not place a personal drive letter or user directory in the manifest.

## 3. Install the prepared VALUE-UK research suite

The application and research data are separate downloads. The current installation
candidate batch is `2026-10-03-rc1` (not a published Git tag): four Full archives
for Windows x64, Linux x64, macOS Intel and macOS Apple Silicon. VALUE macOS
requires 15+. Full includes private Python/Node, locked dependencies and the two
CC0 synthetic teaching packs; installation and bundled teaching work offline.
Windows/macOS native acceptance is pending. The historical `VALUE-Setup.exe`
workflow is not the installer supplied by this batch.

Windows uses `install-value.cmd`, then `start-value.cmd` from the installed
`%USERPROFILE%\VALUE-four-role`; macOS uses `Install VALUE.command`, then
`Start VALUE.command` from `~/VALUE-four-role`; Linux uses `./install-value`, then
`~/VALUE-four-role/start-value`. Keep the startup terminal open and visit
`http://127.0.0.1:8800/`; Ctrl+C stops the service. Start with the four tasks
`reproduce from existing data`, `add your new data`, `Edit module`,
`add new function to VALUE`.

Full contains no rights-governed UK research data. VALUE accepts a separately
prepared research suite without reinstalling the application. The illustrative
filename `VALUE-UK-Research-Suite.bundle.zip` below is not a claim that a public
research-data Release already exists. Its rights-cleared contents and exact
version/hash must be established before distribution; a suite carries data and
declarative Study templates, not executable code.

1. Open `Data` and choose `Install a VALUE-UK research suite`.
2. Select `VALUE-UK-Research-Suite.bundle.zip`.
3. Read the suite and component rights notices, then acknowledge them.
4. Start installation and keep the page open while VALUE validates and stages both components.
5. Confirm that the result shows the exact base Data Pack ID, Network Pack ID, component hashes and two saved Study revisions.

The transaction creates:

| Saved Study | Years | System domain | Data identities |
| --- | --- | --- | --- |
| `VALUE-UK copperplate 2025-2034` | 2025 to 2034 | National single node | `value-uk-open-data-pack-v1`; no Network Pack |
| `VALUE-UK fixed-zonal network 2025-2034` | 2025 to 2034 | Fixed GB zones and redispatch | The same base pack plus `value-gb-zonal-network-v1-*` |

Both Studies use the same national demand, annual clock, storage-cost method and CEM chain. The zonal Study adds the Network Pack and post-thesis redispatch module. Installation leaves both Studies unrun. Open one Study, inspect its immutable revision, then use `Check readiness` before launching it.

Installing identical suite bytes again is idempotent. An existing component ID with different bytes is a collision and must use a new versioned ID. The current Full installer requires an empty target directory. Upgrade by installing into a separate empty directory; automatic migration of previously installed research suites, Studies or Runs is not provided. Keep the old installation and its research state until a separate, verified migration workflow is available.

## 4. Build and install your own data

1. Open `Data` and inspect the definition, format and unit for every required role.
2. If the source schema differs, open `Add data` and build an adapter that converts the source fields into VALUE's role contract.
3. Build one versioned Data Pack bundle. A folder of unrelated uploads is not a reproducible input.
4. Run validation. Resolve missing roles, clock errors, unit errors, checksum failures and unresolved rights before promotion.
5. Install the validated bundle locally. VALUE copies it into the local data store and exposes its immutable pack ID in `Studies`.

The VALUE application installer does not contain the rights-governed UK research pack or the doctoral 1000 TWh reproduction data. Obtain the separate research suite from the project owner, or construct a new pack from sources that you are entitled to use. A manifest can record a restricted source without granting permission to redistribute it.

## 5. Create the full Study

Open `Studies` and create a new revision rather than editing the VALUE 101 baseline in place.

1. Give the Study a research name and a short question that the results should answer.
2. Enter the first and final model years.
3. Select the installed VALUE-UK Data Pack.
4. Choose `National single node` for the copperplate model. Select the zonal method only with compatible network data.
5. Review the seven-module chain and any advanced parameters.
6. Save the Study. VALUE records an immutable revision with data, module and parameter identities.

| Slot | Baseline VALUE purpose |
| --- | --- |
| `psm` | Clears each half-hour market and returns physical and economic results |
| `storage_cost` | Forms the selected storage offer-cost rule |
| `vre_cap` | Calculates wind and solar expansion headroom |
| `storage_cap` | Calculates storage expansion headroom |
| `investment` | Evaluates owner-level investment and retirement |
| `pipeline` | Advances existing projects and admits new proposals |
| `transition` | Carries commissioned assets, retirements and state into the next year |

Creating a Study does not run it. Check the saved Data Pack ID, years, System domain and Module IDs before starting a long calculation.

## 6. Replace a Module when the method changes

Change data when the evidence changes. Change a registered parameter when only an exposed assumption changes. Replace a Module when the algorithm inside an existing lifecycle slot changes. Add an extension when the research introduces a new domain, new conditional data roles or a lifecycle hook that the seven slots do not provide.

| Research change | Correct route |
| --- | --- |
| New demand or weather database | Data Pack or adapter |
| Different planning success assumption already exposed in the registry | Study parameter |
| Different bidding, dispatch or storage-chronology algorithm | `psm` Module |
| Different storage cost recovery rule | `storage_cost` Module |
| Different investment decision method | `investment` Module |
| Different project-stage or commissioning method | `pipeline` Module |
| New hydrology or network domain with extra data and results | Extension, with a compatible executable module where required |

### Bundle layout

A small Module ZIP contains `value-module.json` and an importable Python package. A typical bundle has these members:

| Path | Purpose |
| --- | --- |
| `value-module.json` | Module ID, version, slot, contract and executable entry point |
| `src/my_value_module/__init__.py` | Python package marker |
| `src/my_value_module/plugin.py` | Implementation class |
| `tests/` | Contract, deterministic fixture and scientific method tests |
| `README.md` | Method, parameters, units, limitations and citation |

The manifest declares a unique ID, semantic version, scientific version, slot, implementation such as `my_value_module.plugin:MyModule`, contract version, inputs, outputs, state reads and writes, determinism, capabilities and artifacts.

Use the public interfaces in `gridform_core/v2/interfaces.py` and the typed objects in `gridform_core/v2/contracts.py`. Do not import private doctoral-reproduction compatibility functions into an external module.

### Install and select it

1. Open `Modules` and read the slot contract.
2. Build the ZIP and run its focused contract and method tests.
3. Upload the ZIP. VALUE treats it as trusted in-process Python, so install only reviewed code.
4. Confirm that structural conformance passes and enable the installed version.
5. Open `Studies`, switch to `Advanced`, create a new revision and select the Module in its declared slot.
6. Compare the new revision with the unchanged control Study.

Never overwrite a built-in ID or publish changed code under an existing version. A new scientific implementation needs a new version and source hash. Old Study revisions must continue to resolve to their original implementation.

## 7. Test the migration in stages

Do not begin with a ten-year Run. Start with the smallest calculation that can expose the expected failure.

| Gate | What it checks |
| --- | --- |
| Data validation | All roles, formats, clocks, checksums, licences and provenance are declared |
| Wiring smoke | The selected Data Pack and seven modules resolve and exchange typed objects |
| One market day | Bids, dispatch, storage SOC and unused VRE behave as expected over 48 half-hours |
| PSM method validation | Energy balance, limits and the claimed clearing method match independent or hand-calculated cases |
| Full year | Exactly 17,520 periods run, annual ledgers reconcile and annual economics are eligible |
| Two years | Investment and planning results enter the next year's physical operating state |
| Long run | The intended pathway completes without hidden fallbacks, missing years or ledger drift |

For a changed PSM, cover thermal generation, VRE, imports and storage competition. Check SOC, efficiency, power and energy limits. Include a constraint-breaking case that must fail. If the module makes an optimization claim, compare it with an independent solver or a hand-solvable fixture under the same information structure.

For a changed CEM module, check owner grouping, expansion headroom, commissioned-asset economics, retirement, planning outcomes and next-year injection. A growing asset count must change annualized capital and fixed operating costs when the added assets carry those costs.

## 8. Read the full results

`Runs` shows execution status, annual results and the exact Study revision. `Market replay` exposes bids and accepted energy when the Run stores full market trace. Full annual Runs normally use compact market evidence to control disk and runtime cost. `VRE & curtailment` shows available, accepted and unused renewable energy. `Inspect` contains planning, commissioning, ledgers, module identities and provenance.

The optional `Network & redispatch` page is relevant only to a Study that selected the fixed zonal method and supplied its network data. It is not an AC power-flow or security-analysis result.

Before reporting a VALUE-UK result, confirm that cost and carbon ledgers reconcile, annual period counts are complete, energy-balance residuals are within the declared tolerance and no required evidence is marked missing. Archive the Study, Run artifacts, Data Pack manifest, Module manifests and source hashes together.

## Migration checklist

| Check | Ready when |
| --- | --- |
| Research scope | Question, years, weather, demand and comparison case are written down |
| Data rights | Every source has an access and redistribution classification |
| Data Pack | All 25 roles pass format, unit, clock and checksum validation |
| Fleet | MW, storage MWh, owner, technology, economics and lifetime are complete |
| Planning | Source records, prepared records, success rates and timelines are distinct and traceable |
| Study | Pack ID, years, System domain, modules and parameters are saved as one revision |
| Module changes | Each changed algorithm has a versioned manifest, tests and source hash |
| One-day gate | Physical market behaviour is plausible and auditable |
| Annual gate | 17,520 periods and annual cost and carbon ledgers pass |
| Coupling gate | Commissioned assets appear in the following year's PSM state |
| Publication bundle | Inputs, code identities, results, licences and method notes are archived |

VALUE-UK is the result of these declared inputs and executable choices. The software name alone does not make a Study British, annual or scientifically validated.
