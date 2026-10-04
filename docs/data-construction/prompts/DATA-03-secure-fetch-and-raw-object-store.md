# DATA-03 — Secure fetch and raw-object store

Execute after DATA-02 passes. Act as a data-supply-chain engineer. This prompt
pins raw official objects; it does not interpret their scientific fields.

## Objective

Implement bounded acquisition, content-addressed storage, rights receipts and
atomic recovery for official source revisions.

## Required work

1. Fetch only a discovered SourceRevision from an allowlisted HTTPS domain.
2. Stream into a staging file with configured byte and time limits; compute
   SHA-256 during transfer and atomically install under `raw/sha256/<hash>`.
3. Record final resolved URL, status, headers, media type, byte size, retrieval
   time, licence snapshot and local object-store key in RawObjectReceipt.
4. Never expose the absolute object path through the service or API.
5. Reuse an existing verified object with the same hash and reject a receipt
   whose object no longer verifies.
6. Classify each revision as redistributable, pointer-only, local-use-only or
   needs-rights-review. Unknown rights block downstream promotion.
7. Make interrupted and cancelled fetches recoverable without altering a
   verified object or emitting a usable receipt.

## Acceptance gate

- Tests cover streaming hash, duplicate reuse, redirect allowlist, byte limit,
  media mismatch, cancellation, partial-file cleanup and corrupted-object
  detection.
- Fetching the same bytes through two revisions stores one object and two
  provenance receipts.
- Rights and provenance reports are deterministic apart from declared retrieval
  metadata.
- Archive members are not extracted by the fetch layer.
- Prompt 98 inventory can reference a pinned object without absolute paths.

## Stop conditions

Stop on arbitrary URL fetching, shell-based download commands, unbounded memory
downloads, unverified redirects or an operation that overwrites verified data.

## Deliverables

- secure fetch implementation;
- local content-addressed ObjectStore;
- RawObjectReceipt and rights records;
- failure and cancellation tests;
- DATA-03 gate record and commit.

