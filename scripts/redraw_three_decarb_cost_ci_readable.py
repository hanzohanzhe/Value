"""Redraw the three-scenario cost/carbon chart with readable typography."""
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import numpy as np
import pandas as pd


RUN_ID = "20260718_decarb_virtual_pool_1000twh_scheme_c"
DEFAULT_OUTPUT = Path(__file__).resolve().parents[1] / "outputs"
YEARS = np.arange(2025, 2035)

SCENARIOS = (
    ("existing_decarb_base", "Decarb base", "#2A9D8F"),
    ("subsidy_as_usual", "Subsidy as usual", "#E76F51"),
    ("governmental_target", "Gov target", "#2563EB"),
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", type=Path, required=True, help="Directory containing run_logs")
    parser.add_argument("--run-id", default=RUN_ID)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    source = args.run_root / "run_logs" / args.run_id / "plots_three_decarb" / "three_decarb_cost_ci_2025_2034.csv"
    frame = pd.read_csv(source)
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 18,
            "axes.labelsize": 22,
            "xtick.labelsize": 18,
            "ytick.labelsize": 18,
            "legend.fontsize": 18,
        }
    )

    fig, ax_cost = plt.subplots(figsize=(16, 9.5))
    ax_ci = ax_cost.twinx()
    for key, _label, color in SCENARIOS:
        subset = frame[frame["scenario_key"] == key].set_index("Year").reindex(YEARS)
        ax_cost.plot(
            YEARS, subset["cost_per_mwh_gbp"], color=color, linestyle="-",
            marker="o", linewidth=3.1, markersize=7.5, zorder=4
        )
        ax_ci.plot(
            YEARS, subset["overall_carbon_intensity_kg_per_mwh"], color=color,
            linestyle="--", marker="D", linewidth=2.8, markersize=7, zorder=3
        )
        ax_ci.plot(
            YEARS, subset["operational_carbon_intensity_kg_per_mwh"], color=color,
            linestyle=":", marker="s", linewidth=2.8, markersize=7, zorder=3
        )

    ax_cost.set_xlabel("Year", labelpad=10)
    ax_cost.set_ylabel("System cost (GBP/MWh)", labelpad=12)
    ax_ci.set_ylabel("Carbon intensity (kg CO$_2$/MWh)", labelpad=14)
    ax_cost.set_xticks(YEARS)
    ax_cost.set_xlim(2024.55, 2034.45)
    ax_cost.set_ylim(bottom=0)
    ax_ci.set_ylim(bottom=0)
    ax_cost.tick_params(axis="both", pad=7)
    ax_ci.tick_params(axis="y", pad=7)
    ax_cost.grid(axis="y", linestyle="--", linewidth=0.9, alpha=0.32)

    # Separate colour (scenario) from line style (metric). This preserves every
    # label while avoiding nine tiny, repetitive legend entries.
    scenario_handles = [
        Line2D([0], [0], color=color, linewidth=4, marker="o", markersize=8, label=label)
        for _key, label, color in SCENARIOS
    ]
    metric_handles = [
        Line2D([0], [0], color="#333333", linewidth=3, marker="o", label="System cost"),
        Line2D([0], [0], color="#555555", linewidth=3, linestyle="--", marker="D",
               label="Overall carbon intensity"),
        Line2D([0], [0], color="#6B7280", linewidth=3, linestyle=":", marker="s",
               label="Operational carbon intensity"),
    ]
    scenario_legend = fig.legend(
        handles=scenario_handles, loc="upper center", bbox_to_anchor=(0.5, 0.978),
        ncol=3, frameon=False, columnspacing=2.8, handlelength=2.7
    )
    fig.add_artist(scenario_legend)
    fig.legend(
        handles=metric_handles, loc="upper center", bbox_to_anchor=(0.5, 0.915),
        ncol=3, frameon=False, columnspacing=2.2, handlelength=2.8
    )

    # No title or run-ID text: devote the canvas to labels and data.
    fig.subplots_adjust(left=0.105, right=0.895, top=0.80, bottom=0.13)
    args.output.mkdir(parents=True, exist_ok=True)
    png = args.output / "three_decarb_cost_overall_operational_ci_large_text.png"
    pdf = args.output / "three_decarb_cost_overall_operational_ci_large_text.pdf"
    fig.savefig(png, dpi=240, facecolor="white")
    fig.savefig(pdf, facecolor="white")
    plt.close(fig)
    print(png)
    print(pdf)


if __name__ == "__main__":
    main()
