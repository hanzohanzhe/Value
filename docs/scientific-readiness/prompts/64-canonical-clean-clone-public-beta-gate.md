# Prompt 64 — Canonical clean-clone public-beta gate

Execute after Prompts 59-63 have either passed or produced an explicitly accepted
bounded limitation. Read Prompts 28, 41, 46, 50-55 and the current release
evidence. Act as the final release engineer, independent test lead and scientific
claims auditor. Do not implement new model features in this prompt.

## Objective

Issue the first release decision tied to one canonical Git commit rather than a
mixture of the working tree, a demo copy and historical archives. Prove what a
new user can install and run from a fresh checkout, while reusing still-valid
annual and ten-year scientific evidence instead of rerunning it reflexively.

## Frozen release candidates

Treat these as separate products with separate decisions and hashes:

1. FORCE open-source code and website source;
2. built wheels/sdist and dependency locks;
3. CC0 synthetic tutorial/CI data;
4. rights-governed UK research-data bundle or local installer asset;
5. documentation and machine-readable scientific evidence.

No product may silently include another product whose redistribution decision is
different.

## Non-duplication and evidence-reuse rule

- Reuse Prompt 46/52 full-year, causal two-year and paired ten-year bundles when
  the canonical commit has identical scientific source, module graph, input
  hashes and parameter fingerprints.
- Generate a `science-impact.json` comparing the last accepted scientific commit
  with the release commit. It must classify changes to contracts, adapters,
  PSM/CEM modules, storage policy, state transition, ledgers, UI, packaging,
  documentation and data bytes.
- Packaging, rights, prose and UI-only changes do not authorize a new annual or
  ten-year calculation. If an affected scientific hash changed, run the minimum
  test ladder defined in `POST_58_ALIGNMENT_PLAN.md` and explain why.
- Do not use smoke chronology as annual evidence and do not relabel the retained
  Scheme C comparison as FORCE numerical parity.

## Gate sequence

1. **Canonical source gate.** Verify the commit is reachable from the intended
   protected release branch/tag, the worktree used to build is clean, every
   source-release manifest member is tracked, generated files are current and
   no private output/data/cache/member is included accidentally.
2. **Fresh-clone gate.** On clean Windows and Linux environments, install the
   supported Python runtime and Node dependencies from locks, build wheel/sdist
   and frontend, run the doctor, start the loopback service and open the product
   without developer-specific absolute paths.
3. **Synthetic public path.** Install the CC0 pack, create a Study, resolve the
   declared module graph, run the supported smoke workflow, inspect market and
   curtailment pages, export a bundle and validate it in a second clean directory.
4. **UK local-data path.** Install the exact Prompt 61 UK bundle locally, verify
   all conditional/required roles, provenance and hashes, then run the bounded
   real-data verification appropriate to `science-impact.json`.
5. **External module path.** Build and install a deterministic Prompt 58 example
   bundle, acknowledge executable-code risk, select it in a Study, prove actual
   invocation, disable it safely and preserve the completed run.
6. **Security and operations gate.** Apply Prompt 62 dependency/security policy;
   verify loopback binding, archive traversal defenses, cancellation, quota,
   recovery and exact destructive-action targets.
7. **Documentation gate.** Test every copyable install/start/stop/module/data
   command in the bilingual guide. Verify licences, attribution, citations,
   security contact, data availability, model limitations and method-three
   extension status agree across generated and human-readable pages.
8. **Scientific evidence gate.** Validate all reused or newly required run bundles,
   independent clearing evidence, cost/carbon ledgers and declared divergence.
   Link each public claim to a specific immutable artifact and commit.

## Required decisions

Return independent `GO`, `BOUNDED_GO`, `NO_GO` or `NOT_EVALUATED` decisions for:

- local single-node FORCE application;
- reproducible source checkout and build;
- code-package publication;
- synthetic-data publication;
- UK research-data redistribution/installation;
- external in-process module installation;
- FORCE clearing scientific validation;
- dynamic storage pricing as a selectable research method;
- current annual/ten-year scientific baseline.

One green row cannot override a red row in another product. A bounded performance
or annual-only recovery limitation must be visible in release notes, but it need
not falsely block a local beta whose scientific results remain valid.

## Acceptance

- Every published archive is deterministic, readable, scanned and tied to one
  source commit and manifest hash.
- Clean-clone install, frontend build, synthetic workflow and declared local UK
  workflow pass using documented commands.
- All required tests selected by `science-impact.json` pass; skipped expensive
  gates cite reusable immutable evidence and matching hashes.
- Retained Scheme C hashes and historical bundles are unchanged.
- Release notes contain no unsupported claims about transmission, AC power flow,
  universal optimality, data redistribution or exact Scheme C reproduction.

## Stop conditions

Return `NO_GO` for the affected product if the release tree is not reproducible,
rights metadata conflicts, an archive contains undeclared bytes, a scientific
hash lacks the required test level, or clean installation depends on the author's
machine. Do not repair science, data or architecture inside this gate; open a
numbered remediation prompt instead.

## Deliverables

- `science-impact.json` and canonical commit/release manifest;
- clean-clone Windows/Linux logs and artifact hashes;
- synthetic, UK-data and external-module installation evidence;
- claim-to-artifact matrix;
- human- and machine-readable Prompt 64 release report with the separate decisions.
