# Prompt 50 — Reproducible source-release tree

Continue after Prompt 49. Reuse Prompt 25 installation, Prompt 45 data separation
and Prompt 46 package scans.

## Objective

Ensure the release source archive contains the actual FORCE core, tests, website,
manifests and licences while excluding local runs, large UK data and caches.

## Non-duplication boundary

- Keep the Python wheel as the core-library artifact and the UK pack as a separate
  per-object data asset.
- Do not bundle historical outputs or installed local data into source releases.
- Do not stage or commit the user's working tree automatically.

## Implement

1. Define an allowlisted, versioned source-release manifest and a deterministic
   scanner that fails when required public components are absent or prohibited
   local artifacts are present.
2. Distinguish four deliverables: Python wheel/sdist, full source/website archive,
   CC0 synthetic pack, and separate UK public-data asset.
3. Select npm/package-lock as the frontend dependency authority already used by
   the installer and CI; remove contradictory package-manager metadata without
   changing application code.
4. Expand CI to run the complete Python suite and the post-Prompt-46 correctness
   gates, while retaining a bounded portable-open-core job.
5. Record that Git tracking/staging is a separate maintainer action; a clean
   source archive must not depend on current Git index state.

## Acceptance

- Source-release scan includes backend, core, frontend, tests, docs, manifests,
  licences, lockfiles and launchers.
- It rejects outputs, local state, large real data, caches and developer paths.
- Installer, package metadata and CI name one frontend lock authority.
- The scanner and a source-tree test pass locally.

## Stop condition

Do not call a wheel the complete website product, and do not claim GitHub release
readiness while the public source set would be omitted from a clean checkout.
