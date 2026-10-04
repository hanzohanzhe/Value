# Prompt 75 — Expanded-test version identity remediation

Opened by the Prompt 71 packaging gate. The expanded platform contained material
new extension, hydrology, DC, AC and transmission-expansion code while retaining
the Prompt 64 package identity `0.5.0b1`. A package manager could therefore treat
the expanded build as the already installed baseline, defeating explicit upgrade,
rollback and provenance semantics.

Assign this separate private test line Python version `0.6.0a1` and frontend/user
version `0.6.0-alpha.1`. Synchronise package locks, runtime display, citation,
changelog, current guides and version regression tests. Preserve historical
Prompt 52/64 reports and the retained Scheme C module versions. Rebuild twice,
prove byte reproducibility, install the wheel outside the source tree and rerun
the complete Python and frontend gates. This change alters release identity only,
not scientific equations or retained results.
