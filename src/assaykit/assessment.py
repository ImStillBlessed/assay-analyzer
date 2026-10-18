"""Descriptive reference/target checks; distinct from statistical significance."""

import numpy as np
import pandas as pd

from assaykit.common import AssayInputError, AssayResult


def assess_results(result: AssayResult, config: dict) -> pd.DataFrame:
    """Compare sample means within the same measurement, element and dose.

    A configured unit is mandatory for numeric targets. No default biological or
    regulatory cutoffs are inferred. Missing/censored values cannot meet a target.
    """
    mode = config.get("mode", "Off")
    if mode == "Off" or result.unit == "observation":
        return pd.DataFrame()
    table, unit = result.summary.copy(), result.unit
    if config.get("measurement") == "IC50":
        table = result.extra.get("ic50", pd.DataFrame()).copy()
        unit = result.extra.get("conc_unit", "")
        if table.empty:
            raise AssayInputError("IC50 comparison needs a concentration series. Choose Result to compare single-dose inhibition.")
    elif config.get("measurement") == "FFA":
        if "ffa_mean" not in table:
            raise AssayInputError("FFA comparison is available only for acid-value results.")
        table["mean"] = table["ffa_mean"]
        unit = f"% (as {result.extra['fatty_acid']})"
    if table.empty:
        return pd.DataFrame()
    if mode not in ("Reference sample", "Target range"):
        raise AssayInputError("Choose Reference sample, Target range or Off.")
    if mode == "Target range":
        if config.get("unit") != unit:
            raise AssayInputError(f"Comparison unit must match the calculated unit exactly: {unit}.")
        lo, hi = config.get("lower"), config.get("upper")
        if lo is None or hi is None or not np.isfinite([lo, hi]).all() or lo > hi:
            raise AssayInputError("The target range needs finite lower and upper values, with lower ≤ upper.")
        if "element" in table:
            element = config.get("element", "").strip()
            if not element:
                raise AssayInputError("Choose an element symbol before setting a mineral target range.")
            table = table[table["element"].eq(element)]
            if table.empty:
                raise AssayInputError(f"No results were found for element '{element}'. Check the symbol in Settings.")
    reference = config.get("reference", "").strip()
    if mode == "Reference sample" and not reference:
        raise AssayInputError("Enter the sample name of the measured reference in Settings.")
    checks = []
    for _, row in table.iterrows():
        value = row.get("mean", np.nan)
        flag, target, action = "Needs review", "", "No numeric result is available; inspect the measurement or detection status."
        if mode == "Target range":
            target = f"{lo:g} to {hi:g} {unit}"
            if pd.notna(value) and np.isfinite(value):
                flag = "Below target" if value < lo else "Above target" if value > hi else "Within target"
                action = "Within your configured range." if flag == "Within target" else "Check the readings and method, then review against the source of your target range."
        else:
            matches = table[table["sample_id"].eq(reference)]
            for key in ("element", "concentration"):
                if key in table:
                    matches = matches[matches[key].isna()] if pd.isna(row[key]) else matches[matches[key].eq(row[key])]
            if row["sample_id"] == reference and pd.notna(value) and np.isfinite(value):
                flag, action = "Reference", "This is the measured comparison reference."
            elif len(matches) != 1 or pd.isna(matches.iloc[0].get("mean")) or not np.isfinite(matches.iloc[0]["mean"]):
                flag, action = "No matching reference", "Add a numeric reference measured for the same element/dose and protocol."
            elif pd.notna(value) and np.isfinite(value):
                benchmark = matches.iloc[0]["mean"]
                target = f"{reference}: {benchmark:g} {unit}"
                lower = config.get("direction") == "Lower is the target"
                meets = value <= benchmark if lower else value >= benchmark
                flag = "Meets reference" if meets else "Above reference" if lower else "Below reference"
                action = "Descriptive comparison of means; this is not a test of statistical significance."
        checks.append({"Sample": row["sample_id"], "Element": row.get("element", ""),
                       "Concentration": row.get("concentration", np.nan), "Mean": value, "Unit": unit,
                       "Flag": flag, "Compared with": target, "What to do": action,
                       "Benchmark source": config.get("source", "")})
    return pd.DataFrame(checks)
