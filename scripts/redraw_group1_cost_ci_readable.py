"""Redraw the Base / Base+CM comparison for presentation and screenshots."""
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd


RUN_ID = "20260710_include_uncertain_scheme_c_cap"
DEFAULT_OUTPUT = Path(__file__).resolve().parents[1] / "outputs"
YEARS = np.arange(2025, 2035)
PERIODS = 17_520


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", type=Path, required=True, help="Directory containing run_logs")
    parser.add_argument("--run-id", default=RUN_ID)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    source = args.run_root / "run_logs" / args.run_id / "plots_group1" / "group1_cost_ci_deficit_2025_2034.csv"
    frame = pd.read_csv(source)
    base = frame[frame["scenario"] == "base"].set_index("Year").reindex(YEARS)
    cm = frame[frame["scenario"] == "with_cm"].set_index("Year").reindex(YEARS)

    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 18,
            "axes.labelsize": 22,
            "xtick.labelsize": 18,
            "ytick.labelsize": 18,
            "legend.fontsize": 17,
        }
    )

    fig, ax_cost = plt.subplots(figsize=(18, 10))
    ax_ci = ax_cost.twinx()
    ax_deficit = ax_cost.twinx()
    ax_deficit.spines["right"].set_position(("axes", 1.16))
    ax_deficit.spines["right"].set_color("#777777")

    teal = "#26998E"
    blue = "#2563EB"
    common = {"linewidth": 3.2, "markersize": 8, "zorder": 4}

    ax_cost.plot(
        YEARS, base["cost_per_mwh_gbp"], color=teal, marker="o",
        label="Base — system cost", **common
    )
    ax_cost.plot(
        YEARS, cm["cost_per_mwh_gbp"], color=blue, marker="o", linestyle="--",
        label="Base + CM — system cost", **common
    )
    ax_ci.plot(
        YEARS, base["operational_carbon_intensity_kg_per_mwh"], color=teal,
        marker="s", linestyle="--", label="Base — operational carbon intensity",
        **common
    )
    ax_ci.plot(
        YEARS, cm["operational_carbon_intensity_kg_per_mwh"], color=blue,
        marker="s", label="Base + CM — operational carbon intensity", **common
    )

    width = 0.34
    d_base = base["deficit_periods"].fillna(0).to_numpy()
    d_cm = cm["deficit_periods"].fillna(0).to_numpy()
    ax_deficit.bar(
        YEARS - width / 2, d_base, width, color=teal, alpha=0.40,
        label="Deficit periods — Base", zorder=1
    )
    ax_deficit.bar(
        YEARS + width / 2, d_cm, width, color=blue, alpha=0.40,
        label="Deficit periods — Base + CM", zorder=1
    )

    ax_cost.set_xlabel("Year", labelpad=10)
    ax_cost.set_ylabel("System cost (GBP/MWh)", labelpad=12)
    ax_ci.set_ylabel("Operational carbon intensity (kg CO$_2$/MWh)", labelpad=14)
    ax_deficit.set_ylabel(
        "Deficit periods (17,520 half-hour slots/year)", color="#666666", labelpad=18
    )

    ax_cost.set_xlim(2024.55, 2034.45)
    ax_cost.set_xticks(YEARS)
    ax_cost.set_ylim(0, 190)
    ax_ci.set_ylim(0, 165)
    ax_deficit.set_ylim(0, PERIODS)
    ax_deficit.set_yticks([0, 4380, 8760, 13140, 17520])
    ax_deficit.yaxis.set_major_formatter(
        mticker.FuncFormatter(lambda value, _position: f"{int(value):,}")
    )

    ax_cost.grid(axis="y", linestyle="--", linewidth=0.9, alpha=0.32)
    ax_cost.tick_params(axis="both", pad=7)
    ax_ci.tick_params(axis="y", pad=7)
    ax_deficit.tick_params(axis="y", colors="#666666", pad=9)

    handles, labels = [], []
    for axis in (ax_cost, ax_ci, ax_deficit):
        axis_handles, axis_labels = axis.get_legend_handles_labels()
        handles.extend(axis_handles)
        labels.extend(axis_labels)
    fig.legend(
        handles, labels, loc="upper center", bbox_to_anchor=(0.50, 0.985),
        ncol=2, frameon=False, columnspacing=2.0, handlelength=3.0,
        handletextpad=0.7, labelspacing=0.55
    )

    # No figure title: use the canvas for the data and readable labels.
    fig.subplots_adjust(left=0.095, right=0.745, top=0.80, bottom=0.12)
    args.output.mkdir(parents=True, exist_ok=True)
    png = args.output / "group1_cost_ci_deficit_combo_2025_2034_large_text.png"
    pdf = args.output / "group1_cost_ci_deficit_combo_2025_2034_large_text.pdf"
    fig.savefig(png, dpi=240, facecolor="white")
    fig.savefig(pdf, facecolor="white")
    plt.close(fig)
    print(png)
    print(pdf)


if __name__ == "__main__":
    main()
