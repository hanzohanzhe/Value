"""Redraw the three VALUE excess/curtailment figures with large text."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta
from pathlib import Path
import pickle

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


RUN_ID = "20260718_decarb_virtual_pool_1000twh_scheme_c"
DEFAULT_OUTPUT = Path(__file__).resolve().parents[1] / "outputs"
YEARS = list(range(2025, 2035))
PROFILE_YEARS = [2025, 2030, 2034]
COLORS = {"solar": "#F4A261", "onshore": "#2A9D8F", "offshore": "#264653"}


def style() -> None:
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 17,
            "axes.labelsize": 21,
            "xtick.labelsize": 17,
            "ytick.labelsize": 17,
            "legend.fontsize": 17,
        }
    )


def annual_bars(excess_dir: Path, output: Path) -> None:
    summary = pd.read_csv(excess_dir / "excess_summary_by_year_scheme_c.csv")
    years = summary["year"].astype(int).to_numpy()
    total = summary["total_vre_twh"].to_numpy(float)
    excess = summary["excess_twh"].to_numpy(float)
    x = np.arange(len(years))
    width = 0.38

    fig, ax = plt.subplots(figsize=(15, 8.5))
    bars_total = ax.bar(
        x - width / 2, total, width, color="#4ECDC4", alpha=0.88,
        label="Total VRE generation (cleared + excess)",
    )
    bars_excess = ax.bar(
        x + width / 2, excess, width, color="#FF6B6B", alpha=0.88,
        label="Excess generation",
    )
    pad = max(total.max(), excess.max()) * 0.012
    for bars, colour in ((bars_total, "#155E59"), (bars_excess, "#991B1B")):
        for bar in bars:
            ax.text(
                bar.get_x() + bar.get_width() / 2, bar.get_height() + pad,
                f"{bar.get_height():.1f}", ha="center", va="bottom",
                rotation=90, fontsize=14, fontweight="bold", color=colour,
            )
    ax.set_ylabel("Energy (TWh)", labelpad=12)
    ax.set_xlabel("Year", labelpad=10)
    ax.set_xticks(x, years, rotation=35, ha="right")
    ax.set_ylim(0, max(total.max(), excess.max()) * 1.18)
    ax.grid(axis="y", alpha=0.30, linewidth=0.9)
    ax.set_axisbelow(True)
    ax.legend(loc="upper left", frameon=True, framealpha=0.95)
    fig.subplots_adjust(left=0.105, right=0.975, top=0.965, bottom=0.17)
    fig.savefig(output / "excess_generation_amount_scheme_c_large_text.png", dpi=240, facecolor="white")
    fig.savefig(output / "excess_generation_amount_scheme_c_large_text.pdf", facecolor="white")
    plt.close(fig)


def marginal_bars(marginal_dir: Path, output: Path) -> None:
    summary = pd.read_csv(marginal_dir / "marginal_1mw_curtailment_summary_potential_2025_2034.csv")
    detail = pd.read_csv(marginal_dir / "marginal_1mw_curtailment_detail_potential_2025_2034.csv")
    x = np.arange(len(YEARS), dtype=float)
    width = 0.22
    offsets = {"solar": -width, "onshore": 0.0, "offshore": width}

    fig, ax = plt.subplots(figsize=(15, 8.2))
    for tech in ("solar", "onshore", "offshore"):
        sub = summary[summary["Tech"] == tech].set_index("Year").reindex(YEARS)
        median = sub["median"].to_numpy(float)
        error = np.vstack(
            [
                np.maximum(median - sub["min"].to_numpy(float), 0),
                np.maximum(sub["max"].to_numpy(float) - median, 0),
            ]
        )
        xpos = x + offsets[tech]
        ax.bar(
            xpos, median, width * 0.92, color=COLORS[tech], alpha=0.92,
            label=tech.capitalize(), edgecolor="white", linewidth=0.5, zorder=3,
        )
        ax.errorbar(
            xpos, median, yerr=error, fmt="none", ecolor="#222222",
            elinewidth=1.3, capsize=3.5, capthick=1.3, zorder=4,
        )
    system = detail.groupby("Year")["System_excess_share_pct"].first().reindex(YEARS)
    ax.plot(
        x, system.to_numpy(float), color="#111111", linestyle="--", linewidth=2.6,
        label="System average: excess / total VRE", zorder=5,
    )
    ax.set_xticks(x, YEARS)
    ax.set_xlabel("Year", labelpad=10)
    ax.set_ylabel("Marginal curtailment of +1 MW (%)", labelpad=12)
    ax.set_ylim(0, 105)
    ax.grid(axis="y", alpha=0.30, linewidth=0.9, zorder=0)
    ax.legend(loc="upper left", ncol=2, frameon=True, framealpha=0.95)
    fig.subplots_adjust(left=0.115, right=0.975, top=0.965, bottom=0.14)
    fig.savefig(output / "marginal_1mw_curtailment_thinbars_scheme_c_large_text.png", dpi=240, facecolor="white")
    fig.savefig(output / "marginal_1mw_curtailment_thinbars_scheme_c_large_text.pdf", facecolor="white")
    plt.close(fig)


def profile_data(year: int, profiles: dict) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    delivered = np.asarray(profiles[year]["total_vre_generation"], dtype=float)[:17_520] * 0.5
    excess = np.asarray(profiles[year]["overall_excess"], dtype=float)[:17_520] * 0.5
    n = min(len(delivered), len(excess))
    return delivered[:n], excess[:n], delivered[:n] + excess[:n]


def profile_lines(checkpoint: Path, output: Path) -> None:
    with checkpoint.open("rb") as handle:
        profiles = pickle.load(handle)["vre_excess_profiles"]

    fig, axes = plt.subplots(3, 1, figsize=(17, 14), sharex=False)
    for ax, year in zip(axes, PROFILE_YEARS):
        delivered, excess, total = profile_data(year, profiles)
        dates = [datetime(year, 1, 1) + timedelta(minutes=30 * i) for i in range(len(total))]
        total_twh = total.sum() / 1e6
        delivered_twh = delivered.sum() / 1e6
        excess_twh = excess.sum() / 1e6
        share = 100 * excess_twh / total_twh if total_twh else 0

        ax.plot(dates, total, color="#5DADE2", linewidth=0.75, label="Total VRE (cleared + excess)")
        ax.plot(dates, excess, color="#E74C3C", linewidth=0.75, label="Excess generation")
        ax.set_title(str(year), loc="left", fontsize=20, fontweight="bold", pad=7)
        ax.set_ylabel("Generation\n(MWh/period)", fontsize=17, labelpad=11)
        ax.grid(alpha=0.28, linewidth=0.8)
        ax.xaxis.set_major_locator(mdates.MonthLocator(bymonth=[1, 3, 5, 7, 9, 11]))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b"))
        ax.tick_params(axis="both", labelsize=15, pad=5)
        ax.text(
            0.012, 0.91,
            f"Total VRE: {total_twh:.2f} TWh\nCleared: {delivered_twh:.2f} TWh\n"
            f"Excess: {excess_twh:.2f} TWh ({share:.1f}%)",
            transform=ax.transAxes, va="top", ha="left", fontsize=14,
            bbox=dict(boxstyle="round,pad=0.35", facecolor="white", alpha=0.90, edgecolor="#999999"),
        )

    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(
        handles, labels, loc="upper center", bbox_to_anchor=(0.5, 0.986),
        ncol=2, frameon=False, fontsize=17, handlelength=3.0, columnspacing=2.5,
    )
    axes[-1].set_xlabel("Date", fontsize=20, labelpad=9)
    fig.subplots_adjust(left=0.105, right=0.98, top=0.93, bottom=0.075, hspace=0.31)
    fig.savefig(output / "excess_generation_profiles_2025_2030_2034_scheme_c_large_text.png", dpi=220, facecolor="white")
    fig.savefig(output / "excess_generation_profiles_2025_2030_2034_scheme_c_large_text.pdf", facecolor="white")
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", type=Path, required=True, help="Directory containing run_logs and the retained scenario")
    parser.add_argument("--run-id", default=RUN_ID)
    parser.add_argument("--scenario", type=Path, help="Scenario directory containing checkpoints")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    run = args.run_root / "run_logs" / args.run_id
    scenario = args.scenario or args.run_root / f"03_future_cm_decarb_base_2025_2035_{args.run_id}"
    checkpoint = scenario / "checkpoints" / "case3_v2_existing_decarb_base_checkpoint.pkl"
    args.output.mkdir(parents=True, exist_ok=True)
    style()
    annual_bars(run / "plots_excess", args.output)
    marginal_bars(run / "plots_marginal_curtailment", args.output)
    profile_lines(checkpoint, args.output)
    print("redrew 3 figures")


if __name__ == "__main__":
    main()
