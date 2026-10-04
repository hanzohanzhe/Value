# Data Workbench gap matrix

Design baseline: `2026-08-21-data-workbench-design.md`.

| Prompt | Required outcome | Current evidence | Gate decision | Commit |
| --- | --- | --- | --- | --- |
| DATA-01 | Lifecycle and service contract | 30 focused tests passed; public DTOs reject absolute paths; Prompt 96–98 and retained hashes passed | passed | `feat(data): add workbench lifecycle contracts` |
| DATA-02 | Registry and discovery | 15 focused tests passed; seven official source definitions packaged; frozen NESO response, licence-change rejection, off-domain redirect rejection and portal-outage evidence passed | passed | `feat(data): add official source discovery` |
| DATA-03 | Fetch and object store | 27 focused and retained-source tests passed; bounded streaming, atomic SHA-256 storage, duplicate reuse, cancellation cleanup, corruption/media/redirect rejection and explicit rights state passed | passed | `feat(data): add secure object acquisition` |
| DATA-04 | DSO and ETYS compilers | 36 compiler/Prompt 96–98/retained-source/dependency-policy tests passed; Shapely 2.1.1, PyProj 3.7.1 and OpenPyXL 3.1.0 installed with `pip check` clean | passed | `feat(data): compile DSO and ETYS evidence` |
| DATA-05 | Regional demand | 61 data-workbench/Prompt 96–98/retained-source tests passed; measured postcode energy, mismatch classes, FES relative evolution, named fallback waiver and `1e-8 MWh` national reconciliation passed | passed | `feat(data): compile regional demand evidence` |
| DATA-06 | Interconnectors | 66 data-workbench/Prompt 96–98/retained-source tests passed; physical GB landing, deterministic coast fallback waiver, directional envelope and conserving country-profile split passed | passed | `feat(data): compile interconnector landings` |
| DATA-07 | Cut review candidate | 70 data-workbench/Prompt 96–98/retained-source tests passed; signed cut incidence, review overrides, unresolved blockers, connected computational skeleton, audit-map reconciliation and Prompt 98 facade passed | passed | `feat(data): assemble reviewed zonal candidate` |
| DATA-08 | Validation and promotion | 89 data-workbench/data-bundle/Prompt 96–98/retained-source tests passed; six independent gates, non-waivable mutation failures, waiver registry, stale-candidate rejection, deterministic archive and atomic existing-installer acceptance passed | passed | `feat(data): validate and promote reviewed candidates` |
| DATA-09 | CLI and local API | 102 data-workbench/local-backend/existing API/Prompt 96–98/retained-source tests passed; 11 CLI commands, versioned focused routes, durable SQLite jobs, background execution, cancellation and restart recovery passed | passed | `feat(data): expose workbench CLI and local API` |
| DATA-10 | Frontend and handoff | Typed four-view frontend, 119 bounded Python tests, 2 frontend contract tests, 12 browser tests, lint and production build passed. Live gate pinned 4/7 official objects; all 4 await rights review. Two official builds stopped before construction because the normalized nine-role inventory does not exist. | implementation passed; official candidate and promotion blocked truthfully | `feat(data): complete local data workbench` |

The executor replaces `not executed`, `pending` and `—` only with observed
evidence. A failed or blocked gate remains visible and is not carried forward as
success.
