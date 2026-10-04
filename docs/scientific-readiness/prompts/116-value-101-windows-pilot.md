# Prompt 116 — VALUE 101 Windows pilot and manuals

## Purpose

Package the approved VALUE 101 teaching route as a current-user Windows
application that John Miles can install without a terminal, administrator
rights, an existing Python or Node installation, or internet access after the
download. Replace the retired Castle teaching name and publish one English and
one Chinese manual for the same scientific route.

## Reused contracts

This prompt does not add a teaching solver. It packages the Prompt 109–115
identity, data, Study, Run, comparison and optional fixed-network contracts. It
does not distribute the UK research pack, expose the internal AC experiment, or
change the retained Scheme C source.

## Required product boundary

- one file named `VALUE-101-Setup.exe`;
- current-user installation under `%LOCALAPPDATA%\VALUE-101`;
- private Python 3.10.11, Node 22.22.0 and locked Python dependencies;
- a visible determinate installation progress window;
- automatic loopback startup on ports 8766 and 8800;
- exactly four CC0 teaching packs: Baseline, Windy, High demand and the optional
  fixed three-zone network pack;
- transactional application replacement with persistent teaching state kept
  outside the replaceable application directory;
- Start menu and desktop launchers, guide shortcut, stop shortcut and safe
  uninstaller;
- English Markdown/PDF, Chinese Markdown, a quick card and a pilot runbook.

## Acceptance evidence

The implementation was exercised on Windows with the generated executable.
The clean install used the bundled Python 3.10.11 and returned HTTP 200 from the
frontend and a healthy `force-native` API. Disk and API catalogues contained
only the four declared teaching packs. A baseline Study was created before an
overlay install; both immutable Study files retained the same SHA-256 after the
application was replaced. A real VALUE 101 baseline Run then completed both
teaching years.

Three faults found during the installed journey were corrected with regression
tests:

1. the general backend used to add an empty `uk-scheme-c` placeholder even when
   teaching packs already existed;
2. three teaching components used a development-only relative `/api` address,
   which returned HTML from the production frontend instead of JSON from the
   model service;
3. Windows PowerShell could discover `Get-NetTCPConnection` but receive access
   denied, causing port conflicts to be detected late. The launcher now uses
   the ordinary-user `netstat` path first and refuses an occupied port before it
   starts VALUE services.

The native progress-window test drives the actual C# controls, observes an
intermediate 42% extraction state, proves that early closing is disabled, and
then observes 100% with the Close button enabled.

## Scientific boundary

VALUE 101 runs 48 half-hours in each of two synthetic years. It demonstrates the
real modular PSM–CEM workflow and stored evidence, but it is not annual British
evidence and must not be annualised. The optional network lesson is a fixed,
lossless three-zone transport and pay-as-bid redispatch exercise. It is not DC
load flow, AC power flow, N-1 security analysis or transmission expansion.

## Stop conditions

Do not send the Windows pilot externally if installation changes another VALUE
workspace, the package contains a UK research asset, a public AC implementation
appears, teaching output is labelled annual, the progress window is absent, or
the clean-user gate in Prompt 117 fails.
