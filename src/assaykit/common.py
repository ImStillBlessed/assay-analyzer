"""Shared data structures and input validation.

Every assay takes a "long" table: one row per measurement (one cuvette reading or
one titration), with a `sample_id` and an optional `replicate` column. This is the
shape you get when you copy a lab notebook line by line, so it is also the shape
the templates use.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd


class AssayInputError(ValueError):
    """Raised when an input table cannot be analysed. Messages are written for
    the person at the bench, not for a programmer."""


@dataclass
class AssayResult:
    assay: str
    unit: str
    rows: pd.DataFrame
    """One row per measurement, with the computed value added."""
    summary: pd.DataFrame
    """One row per sample: n, mean, SD, CV and significance letters."""
    warnings: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)
    """Assay-specific outputs (fits, standard curves, reference limits)."""


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Lower-case and snake_case headers so 'Sample ID' and 'sample_id' both work."""
    out = df.copy()
    out.columns = [
        str(c).strip().lower().replace(" ", "_").replace("-", "_").replace("(", "").replace(")", "")
        for c in out.columns
    ]
    # Drop rows that are entirely empty (common in hand-made spreadsheets).
    out = out.dropna(how="all").reset_index(drop=True)
    return out


def prepare(
    df: pd.DataFrame,
    assay: str,
    required: list[str],
    numeric: list[str],
    optional_numeric: list[str] | None = None,
) -> pd.DataFrame:
    """Normalise headers, check required columns, coerce numbers, and fail with a
    message that names the exact spreadsheet row when something is wrong."""
    if df is None or len(df) == 0:
        raise AssayInputError(f"{assay}: the table is empty.")

    out = normalize_columns(df)

    missing = [c for c in required if c not in out.columns]
    if missing:
        raise AssayInputError(
            f"{assay}: missing column(s): {', '.join(missing)}. "
            f"Found: {', '.join(out.columns)}. Download the template to see the expected layout."
        )

    out["sample_id"] = out["sample_id"].astype(str).str.strip()
    if "replicate" not in out.columns:
        out["replicate"] = out.groupby("sample_id").cumcount() + 1

    for col in numeric + [c for c in (optional_numeric or []) if c in out.columns]:
        converted = pd.to_numeric(out[col], errors="coerce")
        bad = out[col].notna() & converted.isna()
        if bad.any():
            rows = _sheet_rows(out.index[bad])
            examples = ", ".join(repr(v) for v in out.loc[bad, col].head(3))
            raise AssayInputError(
                f"{assay}: column '{col}' has non-numeric values on spreadsheet row(s) {rows} "
                f"(e.g. {examples})."
            )
        out[col] = converted

    for col in numeric:
        empty = out[col].isna()
        if empty.any():
            raise AssayInputError(
                f"{assay}: column '{col}' is empty on spreadsheet row(s) {_sheet_rows(out.index[empty])}."
            )
    return out


def _sheet_rows(index: pd.Index) -> str:
    # +2: one for the header row, one because spreadsheets count from 1.
    rows = [int(i) + 2 for i in index]
    shown = ", ".join(str(r) for r in rows[:10])
    return shown + (" …" if len(rows) > 10 else "")
