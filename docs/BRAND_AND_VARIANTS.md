# VALUE identity and repository variants

## Formal name

**VALUE** means **Variable renewable electricity Allocation, Load-enabled
excess-generation Utilisation, and system Evolution**.

The name describes the scientific question. It does not prescribe a clearing
algorithm. Fast cost-ranked clearing, perfect-foresight optimisation, network
clearing and an external user PSM are alternative modules behind versioned
contracts.

## This repository

This repository is **VALUE Network Extensions**, the research branch that keeps
the accepted VALUE single-node model available while adding optional network
capabilities:

- chronological DC network clearing has independent analytical, random,
  24-hour and 168-hour checks;
- AC is an experimental feasibility checker, not AC optimal power flow;
- transmission expansion is an experimental causal lifecycle and has not yet
  established a full-year or ten-year Great Britain pathway.

Selecting a network module requires a compatible network data interface. A
single-node Study does not acquire transmission constraints merely by being run
from this repository. Every result must retain the selected module identity and
its model-card maturity status.

A VALUE national single-node configuration represents Great Britain as one
electrical node; interconnectors are boundary import resources, not internal
branches. The previously labelled VALUE-single product is the private Electrace
differential optimisation engine. It is separate from VALUE and excluded from
this source release and Apache licence grant.

## Compatibility identifiers

Existing research records contain identifiers created before the VALUE name was
adopted. The following are intentionally retained in the 0.x series:

- `force.*` bundle, engine and accounting definition IDs;
- `gridform.*` identifiers in older records and the `gridform_core` Python namespace (module slot contract IDs are now `value.*`; the installer accepts only the IDs in `gridform_core/v2/module_manifest.py`);
- the `.gridform` local state path of a pre-0.5 source checkout (launchers
  point `VALUE_DATA_HOME` at it; `FORCE_DATA_HOME` is no longer read);
- module IDs such as `force-perfect-foresight-lp`;
- the original `install-force.cmd` and `start-gridform.cmd` launchers.

New users should use the VALUE-named launchers. Renaming persistent IDs in place
would make old Studies, checkpoints and external modules unreadable, so any
future namespace migration must use explicit aliases and a versioned migration
tool.
