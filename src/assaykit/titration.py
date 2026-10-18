"""Titrimetric assays: oil quality (acid value, %FFA, peroxide value) and anti-nutrients
(phytate, oxalate).

Acid value (AOCS Cd 3d-63)
    Free fatty acids in ~5 g oil, dissolved in neutralised ethanol–diethyl ether (1:1), are
    titrated with 0.1 N KOH to a phenolphthalein end point.
        AV (mg KOH/g) = (V − B) × N × 56.1 / W
    B (solvent blank) is optional; the solvent is neutralised beforehand, so it is usually 0.

Free fatty acids (AOCS Ca 5a-40, from the acid value)
        %FFA (as oleic) = AV × 0.503        (0.503 = 28.2 / 56.1 = M_oleic / M_KOH / 10)
    FFA measures *hydrolytic* rancidity: lipases and moisture cutting fatty acids off triglycerides.

Peroxide value (AOCS Cd 8-53)
    Hydroperoxides in ~5 g oil oxidise iodide (sat. KI, acetic acid–chloroform 3:2) to iodine,
    titrated with 0.01 N sodium thiosulfate to a starch end point.
        PV (meq O2/kg) = (Vs − Vb) × N × 1000 / W
    PV measures *primary oxidation*. It rises early, then can fall as hydroperoxides break
    down, so a low PV alone does not prove an oil is fresh.

Phytate (Lucas & Markakas 1975)
    Acid extract titrated with standard FeCl3 (≈ 1.95 mg Fe/mL) to a persistent
    brownish-yellow end point with thiocyanate indicator.
        Phytic acid (%) = 8.24 × t × 100 / (1000 × W) × aliquot factor
    8.24 mg phytic acid per mL of titrant. The aliquot factor (filtrate volume / volume
    titrated) defaults to 1, matching the form of the equation used in the thesis.

Oxalate (Day & Underwood 1986)
    Acid extract titrated hot with 0.1 N KMnO4 to a faint persistent pink.
        Oxalate (mg/g) = t × 0.9004

Reference limits are from Codex Alimentarius CXS 210-1999 (named vegetable oils) and are
indicative. Crude, unrefined oils are not expected to meet the refined-oil limits.
"""

from __future__ import annotations

import pandas as pd

from assaykit.common import AssayInputError, AssayResult, prepare
from assaykit.stats import summarize

KOH_MW = 56.1
FFA_FROM_AV = {"oleic": 0.503, "palmitic": 0.457, "lauric": 0.357, "linoleic": 0.500}

PV_LIMITS = {"Refined (Codex)": 10.0, "Cold-pressed / virgin (Codex)": 15.0}
AV_LIMITS = {"Refined (Codex)": 0.6, "Cold-pressed / virgin (Codex)": 4.0}


def _titration_rows(df: pd.DataFrame, what: str, normality: float | None, need_normality: bool = True) -> pd.DataFrame:
    rows = prepare(df, what, required=["sample_id", "sample_mass_g", "titre_ml"],
                   numeric=["sample_mass_g", "titre_ml"], optional_numeric=["blank_titre_ml", "normality"])
    if need_normality:
        if "normality" not in rows.columns:
            rows["normality"] = float("nan")
        if rows["normality"].isna().any():
            if normality is None:
                raise AssayInputError(f"{what}: titrant normality is missing. Add a 'normality' column "
                                      "or set it in the options.")
            rows["normality"] = rows["normality"].fillna(normality)
        if (rows["normality"] <= 0).any():
            raise AssayInputError(f"{what}: normality must be greater than 0.")
    if "blank_titre_ml" not in rows.columns:
        rows["blank_titre_ml"] = 0.0
    rows["blank_titre_ml"] = rows["blank_titre_ml"].fillna(0.0)
    if (rows["sample_mass_g"] <= 0).any():
        raise AssayInputError(f"{what}: sample_mass_g must be greater than 0.")
    rows["net_titre_ml"] = rows["titre_ml"] - rows["blank_titre_ml"]
    return rows


def _negative_warning(rows: pd.DataFrame, what: str) -> list[str]:
    neg = rows[rows["net_titre_ml"] < 0]
    if neg.empty:
        return []
    ids = ", ".join(f"{r.sample_id} rep {r.replicate}" for r in neg.itertuples())
    return [f"{what}: sample titre is smaller than the blank for {ids}, so the result is negative. Check the blank."]


