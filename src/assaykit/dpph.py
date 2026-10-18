"""DPPH radical scavenging assay.

DPPH• is a stable purple radical in methanol (absorbance max 515–520 nm; read at 518 nm
on the Jenway 6100 in the thesis). Antioxidants donate a hydrogen atom or an electron and
reduce it to yellow DPPH-H, so absorbance falls as scavenging rises:

    % inhibition = (A₀ − A₁) / A₀ × 100

A₀ is the control (methanol + DPPH), A₁ the extract (or ascorbic acid standard) + DPPH.

Optional sample blank: coloured extracts absorb at 518 nm on their own, and cottonseed
is yellow from gossypol. Giving `abs_blank` (extract + methanol, no DPPH) subtracts that
colour, A₁ → A₁ − A_blank, so pigment isn't counted as scavenging.

With a dilution series (≥ 3 concentrations per sample) the tool also reports IC50, the
concentration giving 50 % inhibition (lower = stronger antioxidant). Three estimates are
available because the literature uses all three and they disagree near the curve's ends:

    logistic       3-parameter dose-response fit (inhibition is 0 at zero dose)
    interpolation  straight line between the two concentrations bracketing 50 %, on a log axis
    linear         least-squares line through all points, IC50 = (50 − c) / m
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
from scipy import optimize, stats

from assaykit.common import AssayInputError, AssayResult, prepare
from assaykit.stats import summarize

IC50_METHODS = ("logistic", "interpolation", "linear")
MIN_LEVELS_FOR_IC50 = 3


def analyze_dpph(
    df: pd.DataFrame,
    conc_unit: str = "µg/mL",
    method: str = "logistic",
    cv_limit: float = 10.0,
    alpha: float = 0.05,
) -> AssayResult:
    if method not in IC50_METHODS:
        raise AssayInputError(f"DPPH: IC50 method must be one of {', '.join(IC50_METHODS)}.")

    rows = prepare(df, "DPPH", required=["sample_id", "abs_sample", "abs_control"],
                   numeric=["abs_sample", "abs_control"], optional_numeric=["concentration", "abs_blank"])
    warns: list[str] = []
    if (rows["abs_control"] <= 0).any():
        raise AssayInputError("DPPH: abs_control must be greater than 0 (it is the methanol + DPPH reading).")
    if "concentration" not in rows.columns:
        rows["concentration"] = np.nan
    if (rows["concentration"] < 0).any():
        raise AssayInputError("DPPH: concentration cannot be negative.")

    blank = rows["abs_blank"].fillna(0.0) if "abs_blank" in rows.columns else 0.0
    rows["abs_corrected"] = rows["abs_sample"] - blank
    rows["inhibition_pct"] = (rows["abs_control"] - rows["abs_corrected"]) / rows["abs_control"] * 100

    if (rows[["abs_sample", "abs_control"]] > 1.5).any().any():
        warns.append("DPPH: some absorbances are above 1.5, outside the linear range of most "
                     "spectrophotometers. Consider diluting the DPPH solution.")
    if (rows["inhibition_pct"] > 105).any():
        warns.append("DPPH: some readings exceed 100 % inhibition, which usually means a coloured extract "
                     "needs a sample blank (abs_blank).")
    if (rows["inhibition_pct"] < -5).any():
        warns.append("DPPH: some readings are below 0 % inhibition (sample absorbs more than the control). "
                     "A coloured extract adds its own absorbance; record a sample blank (abs_blank).")

    # % inhibition per sample, at each concentration tested. Letters compare samples
    # tested at the same concentration (or all samples, if no concentrations are given).
    tables = []
    level_key = rows["concentration"].fillna(-1)
    for level, sub in rows.groupby(level_key, sort=False):
        t, _, sw = summarize(sub, "inhibition_pct", cv_limit=cv_limit, alpha=alpha)
        t.insert(1, "concentration", np.nan if level == -1 else level)
        tables.append(t)
        at = "" if level == -1 else f" at {level:g} {conc_unit}"
        warns += [f"DPPH{at} — {w}" for w in sw]
    summary = pd.concat(tables, ignore_index=True)

    ic50, ic50_reps, methods, fits = _ic50_tables(rows, method, cv_limit, alpha, warns)
    return AssayResult(
        assay="DPPH", unit="% inhibition", rows=rows, summary=summary, warnings=warns,
        extra={"ic50": ic50, "ic50_replicates": ic50_reps, "method_comparison": methods, "fits": fits,
               "method": method, "conc_unit": conc_unit, "value_col": "inhibition_pct"},
    )


def _ic50_tables(rows, method, cv_limit, alpha, warns):
    """IC50 for each sample that has a dilution series."""
    levels = rows[rows["concentration"] > 0].groupby("sample_id")["concentration"].nunique()
    series = levels[levels >= MIN_LEVELS_FOR_IC50].index
    empty = pd.DataFrame()
    if len(series) == 0:
        return empty, empty, empty, {}
    data = rows[rows["sample_id"].isin(series)]

    # Per replicate series, then mean ± SEM per sample: the form ANOVA needs.
    rep_records = []
    for (sample, rep), sub in data.groupby(["sample_id", "replicate"], sort=False):
        est = estimate_ic50(sub["concentration"].to_numpy(), sub["inhibition_pct"].to_numpy(), method)
        rep_records.append({"sample_id": sample, "replicate": rep, **est})
    reps = pd.DataFrame(rep_records)

    # Pooled fit per sample: draws the curve, and shows all three methods side by side.
    fits, method_rows = {}, []
    for sample, sub in data.groupby("sample_id", sort=False):
        x, y = sub["concentration"].to_numpy(), sub["inhibition_pct"].to_numpy()
        fits[sample] = fit_logistic(x, y)
        method_rows.append({"sample_id": sample, **{f"ic50_{m}": estimate_ic50(x, y, m)["ic50"] for m in IC50_METHODS}})

    valid = reps.dropna(subset=["ic50"])
    if len(valid):
        # Lower IC50 = stronger antioxidant, so 'a' marks the lowest IC50.
        table, _, sw = summarize(valid, "ic50", cv_limit=cv_limit, alpha=alpha, higher_is_better=False)
        warns += [f"DPPH IC50 — {w}" for w in sw]
    else:
        table = pd.DataFrame(columns=["sample_id", "n", "mean", "sd", "sem", "cv_pct", "letters"])
    notes = reps.groupby("sample_id", sort=False)["note"].apply(lambda s: "; ".join(sorted({n for n in s if n})))
    table = pd.DataFrame({"sample_id": [s for s in rows["sample_id"].unique() if s in series]}).merge(
        table, on="sample_id", how="left")
    table["note"] = table["sample_id"].map(notes).fillna("")
    for r in table.itertuples():
        if r.note:
            warns.append(f"DPPH {r.sample_id}: {r.note}.")
    return table, reps, pd.DataFrame(method_rows), fits


def logistic(x, top, ic50_rel, hill):
    """Dose-response curve with bottom fixed at 0 % inhibition."""
    x = np.asarray(x, dtype=float)
    with np.errstate(divide="ignore", over="ignore"):
        return top / (1.0 + (ic50_rel / x) ** hill)


def fit_logistic(x: np.ndarray, y: np.ndarray) -> dict | None:
    """Fit `logistic` to points with x > 0. Returns params and R², or None if it fails."""
    mask = (x > 0) & np.isfinite(y)
    x, y = x[mask], y[mask]
    if len(np.unique(x)) < 3:
        return None
    p0 = [max(min(y.max(), 100), 1), float(np.median(x)), 1.0]
    bounds = ([1.0, x.min() / 100, 0.2], [150.0, x.max() * 100, 6.0])
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            params, _ = optimize.curve_fit(logistic, x, y, p0=p0, bounds=bounds, maxfev=20000)
    except (RuntimeError, ValueError):
        return None
    pred = logistic(x, *params)
    ss_res = float(np.sum((y - pred) ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else np.nan
    return {"top": params[0], "ic50_rel": params[1], "hill": params[2], "r2": r2}


def estimate_ic50(x: np.ndarray, y: np.ndarray, method: str) -> dict:
    """Return {'ic50', 'r2', 'note'} for one concentration series."""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    note = ""
    if len(np.unique(x[x > 0])) < 2:
        return {"ic50": np.nan, "r2": np.nan, "note": "fewer than 2 non-zero concentrations"}

    if y.max() < 50:
        return {
            "ic50": np.nan,
            "r2": np.nan,
            "note": f"50 % inhibition not reached (max {y.max():.1f} % at {x[np.argmax(y)]:g}); IC50 > {x.max():g}",
        }

    if method == "logistic":
        fit = fit_logistic(x, y)
        if fit is None or fit["top"] <= 50:
            method, note = "interpolation", "logistic fit failed, used interpolation"
        else:
            # Absolute IC50: solve top / (1 + (c/x)^h) = 50.
            ic50 = fit["ic50_rel"] / (fit["top"] / 50 - 1) ** (1 / fit["hill"])
            return {"ic50": float(ic50), "r2": fit["r2"], "note": _range_note(ic50, x)}

    if method == "interpolation":
        means = pd.Series(y).groupby(x).mean()
        cx, cy = means.index.to_numpy(), means.to_numpy()
        cx, cy = cx[cx > 0], cy[cx > 0]
        above = np.nonzero(cy >= 50)[0]
        first = above[0]
        if first == 0:
            # Already ≥ 50 % at the lowest dose: extrapolate on the first segment.
            first = 1
            note = (note + "; " if note else "") + "≥ 50 % at lowest concentration (extrapolated)"
        x0, x1 = np.log10(cx[first - 1]), np.log10(cx[first])
        y0, y1 = cy[first - 1], cy[first]
        if y1 == y0:
            return {"ic50": np.nan, "r2": np.nan, "note": "flat response around 50 %"}
        ic50 = 10 ** (x0 + (50 - y0) * (x1 - x0) / (y1 - y0))
        return {"ic50": float(ic50), "r2": np.nan, "note": note}

    # linear
    res = stats.linregress(x, y)
    if res.slope <= 0:
        return {"ic50": np.nan, "r2": res.rvalue**2, "note": "inhibition does not increase with concentration"}
    ic50 = (50 - res.intercept) / res.slope
    return {"ic50": float(ic50), "r2": float(res.rvalue**2), "note": _range_note(ic50, x)}


def _range_note(ic50: float, x: np.ndarray) -> str:
    pos = x[x > 0]
    if ic50 > x.max():
        return f"IC50 extrapolated above highest concentration ({x.max():g})"
    if len(pos) and ic50 < pos.min():
        return f"IC50 extrapolated below lowest concentration ({pos.min():g})"
    return ""
