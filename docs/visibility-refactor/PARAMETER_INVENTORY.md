# Scheme C parameter inventory and policy

The executable registry is `gridform_core/parameters.py`; `GET /api/parameters`
returns the same metadata. Detailed fleet, cost, success-rate, timeline, weather,
demand and policy values remain versioned Data Pack inputs; their hashes are
captured separately and they are never silently copied into project overrides.

| Assumption family | Previous effective source | Current default/unit | Effect | Category |
|---|---|---|---|---|
| GB topology and interconnectors | Scheme C equations | single node; imports as boundary offers | Feasible dispatch | Fixed module assumption |
| Dispatch formulation | Scheme C equations/config | continuous bid-at-cost, multiplier 1 | Merit order and prices | Fixed formulation; multiplier experimental |
| Clock | config/environment | 0.5 h; 17,520/year | Energy conversion and annual totals | Fixed module assumption |
| Virtual storage pool | environment/module constant | 1e9 MW and 1e9 MWh | Keeps diagnostic pool non-binding | Fixed module assumption |
| System-cost boundary | annual Scheme C loop | Scheme C capital + operating + mechanisms | Reported system cost | Fixed module assumption |
| Fleet, capital costs, investment economics | JSON Data Pack roles | versioned values | Operating stock and investment | Data Pack-bound |
| Demand, VRE/weather and import series | Data Pack roles | versioned time series | Period dispatch | Data Pack-bound |
| Success rates and detailed timelines | CSV/JSON Data Pack roles | rates/months | Project success and completion | Data Pack-bound |
| Success method and random seed | hidden environment/function | expected; seed 0 | Expected MW or seeded outcome | Advanced scientific |
| Uncertain projects and zombie rules | config/environment | include; enabled; 2015; 2 y | REPD eligibility | Advanced scientific |
| Project size/horizon/timing | config/environment | 1 MW; 2040; median; 3 y | Pipeline eligibility/timing | Advanced scientific |
| VRE/storage expansion caps | wrapper/environment | 0.20 / 0.20 | Annual headroom | Advanced scientific |
| Storage credit method | environment | `scheme_c` | Storage headroom | Advanced scientific |
| Scenario | project/environment | `existing_decarb_base` | Policy pathway | Basic scientific |
| Checkpoint and traces | environment | checkpoint on; traces off | Runtime/artifact volume | Runtime/output |

Resolution precedence is fixed module assumption; otherwise module default, then
declared Data Pack value, then validated project override. Runtime options use a
separate namespace. Every effective value records its source in
`resolved-run.json`. Unknown keys, wrong types, out-of-range values, unsupported
enums and attempts to override fixed fields fail before model import. A bid
multiplier other than one is explicitly experimental and removes the strict
bid-at-cost claim.

The only environment/global translation of scientific settings is
`SchemeCLegacyParameterAdapter`, the compatibility boundary for the copied Scheme
C kernel. New v2 modules consume the typed resolved parameter objects instead of
reading process environment variables.
