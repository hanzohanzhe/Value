# John pilot runbook

## Purpose

This test asks whether a modeller who understands the research idea but has not operated VALUE can install it, build the baseline Study, run one market day and locate the evidence without coaching.

## Before sending

1. Test `VALUE-Setup.exe` on an isolated Windows account or Windows Sandbox.
2. Keep the installer SHA-256 and English PDF guide beside the download link.
3. Confirm the pilot works offline after download.
4. Confirm that it contains only the baseline and optional network teaching packs, not UK research data or an AC module.

## Core usability test

Start the timer when John opens the installer. Do not direct his clicks unless the software blocks progress. Record whether he can:

- wait for installation and local startup to finish;
- open and explain Data Pack, Module, Study, Run and Results;
- create `VALUE 101 baseline`;
- distinguish the 48-period PSM-only lesson from the two-year annual model;
- run one market day;
- find bids, accepted dispatch and unused VRE;
- explain where a researcher installs a Data Pack or Module;
- distinguish System domain from Optional domain.

The complete two-year Run is a separate production-sized check. It may continue after the timed usability session. A completed annual result should contain 17,520 periods in each year and the PSM-CEM state transition.

## Optional network question

If time remains, ask John to explain the difference between the national single-node Study and the fixed three-zone redispatch Study. He should find the notice that the latter is a lossless transport-constraint method, not AC, voltage, N-1 or transmission-expansion analysis.

## Recovery

If the page does not open, start `VALUE` once. If that fails, use `Stop VALUE` and start it again. Preserve any Run error, the Run state under `%LOCALAPPDATA%\VALUE\state`, and installer or startup diagnostics under `%LOCALAPPDATA%\VALUE\diagnostics`; do not repair code during the timed session.

At the end, use `Stop VALUE`. Use the Start-menu `Uninstall VALUE` shortcut only when the isolated VALUE state is no longer needed. The older `%LOCALAPPDATA%\VALUE-101` pilot is separate, is not migrated and may remain installed.
