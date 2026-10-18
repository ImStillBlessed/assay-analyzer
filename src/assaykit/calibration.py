"""Standard-curve assays: absorbance → concentration → mg standard-equivalents per gram.

Most colorimetric assays share one calculation, and only the reagent and the standard change:

    Assay                 Standard        Read at   Result
    Total phenolics       tannic acid     765 nm    mg TAE/g   (Folin–Ciocalteu)
    Total flavonoids      quercetin       415 nm    mg QE/g    (aluminium chloride)
    Total tannins         tannic acid     760 nm    mg TAE/g   (Folin–Denis)
    FRAP                  ascorbic acid   593 nm    mg AAE/g   (Fe³⁺-TPTZ → Fe²⁺-TPTZ)

The calculation:
    1. Fit  A = m·C + c  to the standards (blank-corrected).
    2. Read each sample off the curve:  C = (A − c) / m           [µg/mL in the cuvette]
    3. Undo any dilution:              C × dilution_factor
    4. Express per gram of material, either
         from the extraction:  C (µg/mL) × extract volume (mL) / sample mass (g) / 1000  → mg/g
         or from a stock:      C (µg/mL) / extract concentration (mg/mL)               → mg/g

Mineral analysis by AAS uses the same curve, one per element (`analyze_minerals`).

Input rows carry a `kind` column: 'standard', 'sample', or 'blank' (reagent blank,
averaged and subtracted from every reading when present).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import stats

from assaykit.common import AssayInputError, AssayResult, prepare, require_positive
from assaykit.stats import summarize

STD_UNITS = {"µg/mL": 1.0, "mg/mL": 1000.0, "mg/L": 1.0}


@dataclass(frozen=True)
class CurveAssay:
    key: str
    name: str
    standard: str
    abbrev: str
    wavelength_nm: int
    reference: str
    higher_is_better: bool = True

    @property
    def unit(self) -> str:
        return f"mg {self.abbrev}/g"


CURVE_ASSAYS = {
    a.key: a
    for a in [
        CurveAssay("tpc", "Total phenolic content", "Tannic acid", "TAE", 765, "Singleton & Rossi 1965"),
        CurveAssay("flavonoids", "Total flavonoids", "Quercetin", "QE", 415, "Boham & Kocipai 1994"),
        CurveAssay("tannins", "Total tannins", "Tannic acid", "TAE", 760, "Bajaj & Devsharma 1977"),
        CurveAssay("frap", "FRAP reducing power", "Ascorbic acid", "AAE", 593, "Benzie & Strain 1996"),
    ]
}


@dataclass
class Curve:
    slope: float
    intercept: float
    r2: float
    abs_range: tuple[float, float]
    n_levels: int

    def concentration(self, absorbance):
        return (np.asarray(absorbance, dtype=float) - self.intercept) / self.slope

    def label(self) -> str:
        sign = "+" if self.intercept >= 0 else "−"
        return f"A = {self.slope:.5g}·C {sign} {abs(self.intercept):.4f}   (R² = {self.r2:.4f})"


def fit_curve(std: pd.DataFrame, x: str, y: str, what: str) -> Curve:
    if std.empty:
        raise AssayInputError(f"{what}: no standard rows (kind = standard).")
    if x not in std or y not in std or std[x].isna().any() or std[y].isna().any():
        raise AssayInputError(f"{what}: every standard row needs a concentration in '{x}'.")
    if std[x].nunique() < 3:
        raise AssayInputError(f"{what}: the standard curve needs at least 3 different concentrations.")
    fit = stats.linregress(std[x], std[y])
    if fit.slope <= 0:
        raise AssayInputError(f"{what}: absorbance does not increase with standard concentration. Check the standards.")
    return Curve(float(fit.slope), float(fit.intercept), float(fit.rvalue**2),
                 (float(std[y].min()), float(std[y].max())), int(std[x].nunique()))


def _check_kind(rows: pd.DataFrame, what: str) -> pd.DataFrame:
    rows["kind"] = rows["kind"].astype(str).str.strip().str.lower()
    unknown = sorted(set(rows["kind"]) - {"standard", "sample", "blank"})
    if unknown:
        raise AssayInputError(f"{what}: 'kind' must be standard, sample or blank (found {', '.join(unknown)}).")
    return rows


def _curve_warnings(curve: Curve, samples: pd.DataFrame, what: str, min_r2: float) -> list[str]:
    warns = []
    if curve.r2 < min_r2:
        warns.append(f"{what}: standard curve R² is {curve.r2:.4f} (below {min_r2}). Results may be unreliable.")
    lo, hi = curve.abs_range
    high = samples[samples["abs_corrected"] > hi]["sample_id"].unique()
    low = samples[samples["abs_corrected"] < lo]["sample_id"].unique()
    for sid in high:
        warns.append(f"{what} {sid}: absorbance above the highest standard ({hi:.3f}), so the value is "
                     "extrapolated. Dilute the extract and re-read.")
    for sid in low:
        warns.append(f"{what} {sid}: absorbance below the lowest standard ({lo:.3f}), so the value is extrapolated.")
    return warns


def analyze_curve_assay(
    df: pd.DataFrame,
    assay: str | CurveAssay,
    std_unit: str = "µg/mL",
    min_r2: float = 0.99,
    cv_limit: float = 10.0,
    alpha: float = 0.05,
) -> AssayResult:
    spec = CURVE_ASSAYS[assay] if isinstance(assay, str) else assay
    what = spec.name
    if std_unit not in STD_UNITS:
        raise AssayInputError(f"{what}: standard unit must be one of {', '.join(STD_UNITS)}.")

    rows = prepare(df, what, required=["kind", "sample_id", "absorbance"], numeric=["absorbance"],
                   optional_numeric=["std_conc", "abs_blank", "dilution_factor", "sample_mass_g",
                                     "extract_volume_ml", "extract_mg_per_ml"])
    rows = _check_kind(rows, what)

    blanks = rows.loc[rows["kind"] == "blank", "absorbance"]
    blank_mean = float(blanks.mean()) if len(blanks) else 0.0
    own_blank = rows["abs_blank"].fillna(0.0) if "abs_blank" in rows.columns else 0.0
    rows["abs_corrected"] = rows["absorbance"] - blank_mean - own_blank

    std = rows[rows["kind"] == "standard"].copy()
    if "std_conc" not in std.columns:
        raise AssayInputError(f"{what}: standard rows need a 'std_conc' column ({std_unit}).")
    std["std_conc_ug_ml"] = std["std_conc"] * STD_UNITS[std_unit]
    curve = fit_curve(std, "std_conc_ug_ml", "abs_corrected", what)

    samples = rows[rows["kind"] == "sample"].copy()
    if samples.empty:
        raise AssayInputError(f"{what}: no sample rows (kind = sample).")
    samples["dilution_factor"] = samples.get("dilution_factor", pd.Series(1.0, index=samples.index)).fillna(1.0)
    require_positive(samples, ["dilution_factor", "sample_mass_g", "extract_volume_ml", "extract_mg_per_ml"], what)
    samples["conc_ug_ml"] = curve.concentration(samples["abs_corrected"]) * samples["dilution_factor"]

    value_col, unit, basis_warn = _per_gram(samples, spec)
    warns = _curve_warnings(curve, samples, what, min_r2) + basis_warn
    if (samples[value_col] < 0).any():
        warns.append(f"{what}: some samples read below the curve intercept and come out negative. "
                     "Check the blank and whether the sample is too dilute.")

    summary, comparison, stat_warns = summarize(samples, value_col, cv_limit=cv_limit, alpha=alpha,
                                       higher_is_better=spec.higher_is_better)
    return AssayResult(
        assay=what, unit=unit, rows=pd.concat([std, samples], ignore_index=True), summary=summary,
        warnings=warns + [f"{what} — {w}" for w in stat_warns],
        extra={"curve": curve, "standards": std, "samples": samples, "value_col": value_col,
               "blank_mean": blank_mean, "spec": spec, "comparisons": {"samples": comparison},
               "alpha": alpha, "std_unit": std_unit},
    )


def _per_gram(samples: pd.DataFrame, spec: CurveAssay) -> tuple[str, str, list[str]]:
    """Choose how to express results per gram, depending on which columns were filled in."""
    def full(col):
        return col in samples.columns and samples[col].notna().all()

    if full("sample_mass_g") and full("extract_volume_ml"):
        if (samples["sample_mass_g"] <= 0).any():
            raise AssayInputError(f"{spec.name}: sample_mass_g must be greater than 0.")
        samples["result_mg_per_g"] = samples["conc_ug_ml"] * samples["extract_volume_ml"] / samples["sample_mass_g"] / 1000
        return "result_mg_per_g", spec.unit, []
    if full("extract_mg_per_ml"):
        if (samples["extract_mg_per_ml"] <= 0).any():
            raise AssayInputError(f"{spec.name}: extract_mg_per_ml must be greater than 0.")
        samples["result_mg_per_g"] = samples["conc_ug_ml"] / samples["extract_mg_per_ml"]
        return "result_mg_per_g", spec.unit, []
    return "conc_ug_ml", f"µg {spec.abbrev}/mL", [
        f"{spec.name}: no sample_mass_g + extract_volume_ml (or extract_mg_per_ml) for every sample, "
        "so results are concentrations in the extract, not per gram."
    ]


# ---------------------------------------------------------------- minerals (AAS)


def analyze_minerals(df: pd.DataFrame, min_r2: float = 0.995, cv_limit: float = 10.0, alpha: float = 0.05) -> AssayResult:
    """Element concentrations by atomic absorption, one calibration curve per element.

        mg/kg = C_digest (mg/L) × dilution × digest volume (mL) / sample mass (g)

    Rows need `element`. Samples can carry either an `absorbance` (read off that
    element's curve) or a `reading_mg_l` if the instrument already reports
    concentration. Alternatively supply final result_mg_kg, or detection_status=nd
    without inventing a numeric value. Optional lod_mg_l or lod_mg_kg records the
    instrument limit. Otherwise LOD = 3 × SD(blank) / slope when there are ≥ 2 blanks.
    Unknown detection limits remain unknown. Numeric groups are compared to the
    mean normalized detection limit; groups mixing explicit ND and numeric rows
    are reported as censored, without calculating a mean or inferential statistics.
    """
    what = "Minerals (AAS)"
    rows = prepare(df, what, required=["kind", "element", "sample_id"], numeric=[],
                   optional_numeric=["absorbance", "reading_mg_l", "result_mg_kg", "lod_mg_l", "lod_mg_kg", "std_conc_mg_l", "dilution_factor",
                                     "digest_volume_ml", "sample_mass_g"])
    rows = _check_kind(rows, what)
    rows["element"] = rows["element"].astype(str).str.strip()
    for col in ("absorbance", "reading_mg_l", "result_mg_kg", "lod_mg_l", "lod_mg_kg", "std_conc_mg_l"):
        if col not in rows.columns:
            rows[col] = np.nan
    samples = rows[rows["kind"] == "sample"].copy()
    if samples.empty:
        raise AssayInputError(f"{what}: no sample rows (kind = sample).")
    samples["detection_status"] = samples.get("detection_status", pd.Series("auto", index=samples.index)).fillna("auto").astype(str).str.lower().str.strip()
    if not samples["detection_status"].isin(["auto", "detected", "nd"]).all():
        raise AssayInputError(f"{what}: detection_status must be auto, detected or nd.")
    final = samples["result_mg_kg"].notna()
    nd = samples["detection_status"].eq("nd")
    convert = ~final & ~nd
    for col in ("digest_volume_ml", "sample_mass_g"):
        if col not in samples:
            samples[col] = np.nan
        if samples.loc[convert, col].isna().any():
            raise AssayInputError(f"{what}: readings in mg/L or absorbance need {col}.")
    samples["dilution_factor"] = samples.get("dilution_factor", pd.Series(1.0, index=samples.index)).fillna(1.0)
    require_positive(samples, ["sample_mass_g", "digest_volume_ml", "dilution_factor"], what)
    for col in ("lod_mg_l", "lod_mg_kg"):
        if (samples[col].dropna() < 0).any():
            raise AssayInputError(f"{what}: {col} cannot be negative.")

    warns: list[str] = []
    curves: dict[str, Curve] = {}
    lods: dict[str, float] = {}
    for element, el_rows in rows.groupby("element", sort=False):
        el_samples = samples["element"] == element
        from_curve = el_samples & convert & samples["reading_mg_l"].isna()
        need_curve = from_curve.any()
        blanks = el_rows.loc[el_rows["kind"] == "blank", "absorbance"].dropna()
        blank_mean = float(blanks.mean()) if len(blanks) else 0.0
        if need_curve:
            if samples.loc[from_curve, "absorbance"].isna().any():
                raise AssayInputError(f"{what} {element}: provide absorbance, reading_mg_l, result_mg_kg or detection_status=nd.")
            std = el_rows[el_rows["kind"] == "standard"].copy()
            std["abs_corrected"] = std["absorbance"] - blank_mean
            curve = fit_curve(std, "std_conc_mg_l", "abs_corrected", f"{what} {element}")
            curves[element] = curve
            if curve.r2 < min_r2:
                warns.append(f"{what} {element}: calibration R² is {curve.r2:.4f} (below {min_r2}).")
            samples.loc[from_curve, "reading_mg_l"] = curve.concentration(samples.loc[from_curve, "absorbance"] - blank_mean)
            if len(blanks) >= 2:
                lods[element] = float(3 * blanks.std() / curve.slope)

    samples["digest_mg_l"] = samples["reading_mg_l"] * samples["dilution_factor"]
    factor = samples["dilution_factor"] * samples["digest_volume_ml"] / samples["sample_mass_g"]
    samples["mg_per_kg"] = samples["result_mg_kg"].combine_first(samples["reading_mg_l"] * factor)
    if samples.loc[~nd, "mg_per_kg"].isna().any():
        raise AssayInputError(f"{what}: each measured sample needs a numeric result.")
    instrument_lod = samples["lod_mg_l"].combine_first(samples["element"].map(lods))
    if (samples["lod_mg_l"].notna() & factor.isna() & samples["lod_mg_kg"].isna()).any():
        raise AssayInputError(f"{what}: LOD in mg/L needs mass and digest volume; use lod_mg_kg for final results.")
    samples["effective_lod_mg_kg"] = samples["lod_mg_kg"].combine_first(instrument_lod * factor)
    samples["lod_source"] = np.select(
        [samples["lod_mg_kg"].notna() | samples["lod_mg_l"].notna(), samples["element"].isin(lods)],
        ["supplied", "blank-derived"], default="unknown")
    # Detection is decided per sample from the mean of its replicate readings, so one noisy
    # replicate cannot turn an absent element into a reported value (or the reverse).
    keys = ["element", "sample_id"]
    mean_reading = samples.groupby(keys)["mg_per_kg"].transform("mean")
    lod = samples.groupby(keys)["effective_lod_mg_kg"].transform("mean")
    censored = nd.groupby([samples[k] for k in keys]).transform("any")
    mixed = censored & ~nd.groupby([samples[k] for k in keys]).transform("all")
    samples["detected"] = ~censored & (lod.isna() | (mean_reading > lod))
    for element in samples.loc[samples["effective_lod_mg_kg"].isna() & ~nd, "element"].unique():
        warns.append(f"{what} {element}: detection limit unknown; numeric readings are not evidence of a validated detection limit.")

    tables, comparisons = [], {}
    for element, sub in samples.groupby("element", sort=False):
        detected = sub[sub["detected"]]
        if detected.empty:
            t = pd.DataFrame({"sample_id": sub["sample_id"].unique()})
        else:
            t, comparison, sw = summarize(detected, "mg_per_kg", cv_limit=cv_limit, alpha=alpha, warn_single=False)
            comparisons[element] = comparison
            warns += [f"{what} {element} — {w}" for w in sw]
            t = pd.DataFrame({"sample_id": sub["sample_id"].unique()}).merge(t, on="sample_id", how="left")
        t.insert(0, "element", element)
        counts = sub.groupby("sample_id").size()
        t["n"] = t["sample_id"].map(counts)
        for col in ("mean", "sd", "sem", "cv_pct"):
            if col not in t:
                t[col] = np.nan
        if "letters" not in t:
            t["letters"] = ""
        t["result"] = [f"{m:.4g}" if pd.notna(m) else "ND" for m in t.get("mean", pd.Series([np.nan] * len(t)))]
        mixed_ids = samples.loc[mixed & samples["element"].eq(element), "sample_id"].unique()
        t.loc[t["sample_id"].isin(mixed_ids), "result"] = "Censored"
        for sid in mixed_ids:
            warns.append(f"{what} {element} {sid}: numeric and ND replicates are mixed; summary statistics omitted.")
        tables.append(t)
    summary = pd.concat(tables, ignore_index=True)

    return AssayResult(
        assay=what, unit="mg/kg", rows=samples, summary=summary, warnings=warns,
        extra={"curves": curves, "lods_mg_l": lods, "value_col": "mg_per_kg", "alpha": alpha,
               "comparisons": comparisons},
    )
