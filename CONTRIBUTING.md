# Contributing to VALUE

Before proposing a change, open an issue describing the scientific question,
data rights and expected contract impact. Model contributions must include a
versioned module manifest, units, assumptions, deterministic fixtures and a
public-contract conformance test. Data contributions must include source,
version, access date, exact licence, attribution, source hash, normalized hash
and transformation version.

Do not commit local UK data packs, run bundles, credentials or private thesis
drafts. VALUE compatibility changes must be made only in the repository copy;
the retained source is immutable. The release audit must pass before material is
published. Unless explicitly marked otherwise, intentionally submitted software
contributions are accepted under Apache-2.0 (see LICENSE and LICENSING.md). Contributors certify that they have
the right to submit their contribution. Documentation contributions are accepted
under CC BY 4.0; synthetic data intended for the shipped fixture must be eligible
for CC0 dedication. Other owner-authorized data contributions require an explicit applicable
licence; upstream materials retain their own terms. Existing valid grants
are not revoked.

## Backend test ratchet

The backend suite is gated by a fingerprinted ratchet rather than by a green
bar, because some tests depend on the host (Windows tools, the author's
private R0 source tree, optional pytest/pypdf, free disk space):

```bash
python -B scripts/run_backend_tests.py            # ratchet against the baseline
python -B scripts/run_backend_tests.py --strict   # also fail on fingerprint drift
python -B scripts/run_backend_tests.py --update-baseline   # delete fixed ids only
python -B scripts/run_backend_tests.py --pytest   # pytest-style modules (separate baseline)
```

* `tests/baselines/known-failures-linux-py310.txt` lists the failing test ids
  (`module.Class.method`, `IMPORT:module`) recorded at the branch point; its
  first line is the environment fingerprint.  A new failure, or a listed test
  that now passes, makes the run exit 1.  Adding an entry needs
  `--update-baseline --allow-add --reason "..."`; never add a real regression.
* `tests/baselines/quarantine.txt` holds host-dependent ids with a reason,
  owner and expiry milestone (`tests/baselines/milestone.txt`).  They are
  reported but excluded from the ratchet; an expired entry fails the run.
* Every test module runs in its own subprocess with `-B`,
  `PYTHONDONTWRITEBYTECODE=1` and private `HOME`, `TMPDIR`, `VALUE_DATA_HOME`
  and `PYTHONPYCACHEPREFIX` directories.

Every commit that adds, removes or edits a file also runs
`python -B scripts/refresh_source_release_manifest.py`
(release exclusions: `tests/baselines/release-exclusions.txt`).

## Local API boundary in code and tests

* Start the API in HTTP tests only through
  `tests.local_api_harness.start_local_api(data_home=...)`; it binds port 0,
  creates a session token and installs an opener that adds only
  `X-VALUE-Session`.  Tests that check the boundary itself send raw
  `http.client` requests (see `tests/test_local_api_boundary.py`).
* The API has no CORS and refuses any `Origin`, a cross-site
  `Sec-Fetch-Site`, a foreign `Host`, a missing session and form-style
  bodies; do not add per-route exceptions.  New routes go into
  `Handler._route_get`/`_route_post`, behind `_dispatch` and its guard.
* Frontend code calls same-origin `/api/...` (`app/features/shared/api.ts`)
  and never embeds an API port or a token.  Every POST sets an explicit
  non-form `Content-Type`.
* Scripts that call a running API use
  `backend.api_session.authorized_headers(<data home>, <port>)`.
