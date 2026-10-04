"""Redraw the single decarbonisation scenario chart with presentation-size text."""
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd


RUN_ID = "20260718_decarb_virtual_pool_1000twh_scheme_c"
DEFAULT_OUTPUT = Path(__file__).resolve().parents[1] / "outputs"

COST = "#2A9D8F"
OVERALL = "#E76F51"
OPERATIONAL = "#6B7280"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", type=Path, required=True, help="Directory containing run_logs")
    parser.add_argument("--run-id", default=RUN_ID)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    source = args.run_root / "run_logs" / args.run_id / "plots_three_decarb" / "three_decarb_cost_ci_2025_2034.csv"
    frame = pd.read_csv(source)
    frame = frame[frame["scenario_key"] == "existing_decarb_base"].sort_values("Year")
    years = frame["Year"].to_numpy()

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

    fig, ax_cost = plt.subplots(figsize=(15, 8.5))
    ax_ci = ax_cost.twinx()
    line = {"linewidth": 3.2, "markersize": 8, "zorder": 3}

    ax_cost.plot(
        years, frame["cost_per_mwh_gbp"], color=COST, marker="o",
        label="System cost", **line
    )
    ax_ci.plot(
        years, frame["overall_carbon_intensity_kg_per_mwh"], color=OVERALL,
        linestyle="--", marker="D", label="Overall carbon intensity", **line
    )
    ax_ci.plot(
        years, frame["operational_carbon_intensity_kg_per_mwh"], color=OPERATIONAL,
        linestyle=":", marker="s", label="Operational carbon intensity", **line
    )

    ax_cost.set_xlabel("Year", labelpad=10)
    ax_cost.set_ylabel("System cost (GBP/MWh)", labelpad=12)
    ax_ci.set_ylabel("Carbon intensity (kg CO$_2$/MWh)", labelpad=14)
    ax_cost.set_xticks(years)
    ax_cost.set_xlim(years.min() - 0.4, years.max() + 0.4)
    ax_cost.set_ylim(bottom=0)
    ax_ci.set_ylim(bottom=0)
    ax_cost.tick_params(axis="both", pad=7)
    ax_ci.tick_params(axis="y", pad=7)
    ax_cost.grid(axis="y", linestyle=":", linewidth=1.1, alpha=0.36)

    h_cost, l_cost = ax_cost.get_legend_handles_labels()
    h_ci, l_ci = ax_ci.get_legend_handles_labels()
    fig.legend(
        h_cost + h_ci, l_cost + l_ci,
        loc="upper center", bbox_to_anchor=(0.5, 0.975), ncol=3,
        frameon=False, columnspacing=2.1, handlelength=2.8, handletextpad=0.7
    )

    # Deliberately no title: maximize the useful plotting area for screenshots.
    fig.subplots_adjust(left=0.105, right=0.895, top=0.84, bottom=0.14)
    args.output.mkdir(parents=True, exist_ok=True)
    png = args.output / "decarb_base_cost_overall_operational_ci_large_text.png"
    pdf = args.output / "decarb_base_cost_overall_operational_ci_large_text.pdf"
    fig.savefig(png, dpi=240, facecolor="white")
    fig.savefig(pdf, facecolor="white")
    plt.close(fig)
    print(png)
    print(pdf)


if __name__ == "__main__":
    main()
