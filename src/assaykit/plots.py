"""Publication-style figures (matplotlib). `figures_for(result)` returns every figure for a result."""

from __future__ import annotations

import math
from functools import partial

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.figure import Figure
from matplotlib.ticker import MaxNLocator

from assaykit.common import AssayResult
from assaykit.dpph import logistic

# Validated categorical order (CVD-safe for adjacent series); fixed, never cycled.
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
INK, INK_2, MUTED, GRID, SURFACE = "#0b0b0b", "#52514e", "#8a8985", "#e4e3df", "#fcfcfb"
ERR_LABEL = {"sem": "SEM", "sd": "SD"}


def _style(ax, title: str = "", xlabel: str = "", ylabel: str = ""):
    ax.set_facecolor(SURFACE)
    ax.figure.set_facecolor(SURFACE)
    if title:
        ax.set_title(title, loc="left", fontsize=12, fontweight="bold", color=INK, pad=12)
    ax.set_xlabel(xlabel, color=INK_2, fontsize=10)
    ax.set_ylabel(ylabel, color=INK_2, fontsize=10)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=INK_2, labelsize=9, length=0)
    ax.grid(color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def bars(
    table: pd.DataFrame,
    title: str,
    xlabel: str,
    err: str = "sem",
    mean_col: str = "mean",
    err_col: str | None = None,
    limits: dict[str, float] | None = None,
    label_col: str = "sample_id",
    better: str = "",
    alpha: float = 0.05,
) -> Figure:
    """Horizontal bars, mean ± error, Tukey letters at the bar end, optional reference lines."""
    s = table.dropna(subset=[mean_col]).reset_index(drop=True)
    err_col = err_col or err
    e = s[err_col].fillna(0) if err_col in s.columns else pd.Series(0.0, index=s.index)
    letters = s["letters"].fillna("") if "letters" in s.columns else pd.Series("", index=s.index)

    fig, ax = plt.subplots(figsize=(7.5, 0.6 * len(s) + 1.9))
    _style(ax, title, xlabel)
    ax.grid(axis="y", visible=False)
    y = np.arange(len(s))[::-1]
    ax.barh(y, s[mean_col], height=0.55, color=SERIES[0], zorder=2)
    ax.errorbar(s[mean_col], y, xerr=e, fmt="none", ecolor=INK_2, elinewidth=1.2, capsize=3, zorder=3)
    ax.set_yticks(y, s[label_col].astype(str))
    span = max(float((s[mean_col] + e).max()), 1e-12)
    for yi, m, ei, letter in zip(y, s[mean_col], e, letters):
        ax.text(m + ei + span * 0.02, yi, f"{m:.3g}" + (f"  {letter}" if letter else ""), va="center", fontsize=9, color=INK)
    right = span * 1.25
    limits = limits or {}
    # Stack the reference-line labels so neighbouring limits don't overprint each other.
    for i, (name, value) in enumerate(sorted(limits.items(), key=lambda kv: kv[1])):
        ax.axvline(value, color=MUTED, linestyle="--", linewidth=1, zorder=1)
        ax.text(value, len(s) - 0.45 + 0.32 * i, f" {name}: {value:g}", fontsize=7.5, color=INK_2, va="bottom")
        right = max(right, value * 1.6)
    ax.set_xlim(0, right)
    ax.set_ylim(-0.6, len(s) - 0.4 + (0.35 + 0.32 * len(limits) if limits else 0))
    note = f"Mean ± {ERR_LABEL.get(err, err)}."
    if letters.str.len().any():
        note += f" Bars sharing a letter are not significantly different (Tukey HSD, α = {alpha:g}); 'a' = {better or 'highest'}."
    fig.text(0.01, 0.01, note, fontsize=7.5, color=INK_2)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    return fig


def standard_curve(res: AssayResult) -> Figure:
    curve, std, samples = res.extra["curve"], res.extra["standards"], res.extra["samples"]
    spec = res.extra["spec"]
    fig, ax = plt.subplots(figsize=(7.5, 4.8))
    _style(ax, f"{spec.name}: {spec.standard.lower()} standard curve ({spec.wavelength_nm} nm)",
           f"{spec.standard} (µg/mL)", "Absorbance (blank-corrected)")
    cuvette = curve.concentration(samples["abs_corrected"])
    xmax = max(std["std_conc_ug_ml"].max(), np.nanmax(cuvette)) * 1.05
    xs = np.linspace(0, xmax, 50)
    ax.plot(xs, curve.slope * xs + curve.intercept, color=MUTED, linewidth=1.5, zorder=1)
    ax.scatter(std["std_conc_ug_ml"], std["abs_corrected"], s=42, color=SERIES[0], edgecolor=SURFACE,
               linewidth=1.5, zorder=3, label="Standards")
    ax.scatter(cuvette, samples["abs_corrected"], s=42, color=SERIES[1], marker="D", edgecolor=SURFACE,
               linewidth=1.5, zorder=3, label="Samples (read off the curve)")
    ax.text(0.02, 0.95, curve.label(), transform=ax.transAxes, va="top", fontsize=9, color=INK)
    ax.legend(frameon=False, fontsize=8.5, labelcolor=INK_2, loc="lower right")
    fig.tight_layout()
    return fig


def dpph_curves(res: AssayResult, err: str = "sem") -> Figure:
    data = res.rows[res.rows["concentration"] > 0]
    curve = data.groupby(["sample_id", "concentration"], sort=False)["inhibition_pct"].agg(
        mean="mean", sd="std", n="count").reset_index()
    curve["sem"] = curve["sd"] / np.sqrt(curve["n"])
    ic50 = res.extra["ic50"].set_index("sample_id")
    fig, ax = plt.subplots(figsize=(7.5, 4.8))
    _style(ax, "DPPH radical scavenging", f"Concentration ({res.extra['conc_unit']}, log scale)", "Inhibition (%)")
    ax.set_xscale("log")
    ax.axhline(50, color=MUTED, linewidth=1, linestyle="--", zorder=1)
    for i, (sample, sub) in enumerate(curve.groupby("sample_id", sort=False)):
        if sample not in ic50.index:
            continue
        color = SERIES[i % len(SERIES)]
        m = ic50.loc[sample, "mean"]
        label = f"{sample}  (IC50 {m:.3g})" if pd.notna(m) else f"{sample}  (IC50 not reached)"
        ax.errorbar(sub["concentration"], sub["mean"], yerr=sub[err].fillna(0), fmt="o", color=color,
                    markersize=6, markeredgecolor=SURFACE, markeredgewidth=1.5, elinewidth=1.2, label=label, zorder=3)
        fit = res.extra["fits"].get(sample)
        if fit:
            xs = np.geomspace(sub["concentration"].min() * 0.8, sub["concentration"].max() * 1.25, 200)
            ax.plot(xs, logistic(xs, fit["top"], fit["ic50_rel"], fit["hill"]), color=color, linewidth=2, zorder=2)
    ax.set_ylim(min(-5, curve["mean"].min() - 5), 105)
    ax.legend(frameon=False, fontsize=8.5, labelcolor=INK_2, loc="upper left")
    fig.tight_layout()
    return fig


def minerals_grid(res: AssayResult, err: str = "sem") -> Figure:
    """One small panel per element: elements span orders of magnitude, so each gets its own scale."""
    s = res.summary
    elements = list(s["element"].unique())
    samples = list(s["sample_id"].unique())
    cols = 3
    rows_n = math.ceil(len(elements) / cols)
    fig, axes = plt.subplots(rows_n, cols, figsize=(9, 1.0 + 0.35 * len(samples) * rows_n + 0.6 * rows_n),
                             squeeze=False)
    for i, (ax, element) in enumerate(zip(axes.flat, elements)):
        sub = s[s["element"] == element].set_index("sample_id").reindex(samples)
        _style(ax)
        ax.set_title(element, loc="left", fontsize=10, fontweight="bold", color=INK)
        ax.grid(axis="y", visible=False)
        y = np.arange(len(samples))[::-1]
        means = sub["mean"].fillna(0) if "mean" in sub else pd.Series(0.0, index=sub.index)
        e = sub[err].fillna(0) if err in sub else pd.Series(0.0, index=sub.index)
        ax.barh(y, means, height=0.55, color=SERIES[0], zorder=2)
        if e.any():
            ax.errorbar(means, y, xerr=e, fmt="none", ecolor=INK_2, elinewidth=1, capsize=2, zorder=3)
        ax.set_yticks(y, samples if i % cols == 0 else [""] * len(samples))
        top = float((means + e).max())
        if top <= 0:
            ax.set_xticks([])  # nothing detected: an axis scale would be meaningless
            top = 1.0
        ax.set_xlim(0, top * 1.5)
        ax.xaxis.set_major_locator(MaxNLocator(4))
        for yi, m, ei, text in zip(y, means, e, sub["result"]):
            ax.text(m + ei + top * 0.04, yi, text, va="center", fontsize=8, color=INK if text != "ND" else MUTED)
    for ax in list(axes.flat)[len(elements):]:
        ax.set_visible(False)
    fig.suptitle("Mineral elements (mg/kg, AAS)", x=0.01, ha="left", fontsize=12, fontweight="bold", color=INK)
    fig.text(0.01, 0.005, "ND = not detected (below the detection limit). Each panel has its own scale.",
             fontsize=7.5, color=INK_2)
    fig.set_facecolor(SURFACE)
    fig.tight_layout(rect=(0, 0.03, 1, 0.97))
    return fig


def figures_for(res: AssayResult, err: str = "sem") -> dict[str, Figure]:
    """All standard figures for a result, keyed by a file-friendly name."""
    bars = partial(globals()["bars"], alpha=res.extra.get("alpha", 0.05))
    if res.assay == "Qualitative screening":
        return {}
    key = res.assay.lower().replace(" ", "_").replace("(", "").replace(")", "").replace("&", "and")
    if res.extra.get("reported"):
        figures = {}
        for element, group in res.summary.groupby("element", sort=False, dropna=False):
            label = group.assign(label=[f"{r.sample_id}" if pd.isna(r.concentration) else f"{r.sample_id} @ {r.concentration:g}"
                                        for r in group.itertuples()])
            if label["mean"].notna().any():
                name = f"{key}_{element}" if element else key
                figures[name] = bars(label, res.assay + (f" · {element}" if element else ""), res.unit, err, label_col="label")
        return figures
    if res.assay == "DPPH":
        figs = {}
        if not res.extra["ic50"].empty:
            figs["dpph_curves"] = dpph_curves(res, err)
            figs["dpph_ic50"] = bars(res.extra["ic50"], "DPPH IC50", f"IC50 ({res.extra['conc_unit']})", err,
                                     better="lowest IC50 (strongest)")
        single = res.summary[~res.summary["sample_id"].isin(res.extra["ic50"].get("sample_id", []))]
        if not single.empty:
            single = single.assign(label=[f"{sid}" if pd.isna(c) else f"{sid} ({c:g})"
                                          for sid, c in zip(single["sample_id"], single["concentration"])])
            figs["dpph_inhibition"] = bars(single, "DPPH radical scavenging", "Inhibition (%)", err,
                                           label_col="label", better="highest scavenging")
        return figs
    if "curve" in res.extra and "spec" in res.extra:
        return {f"{key}_standard_curve": standard_curve(res),
                key: bars(res.summary, res.assay, res.unit, err, better="highest")}
    if res.assay == "Minerals (AAS)":
        return {"minerals": minerals_grid(res, err)}
    if res.assay == "Acid value":
        ffa = res.summary.rename(columns={"ffa_mean": "m", "ffa_sem": "fsem", "ffa_sd": "fsd"})
        return {
            "acid_value": bars(res.summary, "Acid value", res.unit, err, limits=res.extra["limits"], better="lowest"),
            "ffa": bars(ffa.assign(letters=res.summary["letters"]), "Free fatty acids",
                        f"% FFA (as {res.extra['fatty_acid']})", err, mean_col="m",
                        err_col="fsem" if err == "sem" else "fsd", better="lowest"),
        }
    if res.assay == "Peroxide value":
        return {"peroxide_value": bars(res.summary, "Peroxide value", res.unit, err, limits=res.extra["limits"],
                                       better="lowest")}
    lower = res.assay in ("Phytate", "Oxalate")
    return {key: bars(res.summary, res.assay, res.unit, err, better="lowest" if lower else "highest")}
