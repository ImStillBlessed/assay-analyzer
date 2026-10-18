"""Replicate statistics and between-sample comparison.

Thesis tables report mean ± SEM (or SD) with superscript letters, where samples
sharing a letter are not significantly different (one-way ANOVA followed by
Tukey's HSD). `summarize` produces exactly that table.

Letters compare *samples measured by the same assay*. Comparing different assays
(say acid value against peroxide value) is not meaningful: they have different units.
"""

from __future__ import annotations

import string
import warnings
from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import stats
from assaykit.common import AssayInputError


@dataclass
class Comparison:
    f_stat: float
    p_value: float
    groups: list[str]
    tukey_p: np.ndarray
    letters: dict[str, str]


def summarize(
    df: pd.DataFrame,
    value_col: str,
    group_col: str = "sample_id",
    cv_limit: float = 10.0,
    alpha: float = 0.05,
    higher_is_better: bool = True,
    warn_single: bool = True,
) -> tuple[pd.DataFrame, Comparison | None, list[str]]:
    """Mean, SD, SEM, CV per sample plus Tukey letters ('a' = best). Returns (table, comparison, warnings)."""
    warns: list[str] = []
    if not 0 < alpha < 1:
        raise AssayInputError("Significance level alpha must be between 0 and 1.")
    if not np.isfinite(cv_limit) or cv_limit <= 0:
        raise AssayInputError("Replicate CV limit must be positive and finite.")
    g = df.groupby(group_col, sort=False)[value_col]
    table = g.agg(n="count", mean="mean", sd="std").reset_index()
    table["sem"] = table["sd"] / np.sqrt(table["n"])
    with np.errstate(divide="ignore", invalid="ignore"):
        table["cv_pct"] = np.where(table["mean"] != 0, table["sd"] / table["mean"].abs() * 100, np.nan)

    for _, row in table.iterrows():
        if row["n"] < 2:
            if warn_single:
                warns.append(f"{row[group_col]}: only 1 replicate, so SD and statistics are unavailable.")
        elif row["cv_pct"] > cv_limit:
            worst = _most_deviant(df[df[group_col] == row[group_col]], value_col)
            warns.append(
                f"{row[group_col]}: replicate CV is {row['cv_pct']:.1f}% (limit {cv_limit:g}%). "
                f"Replicate {worst} deviates most from the mean; check it against your notebook."
            )

    comparison = compare_groups(df, value_col, group_col, alpha, higher_is_better)
    table["letters"] = table[group_col].map(comparison.letters) if comparison else ""
    table["letters"] = table["letters"].fillna("")
    return table, comparison, warns


def _most_deviant(sub: pd.DataFrame, value_col: str):
    dev = (sub[value_col] - sub[value_col].mean()).abs()
    return sub.loc[dev.idxmax(), "replicate"] if "replicate" in sub.columns else dev.idxmax()


def compare_groups(
    df: pd.DataFrame,
    value_col: str,
    group_col: str = "sample_id",
    alpha: float = 0.05,
    higher_is_better: bool = True,
) -> Comparison | None:
    """One-way ANOVA + Tukey HSD over samples with at least 2 replicates."""
    groups = [
        (str(name), sub[value_col].dropna().to_numpy(dtype=float))
        for name, sub in df.groupby(group_col, sort=False)
    ]
    groups = [(n, v) for n, v in groups if len(v) >= 2]
    if len(groups) < 2:
        return None
    names = [n for n, _ in groups]
    values = [v for _, v in groups]
    if all(np.ptp(v) == 0 for v in values):
        # No within-group variance at all: ANOVA is undefined.
        return None

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        f_stat, p_value = stats.f_oneway(*values)
        tukey = stats.tukey_hsd(*values)
    sign = 1.0 if higher_is_better else -1.0
    means = [sign * float(v.mean()) for v in values]
    letters = compact_letter_display(names, means, tukey.pvalue, alpha)
    return Comparison(float(f_stat), float(p_value), names, tukey.pvalue, letters)


def compact_letter_display(
    names: list[str], means: list[float], pvalues: np.ndarray, alpha: float = 0.05
) -> dict[str, str]:
    """Assign letters so that samples sharing a letter are not significantly
    different. 'a' goes to the highest of `means`.

    Insert-and-absorb algorithm (Piepho 2004, J. Comput. Graph. Stat. 13:456).
    """
    n = len(names)
    columns: list[set[int]] = [set(range(n))]
    for i in range(n):
        for j in range(i + 1, n):
            if not pvalues[i][j] < alpha:
                continue
            split: list[set[int]] = []
            for col in columns:
                if i in col and j in col:
                    split += [col - {i}, col - {j}]
                else:
                    split.append(col)
            unique: list[set[int]] = []
            for col in split:
                if col and col not in unique:
                    unique.append(col)
            columns = [c for c in unique if not any(c < other for other in unique)]

    rank = {idx: r for r, idx in enumerate(sorted(range(n), key=lambda k: -means[k]))}
    columns.sort(key=lambda c: min(rank[k] for k in c))
    letters = {k: "" for k in range(n)}
    alphabet = string.ascii_lowercase + string.ascii_uppercase
    for pos, col in enumerate(columns):
        for k in col:
            letters[k] += alphabet[pos]
    return {names[k]: letters[k] for k in range(n)}
