# Prompt 29 — Truthful compatibility-path hygiene and release scanning

Continue from the completed licensing/data-provenance update and the current
0.5.0-beta.1 release report. Read scientific Prompts 24, 25 and 28 before editing.
Act as a release engineer and preservation-boundary owner.

## Objective

Remove developer-machine path dependencies from distributable execution without
editing the retained Scheme C scientific source, and make the release scanner
distinguish a real absolute path from an ordinary escaped string. Correct the
current evidence: `compat/config.py` contains two real `E:\\...` weather defaults;
`compat/load_mechanism_costs.py` is a false positive caused by `year:\\n`.

## Non-duplication boundary

- Prompt 24 already established licensing and per-object data rights; do not redo
  that audit or change the UK pack.
- Prompt 25 already owns installation, locks and general portability; this prompt
  closes only the demonstrated compatibility-path and scanner defects.
- Prompt 28 remains the integrated gate. Do not manufacture a GO by allowlisting
  a path that is still present in a distributable runtime artifact.
- Preserve retained-source hashes and historical outputs. Do not edit the
  authoritative Scheme C tree or the installed data pack.

## Implement

1. Record a byte- and line-level baseline showing the two real weather paths and
   the `year:\\n` false positive. Update the release report so it does not claim
   that both files contain real developer paths.
2. Replace the byte-regex-only decision with a tested path detector that handles
   Python/JSON/string-literal context or otherwise requires a syntactically
   plausible absolute path. It must still catch Windows drive, UNC, user-profile,
   Desktop and POSIX home paths while rejecting escape sequences and prose.
3. Do not alter retained Scheme C files. Build a deterministic, source-hashed
   runtime overlay or packaged compatibility copy in which machine-specific
   weather defaults are an explicit unbound sentinel. The data-pack binding must
   supply both weather roles before any compatibility import can execute.
4. Fail with a typed compatibility/data-binding error when either weather role is
   absent. Never fall back to the original `E:` paths or current working directory.
5. Scan repository source, wheel, sdist and runtime overlay separately. A retained
   reference file may be reported as preserved reference evidence, but it cannot
   leak into a claimed portable runtime artifact.
6. Store overlay generator version, retained source hash, generated file hash and
   the exact mechanical substitutions in provenance and SBOM inputs.

## Tests and acceptance

- `year:\\n`, URLs and escaped control strings do not trigger an absolute-path
  failure.
- Deliberately injected `C:\\Users\\...`, `E:\\weather\\...`, UNC and `[LOCAL_PATH_REDACTED]`
  paths fail with file and line evidence.
- A clean copied install with no `E:` drive runs the synthetic two-period and
  two-year workflows through the website worker.
- Removing a weather binding fails before the first period and never opens the
  retained default path.
- The generated overlay is deterministic and the retained hashes remain unchanged.
- Fresh wheel/sdist scans contain no developer path, prohibited UK data or silent
  source substitution.

## Stop condition

If portable execution still imports a retained file containing a live absolute
default, keep `PUBLIC_BINARY_BETA_NO_GO`. Do not weaken the scanner to pass the
artifact.

## Deliverable

Provide the corrected diagnostic, scanner design and mutation cases, runtime
overlay manifest, clean-location execution proof, artifact scans and updated
release decision.
