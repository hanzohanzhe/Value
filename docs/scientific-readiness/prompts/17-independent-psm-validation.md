# Prompt 17 - Solver modularity and independent PSM validation

This former combined task is now an umbrella for two executable prompts. Do not
execute the old single-task interpretation separately.

1. `17a-optional-perfect-foresight-psm.md` adds a genuinely selectable,
   solver-backed perfect-foresight PSM module without changing the published
   FORCE storage-bidding method.
2. `17b-independent-multi-engine-psm-validation.md` validates both the actual
   FORCE bid-at-cost clearing path and the optional perfect-foresight module with
   an independently formulated optimization oracle.

Execute 17A only after Prompts 12, 15 and 16 are accepted. Execute 17B after 17A.
Prompt 17 is accepted only when both sub-prompts pass their own acceptance gates.

The separation is scientific, not cosmetic: the published FORCE storage-cost
rule is an agent offer rule, while perfect-foresight storage is centrally
co-optimized and therefore has no storage offer-price rule.