def _finish(rows, what, unit, value_col, cv_limit, alpha, higher_is_better, extra, warns) -> AssayResult:
    summary, _, stat_warns = summarize(rows, value_col, cv_limit=cv_limit, alpha=alpha,
                                       higher_is_better=higher_is_better)
    return AssayResult(assay=what, unit=unit, rows=rows, summary=summary,
                       warnings=warns + [f"{what} — {w}" for w in stat_warns],
                       extra={"value_col": value_col, **extra})


def analyze_acid_value(
    df: pd.DataFrame,
    normality: float | None = 0.1,
    fatty_acid: str = "oleic",
    cv_limit: float = 10.0,
    alpha: float = 0.05,
) -> AssayResult:
    """Acid value and %FFA from the same titration. The summary is for acid value;
    %FFA is added alongside it (it is the same measurement × 0.503)."""
    if fatty_acid not in FFA_FROM_AV:
        raise AssayInputError(f"Acid value: fatty_acid must be one of {', '.join(FFA_FROM_AV)}.")
    what = "Acid value"
    rows = _titration_rows(df, what, normality)
    rows["acid_value_mg_koh_g"] = rows["net_titre_ml"] * rows["normality"] * KOH_MW / rows["sample_mass_g"]
    rows["ffa_pct"] = rows["acid_value_mg_koh_g"] * FFA_FROM_AV[fatty_acid]
    res = _finish(rows, what, "mg KOH/g", "acid_value_mg_koh_g", cv_limit, alpha, False,
                  {"limits": AV_LIMITS, "fatty_acid": fatty_acid}, _negative_warning(rows, what))
    ffa = summarize(rows, "ffa_pct", cv_limit=cv_limit, alpha=alpha, higher_is_better=False)[0]
    res.summary = res.summary.merge(
        ffa[["sample_id", "mean", "sd", "sem"]].rename(columns=lambda c: c if c == "sample_id" else f"ffa_{c}"),
        on="sample_id")
    for r in res.summary.itertuples():
        if r.mean > AV_LIMITS["Cold-pressed / virgin (Codex)"]:
            res.warnings.append(f"Acid value {r.sample_id}: {r.mean:.2f} mg KOH/g is above the Codex limit for "
                                f"cold-pressed oils (4.0), equal to {r.ffa_mean:.2f} % FFA as {fatty_acid}.")
    return res


def analyze_peroxide(
    df: pd.DataFrame, normality: float | None = 0.01, cv_limit: float = 10.0, alpha: float = 0.05
) -> AssayResult:
    what = "Peroxide value"
    rows = _titration_rows(df, what, normality)
    rows["pv_meq_kg"] = rows["net_titre_ml"] * rows["normality"] * 1000 / rows["sample_mass_g"]
    res = _finish(rows, what, "meq O2/kg", "pv_meq_kg", cv_limit, alpha, False, {"limits": PV_LIMITS},
                  _negative_warning(rows, what))
    for r in res.summary.itertuples():
        if r.mean > PV_LIMITS["Cold-pressed / virgin (Codex)"]:
            res.warnings.append(f"Peroxide value {r.sample_id}: {r.mean:.2f} meq O2/kg is above the Codex limit "
                                "for cold-pressed oils (15), which indicates advanced primary oxidation.")
    return res


def analyze_phytate(
    df: pd.DataFrame, mg_per_ml: float = 8.24, aliquot_factor: float = 1.0, cv_limit: float = 10.0, alpha: float = 0.05
) -> AssayResult:
    what = "Phytate"
    rows = _titration_rows(df, what, None, need_normality=False)
    rows["phytate_pct"] = mg_per_ml * rows["net_titre_ml"] * 100 / (1000 * rows["sample_mass_g"]) * aliquot_factor
    return _finish(rows, what, "% phytic acid", "phytate_pct", cv_limit, alpha, False,
                   {"aliquot_factor": aliquot_factor}, _negative_warning(rows, what))


def analyze_oxalate(
    df: pd.DataFrame, mg_per_ml: float = 0.9004, cv_limit: float = 10.0, alpha: float = 0.05
) -> AssayResult:
    """Oxalate (mg/g) = t × 0.9004, for the 1 g sample of the method. If another mass
    was used the result is scaled to per gram: t × 0.9004 / W."""
    what = "Oxalate"
    rows = _titration_rows(df, what, None, need_normality=False)
    rows["oxalate_mg_g"] = rows["net_titre_ml"] * mg_per_ml / rows["sample_mass_g"]
    return _finish(rows, what, "mg/g", "oxalate_mg_g", cv_limit, alpha, False, {}, _negative_warning(rows, what))
