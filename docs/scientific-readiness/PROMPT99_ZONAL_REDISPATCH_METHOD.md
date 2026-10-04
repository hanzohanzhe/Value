# Prompt 99: single-period zonal redispatch method

Date: 21 August 2026  
Status: analytical implementation accepted; independent oracle validation is
reserved for Prompt 103

## Scope

`value-zonal-redispatch-balancing` clears one realised half-hour after the
national ahead schedule has been fixed. It uses SciPy/HiGHS and the signed
lossless zonal network pack. It is a computational transport and ETYS cut-set
model. It is not DC power flow, AC power flow, N-1 security analysis, network
expansion or a forecast-perfect annual optimisation.

The module does not alter the retained Scheme C source. It implements the
public `force.balancing-module/v1` contract and is discovered through the v2
workspace registry. The older standalone `module_registry.py` is deliberately
not given a second registration path.

## Signed quantities and balance

For bid (i), (x_i\geq 0) is the accepted bid magnitude in MWh. An upward bid
has signed adjustment (+x_i); a downward bid has signed adjustment (-x_i).
For corridor (c=(a,b)), (f_c>0) means transfer from zone (a) to zone (b).
Load shedding (l_z\geq0) is an operator action priced at the declared VOLL,
which defaults to £17,000/MWh.

For every zone (z), the solver enforces

\[
g^{ahead}_z + \sum_{i\in z}\Delta_i + l_z
+ \sum_{c\rightarrow z} f_c - \sum_{c\leftarrow z} f_c = d^{real}_z.
\]

All zone equations are simultaneous. Internal corridor flow cancels from the
GB-wide energy balance.

For boundary (b), the signed transfer is

\[
F_b=\sum_c m_{bc}f_c,
\qquad
-\bar F^{rev}_{b,t}\leq F_b\leq\bar F^{fwd}_{b,t},
\]

where the period rating includes the signed pack's maintenance multiplier.
Optional individual corridor envelopes use separate forward and reverse limits.
They do not turn a computational corridor into a physical circuit.

## Resource constraints

Final thermal, VRE and other positive-injection dispatch cannot exceed realised
availability and cannot fall below zero. Signed interconnector output stays
inside its declared current-period envelope: a positive import profile permits
`0..profile`, while a negative export profile permits `profile..0`.

Storage uses discharge (q^+\geq0) and charge (q^-\geq0):

\[
q^+-q^-=g^{ahead}+\sum_i\Delta_i,
\]

\[
SOC_t=SOC_{t-1}-q^+/\eta_d+q^-\eta_c.
\]

Power, energy and SOC bounds are explicit. The v1 storage offer must declare
`convex_net_power_v1`, with at most one bid in each direction and a nondecreasing
charge-to-discharge slope. Physical-throughput minimisation and post-solve
validation reject simultaneous charge and discharge rather than silently
approximating a non-convex offer.

## Objective and ties

The four deterministic phases are:

1. minimise signed accepted pay-as-bid value plus VOLL load shedding;
2. fix that optimum and minimise absolute adjustment from the ahead schedule;
3. fix both optima and minimise storage throughput and absolute corridor flow;
4. fix all earlier optima and apply a stable variable key.

Equal-price bids with the same direction, zone, network effect and resource
class are constrained to accept the same fraction of their available volume.
This makes partial acceptance proportional rather than dependent on HiGHS' row
ordering.

## Failure and evidence

A malformed contract or unsuccessful solve fails the network run. When an
output directory is configured, FORCE retains the exact declared input, pack
identity, phase, HiGHS message, residual information and runtime environment in
`market/failures/`. It never converts the failed run into a copperplate result.
A copperplate rerun must be a separately declared linked run.

Successful configured runs write a compact diagnostics JSON containing solver
phases, objectives and residuals. Period results expose accepted adjustments,
final dispatch, SOC, VRE curtailment, load shedding, corridor flow and boundary
transfer. Prompt 100 will add the persistent settlement, counterfactual and
reliability ledger; Prompt 103 will assemble the independent PuLP/CBC oracle.
