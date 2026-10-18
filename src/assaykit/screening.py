"""Qualitative observations, kept separate from numeric assay statistics."""

import pandas as pd

from assaykit.common import AssayInputError, AssayResult, prepare


def analyze_screening(df: pd.DataFrame) -> AssayResult:
    rows = prepare(df, "Qualitative screening", required=["sample_id", "test", "status"], numeric=[])
    for col in ("test", "status"):
        if rows[col].isna().any() or rows[col].astype(str).str.strip().eq("").any():
            raise AssayInputError(f"Qualitative screening: every observation needs {col}.")
    rows["status"] = rows["status"].astype(str).str.lower().str.strip()
    if not rows["status"].isin(["present", "absent", "indeterminate"]).all():
        raise AssayInputError("Qualitative screening: status must be present, absent or indeterminate.")
    return AssayResult("Qualitative screening", "observation", rows, rows.copy())
