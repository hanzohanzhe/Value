# Prompt 25 — Reproducible installation, environment locking and CI

Continue from accepted Prompt 24. Read the current Python/Node requirements,
launchers, preflight and Python 3.10 Scheme C compatibility rules. Act as a release
and developer-experience engineer.

## Objective

Allow a non-programmer to install and launch the local website reproducibly, and
allow contributors to verify the open core in clean CI environments.

## Non-duplication boundary

- Reuse preflight diagnostics and the existing local service; do not add a second
  backend/frontend stack.
- Keep the verified Scheme C environment on Python 3.10 unless a new numerical
  validation explicitly approves another version.
- Do not auto-download large/proprietary data or dependencies without consent.

## Implement

1. Pin direct and transitive Python and frontend dependencies with reproducible
   lock artifacts. Separate mandatory open-core, Scheme C compatibility and
   optional export/solver groups.
2. Add an environment doctor that checks architecture, Python, Node, solver,
   ports, writable storage, disk headroom and optional capabilities with actionable
   English messages.
3. Provide a Windows one-click launcher/installer path that creates the approved
   environment, builds/serves the frontend, starts the loopback-only service and
   opens or prints the correct `http://127.0.0.1:<port>` URL. Repeated launch must
   be idempotent and avoid orphan services.
4. Add a documented contributor install and optional portable environment
   (for example Conda or container) where compatible. Keep path handling independent
   of the developer's username/Desktop layout.
5. Add CI for formatting/static checks, Python tests, frontend build/tests,
   synthetic-pack integration, bundle validation, source-preservation manifest and
   package build. Use Windows for the verified Scheme C compatibility gate and
   another platform only for components genuinely portable there.
6. Cache dependencies safely, publish no local data, and attach test/release
   reports with exact versions. Add software bill of materials and dependency
   vulnerability reporting as informative/blocking according to documented policy.
7. Version the application and schema migrations; support upgrade without
   rewriting immutable historical runs.
8. Remove developer-machine path dependencies from production and tests. Locate
   packaged resources through the installed package/application root, put mutable
   state in an explicit user-data directory, resolve data packs through manifests,
   and pass run paths as typed configuration. Reject committed `C:\\Users\\...`,
   Desktop, temporary-directory and current-working-directory assumptions with a
   CI source scan and portable-path tests.
9. Make optional solver/export/data capabilities installable through named extras
   or installer choices with compatible lock files. The one-click launcher must
   explain and install the selected perfect-foresight solver path or leave it
   clearly unavailable without breaking FORCE agent bidding.
10. Simulate both a non-programmer and contributor workflow in CI: clean checkout
   or signed package, install, first launch, health check, synthetic project,
   external module/data-adapter conformance, restart, upgrade and uninstall. No
   step may depend on files outside the packaged fixture set.

## Tests and acceptance

- Test installation and launch in a clean Windows environment with no pre-existing
  project virtual environment.
- Browser health check reaches the local service and synthetic project workflow.
- Lockfile recreation is deterministic under the documented tool versions.
- CI fails on retained-source mutation, package inclusion of prohibited data and
  broken frontend/backend contracts.
- A path containing spaces and non-ASCII characters works.
- Relocating the installed application and data directory does not change model
  fingerprints or break imports/checkpoint validation.
- Uninstall/cleanup identifies exact application files and leaves research data
  unless the user explicitly chooses otherwise.

## Stop condition

If a clean install still requires undocumented shell commands or manual source
editing, the non-programmer installation gate remains failed.

## Deliverable

Provide supported environments, lock strategy, installer/launcher flow, CI matrix,
clean-machine evidence and upgrade/uninstall policy.
