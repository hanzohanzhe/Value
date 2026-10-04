# VALUE 101 quick card

## Start

1. Double-click `VALUE-Setup.exe` and wait for the progress bar to finish.
2. Open [http://127.0.0.1:8800](http://127.0.0.1:8800).
3. Open `Learn`, then `Open lesson`.
4. Create `VALUE 101 baseline`.

## One-day lesson

1. Choose `Run one market day`.
2. VALUE clears 48 half-hours through the production PSM only.
3. Inspect bids in `Market replay` and unused renewable energy in `VRE & curtailment`.
4. Do not use this Run for annual income, cost or investment conclusions.

## Complete model

1. Choose `Run complete two-year model`.
2. VALUE clears 17,520 periods for 2025, executes the annual CEM lifecycle, and builds the 2026 state.
3. It then clears 17,520 periods for 2026 and executes the second annual lifecycle.
4. Return to `Runs` when the background calculation completes.

The complete model keeps compact period, dispatch, storage and unused-VRE evidence. Use the one-day lesson for the complete auction-level bidding record.

## Build your own model

- `Data`: map, validate and install a complete 25-role Data Pack.
- `Modules`: inspect contracts and install an executable module bundle.
- `Studies · Advanced`: select compatible module implementations.
- `Add data`: build adapters or a new optional-domain extension.

Research changes are installed and versioned through the normal Data Pack, Module and extension contracts.

## Scientific boundary

The data are synthetic CC0 teaching data, not a GB benchmark. The optional three-zone network is a fixed lossless transport and redispatch model, not AC, voltage or N-1 analysis.

## Stop or repair

Use `Stop VALUE` from the Start menu. Reinstall if a bundled pack is missing. VALUE will not terminate another program that owns port 8800 or 8766.
