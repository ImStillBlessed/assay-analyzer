"""Import already-calculated observations without inventing bench measurements."""

import numpy as np
import pandas as pd

from assaykit.assays import ASSAYS
from assaykit.common import AssayInputError, AssayResult, prepare
from assaykit.dpph import analyze_dpph_inhibition
from assaykit.stats import summarize


def analyze_result_table(df: pd.DataFrame, combine_repeats: bool = False,
                         cv_limit: float = 10.0, alpha: float = 0.05, method: str = "logistic") -> list[AssayResult]:
    """One row per calculated observation; doses never become replicates.

    Required: assay, sample_id, value, unit. Optional group_id labels a material
    whose distinct observations may be combined only after user confirmation.
    ND requires status=nd and no invented value. Numeric zero stays numeric zero.
    Supplied source means/SEM are not supported as if they were replicate values.
    """
    rows = prepare(df, "Calculated results", required=["assay", "sample_id", "value", "unit"], numeric=[],
                   optional_numeric=["value", "concentration"])
    for col in ("assay", "unit"):
        if rows[col].isna().any() or rows[col].astype(str).str.strip().eq("").any():
            raise AssayInputError(f"Calculated results: every observation needs {col}.")
        rows[col] = rows[col].astype(str).str.strip()
    rows["status"] = rows.get("status", pd.Series("measured", index=rows.index)).fillna("measured").str.lower().str.strip()
    if not rows["status"].isin(["measured", "nd"]).all():
        raise AssayInputError("Calculated results: status must be measured or nd.")
    if (rows["status"].eq("measured") & rows["value"].isna()).any():
        raise AssayInputError("Calculated results: numeric value required, or use status=nd for a non-detect.")
    if (rows["status"].eq("nd") & rows["value"].notna()).any():
        raise AssayInputError("Calculated results: leave value blank for status=nd; do not substitute zero.")
    rows["source_sample_id"] = rows["sample_id"]
    if combine_repeats:
        if "group_id" not in rows:
            raise AssayInputError("No group_id column is present. Keep samples separate or add confirmed repeat groups.")
        group = rows["group_id"].fillna("").astype(str).str.strip()
        rows.loc[group.ne(""), "sample_id"] = group[group.ne("")]
    if "concentration" not in rows:
        rows["concentration"] = np.nan
    if (rows["concentration"].dropna() < 0).any():
        raise AssayInputError("Calculated results: concentrations cannot be negative.")
    if "element" not in rows:
        rows["element"] = ""
    rows["element"] = rows["element"].fillna("").astype(str).str.strip()
    if (rows["assay"].eq("minerals") & rows["element"].eq("")).any():
        raise AssayInputError("Mineral results need an element symbol on every row.")
    if "concentration_unit" not in rows:
        rows["concentration_unit"] = ""
    rows["concentration_unit"] = rows["concentration_unit"].fillna("").astype(str).str.strip()
    if (rows["concentration"].notna() & rows["concentration_unit"].eq("")).any():
        raise AssayInputError("Every supplied concentration needs concentration_unit; for example µg/mL.")
    results = []
    for (assay, unit, conc_unit), sub in rows.groupby(["assay", "unit", "concentration_unit"], sort=False):
        warns = ["Imported calculated observations: the original calibration, absorbance, masses and titres were not supplied."]
        if assay == "dpph" and unit == "% inhibition" and sub["status"].eq("measured").all():
            data = sub.rename(columns={"value": "inhibition_pct"}).copy()
            # A supplied replicate identifies a series; doses alone never count as repeats.
            if "replicate" not in df.columns:
                data["replicate"] = data["source_sample_id"]
            res = analyze_dpph_inhibition(data, conc_unit=conc_unit or "µg/mL", method=method,
                                           cv_limit=cv_limit, alpha=alpha)
        else:
            title = ASSAYS[assay].title if assay in ASSAYS else "Free fatty acids" if assay == "ffa" else assay
            if assay == "acid_value":
                title = "Acid value"
            elif assay == "minerals":
                title = "Minerals"
            tables, comparisons = [], {}
            for (element, concentration), part in sub.groupby(["element", "concentration"], sort=False, dropna=False):
                measured = part[part["status"].eq("measured")]
                censored = set(part.loc[part["status"].eq("nd"), "sample_id"])
                usable = measured[~measured["sample_id"].isin(censored)]
                if usable.empty:
                    table = pd.DataFrame(columns=["sample_id", "n", "mean", "sd", "sem", "cv_pct", "letters"])
                else:
                    table, comparison, sw = summarize(usable, "value", cv_limit=cv_limit, alpha=alpha, warn_single=False)
                    comparisons[f"{element} / {concentration}"] = comparison
                    warns.extend(sw)
                table = pd.DataFrame({"sample_id": part["sample_id"].unique()}).merge(table, how="left", on="sample_id")
                table["n"] = table["sample_id"].map(part.groupby("sample_id").size())
                table["result"] = ["Censored" if name in censored and name in set(measured["sample_id"]) else "ND" if name in censored else "numeric" for name in table["sample_id"]]
                table["element"], table["concentration"] = element, concentration
                tables.append(table)
            if assay == "frap" and "%" in unit:
                warns.append("FRAP is retained as the source's reported percentage. Its normalization formula is unknown; no conversion to mg AAE/g was made.")
            if assay == "minerals" and sub["value"].eq(0).any():
                warns.append("Mineral zeros are retained as numeric zeros. This source does not establish whether they mean non-detects; no LOD is inferred.")
            res = AssayResult(title + " (reported)", unit, sub.copy(), pd.concat(tables, ignore_index=True), warns,
                              {"reported": True, "value_col": "value", "conc_unit": conc_unit,
                               "comparisons": comparisons, "alpha": alpha})
        res.extra.update(input_basis="calculated_results", assay_key=assay,
                         combine_repeats=combine_repeats, options={"alpha": alpha, "cv_limit": cv_limit,
                         "combine_repeats": combine_repeats, "method": method})
        results.append(res)
    return results
