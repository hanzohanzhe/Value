# VALUE Product Installer Design

**Date:** 26 August 2026  
**Status:** Approved in conversation  
**Scope:** Windows current-user installer and release identity only

## Goal

Ship one self-contained Windows installer for the complete VALUE modelling
platform. The installed application can run the bundled synthetic teaching
models immediately and can run research models after the user installs a
compatible Data Pack or research suite.

`VALUE` is the product. `VALUE 101` remains the name of the optional tutorial
inside that product; it is not the installer, application, Windows package or
state location.

## Product identity

The release uses the following public Windows identities:

| Item | Identity |
| --- | --- |
| Installer | `VALUE-Setup.exe` |
| Product name | `VALUE` |
| Installation root | `%LOCALAPPDATA%\VALUE` |
| Application root | `%LOCALAPPDATA%\VALUE\app` |
| State root | `%LOCALAPPDATA%\VALUE\state` |
| Desktop shortcut | `VALUE` |
| Start-menu group | `VALUE` |
| Uninstaller | `Uninstall VALUE.exe` |
| Windows uninstall key | `VALUE` |

Installer progress, errors and diagnostics use `VALUE`, never `VALUE 101`.
Internal teaching Data Pack IDs and tutorial titles may retain `value-101` or
`VALUE 101` because they identify the lesson, not the product.

## Installation and isolation

The new product installs beside the pilot:

- `%LOCALAPPDATA%\VALUE-101` is neither modified nor removed;
- `%LOCALAPPDATA%\VALUE` starts with its own application and state;
- the installer does not silently copy old Studies, Runs or Data Packs;
- the old pilot can be removed later by its own uninstaller;
- VALUE upgrades replace only `%LOCALAPPDATA%\VALUE\app` and preserve
  `%LOCALAPPDATA%\VALUE\state`.

The installer remains current-user, terminal-free and offline after download.
It retains the existing progress window, stop-before-replace, rollback and
payload-integrity behaviour.

## Installed modelling capability

The installer contains the complete modular VALUE code, frontend, Python and
Node runtimes, module manifests, adapters and the two synthetic tutorial Data
Packs. It does not contain the separately governed UK research data.

After installation a user can:

1. open `Learn -> VALUE 101` and run the synthetic single-day and two-year
   teaching paths;
2. inspect and compose ordinary Studies, Modules and Data Packs;
3. install the separate VALUE-UK research suite;
4. run its copperplate or fixed-zonal Study;
5. install another compatible Data Pack or extension without reinstalling the
   application.

## Documentation

The installer carries three maintained PDFs:

- the VALUE 101 tutorial;
- the VALUE 101 to VALUE-UK guide;
- the VALUE methodology.

Their content continues to distinguish tutorial results from annual research
results. Windows shortcut and installer wording call the application `VALUE`.

## Failure and rollback behaviour

Installation fails closed when the old VALUE service cannot be stopped, the
payload does not match its manifest, extraction fails or the new service does
not start. A failed replacement restores the previous `%LOCALAPPDATA%\VALUE`
application and metadata. It never falls back to or edits the pilot directory.

Model-run failures must persist `status=failed` and
`execution_status=failed` even when optional provenance sealing encounters
transient SQLite files.

## Verification boundary

The release is accepted only if all of the following pass:

1. focused product-identity and installer tests;
2. C# installer compilation and embedded-payload audit;
3. first installation into a clean `%LOCALAPPDATA%\VALUE` root;
4. successful local frontend and backend health checks;
5. bundled VALUE 101 baseline run;
6. installation of the frozen VALUE-UK research suite;
7. VALUE-UK copperplate two-period-per-year, two-year smoke;
8. VALUE-UK zonal two-period-per-year, two-year smoke with redispatch artifacts;
9. in-place reinstall while VALUE is running, preserving new VALUE state;
10. proof that `%LOCALAPPDATA%\VALUE-101` and the source worktree are unchanged;
11. final SHA-256 for `VALUE-Setup.exe` and the unchanged UK suite.

No full annual or ten-year scientific run is part of installer acceptance.

## Out of scope

- automatic migration from VALUE 101;
- bundling the real UK research data in the EXE;
- changing PSM, CEM, storage pricing or transmission science;
- changing tutorial Data Pack IDs;
- cloud hosting, accounts or remote execution;
- declaring a new scientific baseline.
