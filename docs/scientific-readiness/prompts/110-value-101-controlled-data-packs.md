# Prompt 110: controlled VALUE 101 data-pack family

## Purpose

Replace the single Castle teaching pack with three complete, deterministic and
independently installable VALUE 101 packs. The comparison must change one
scientific input dimension at a time while keeping the production PSM/CEM path
unchanged.

## Implemented packs

| Pack ID | Controlled meaning | Changed scientific roles |
| --- | --- | --- |
| `value-101-baseline-v1` | Deterministic 48-period synthetic baseline | Generated parent |
| `value-101-windy-v1` | Wind availability increased by 35%, capped at full output | `weather.wind`, `profiles.vre_onshore`, `profiles.vre_offshore` |
| `value-101-high-demand-v1` | Forecast and realised demand increased by 20% | `demand.forecast`, `demand.real` |

Every directory binds all 25 required roles, carries CC0-1.0 metadata and is
explicitly ineligible for annual economics or a scientific baseline claim.
Each has a machine-readable `derivation.json` recording its parent payload,
transform, affected roles and unchanged-role hash result.

## Wind transformation

The PSM input `weather.wind` stores wind speed, not per-unit availability. It
therefore cannot be multiplied by 1.35 or clipped to 1. The live VALUE wind
curve is cubic above the shared 3 m/s cut-in speed. For the synthetic values in
this pack, Windy uses:

```text
v_windy = [3^3 + 1.35 * (v_baseline^3 - 3^3)]^(1/3)
```

with full-output protection at 10.5 m/s. This multiplies the availability
numerator used by both the onshore and offshore curves by 1.35. The CEM's
per-unit wind profiles use `min(parent * 1.35, 1.0)` directly. The baseline
offshore profile is deliberately non-zero while installed offshore capacity is
zero; this preserves zero current offshore production while giving the
expansion module a meaningful synthetic resource profile.

## Installation contract

The local installer adds all three packs idempotently. It compares complete
pack trees. If a user already has different bytes under one of these immutable
IDs, the installer reports `conflict_preserved` and leaves both the user's
installed revision and the bundled source untouched.

## TDD evidence

The first run of `test_prompt110_value_101_pack_family.py` failed because the
new builder did not exist. After the initial implementation, the exact-diff
test exposed that the inherited offshore profile was all zero and therefore
could not change under the Windy transform. The baseline was corrected as
described above, after which the controlled-diff test passed.

Accepted verification on Python 3.10.11:

- pack-family contract: 4/4 passed;
- real VALUE PSM/CEM teaching-chain regression: 3/3 passed;
- data-pack validator: 3/3 passed;
- executable data adapters: 3/3 passed;
- checked-in deterministic rebuild: passed for all three packs.

This evidence validates a bounded teaching input family. It does not turn the
48-period examples into annual GB results.
