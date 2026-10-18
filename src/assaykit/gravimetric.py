"""Gravimetric assays: the analyte is isolated, dried and weighed.

Alkaloids (Harborne 1973)
    Extracted in 20 % acetic acid in ethanol, concentrated, precipitated with NH4OH,
    washed, dried, weighed.
Saponins (Obadoni & Ochuko 2001)
    Extracted in 20 % aqueous ethanol, defatted with diethyl ether, partitioned into
    n-butanol, washed with 5 % NaCl, evaporated in a pre-weighed crucible.

        Content (%) = residue mass / sample mass × 100      (× 10 for g/kg)

Weigh the empty container and the container + residue; the tool does the subtraction,
so the arithmetic of a tare never goes wrong.
"""

from __future__ import annotations

import pandas as pd

from assaykit.common import AssayInputError, AssayResult, prepare
from assaykit.stats import summarize

ANALYTES = {"alkaloids": "Alkaloids", "saponins": "Saponins"}
UNITS = {"%": 100.0, "g/kg": 1000.0, "mg/g": 1000.0}


def analyze_gravimetric(
    df: pd.DataFrame, analyte: str = "alkaloids", unit: str = "%", cv_limit: float = 10.0, alpha: float = 0.05
) -> AssayResult:
    what = ANALYTES.get(analyte, analyte)
    if unit not in UNITS:
        raise AssayInputError(f"{what}: unit must be one of {', '.join(UNITS)}.")
    rows = prepare(df, what, required=["sample_id", "sample_mass_g"], numeric=["sample_mass_g"],
                   optional_numeric=["residue_g", "container_g", "container_residue_g"])
    if "residue_g" not in rows.columns or rows["residue_g"].isna().any():
        if not {"container_g", "container_residue_g"} <= set(rows.columns):
            raise AssayInputError(f"{what}: give residue_g, or container_g and container_residue_g.")
        rows["residue_g"] = rows.get("residue_g", pd.Series(index=rows.index, dtype=float)).fillna(
            rows["container_residue_g"] - rows["container_g"])
    if (rows["sample_mass_g"] <= 0).any():
        raise AssayInputError(f"{what}: sample_mass_g must be greater than 0.")
    warns = []
    if (rows["residue_g"] < 0).any():
        warns.append(f"{what}: a residue mass is negative. The container weighed more empty than with residue.")
    if (rows["residue_g"] > rows["sample_mass_g"]).any():
        warns.append(f"{what}: a residue is heavier than the sample it came from. Check the masses.")

    rows["content"] = rows["residue_g"] / rows["sample_mass_g"] * UNITS[unit]
    summary, comparison, stat_warns = summarize(rows, "content", cv_limit=cv_limit, alpha=alpha)
    return AssayResult(assay=what, unit=unit, rows=rows, summary=summary,
                       warnings=warns + [f"{what} — {w}" for w in stat_warns], extra={"value_col": "content", "alpha": alpha, "comparisons": {"samples": comparison}})
