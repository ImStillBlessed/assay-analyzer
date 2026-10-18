"""Command line:  assaykit <folder> [--out report/]

The folder is scanned for files named after the assays (tpc.csv, dpph.xlsx, peroxide.csv, ...);
whichever exist are analysed. `assaykit --list` shows every supported assay.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from assaykit.assays import ASSAYS
from assaykit.common import AssayInputError
from assaykit.report import overview, write_report


def read_table(path: Path) -> pd.DataFrame:
    return pd.read_excel(path) if path.suffix.lower() in (".xlsx", ".xls") else pd.read_csv(path)


def find_inputs(folder: Path) -> dict[str, Path]:
    found = {}
    for key in ASSAYS:
        for ext in (".csv", ".xlsx", ".xls"):
            if (folder / f"{key}{ext}").exists():
                found[key] = folder / f"{key}{ext}"
                break
    return found


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="assaykit", description="Analyse phytochemical, antioxidant, anti-nutrient, "
                                "oil-quality and mineral assay data.")
    p.add_argument("folder", type=Path, nargs="?", help="folder with <assay>.csv / .xlsx files")
    p.add_argument("--out", type=Path, default=Path("report"), help="output folder (default: report/)")
    p.add_argument("--error", choices=["sem", "sd"], default="sem", help="error shown as ± (default: sem)")
    p.add_argument("--alpha", type=float, default=0.05, help="significance level (default: 0.05)")
    p.add_argument("--cv-limit", type=float, default=10.0, help="flag replicate CV above this %% (default: 10)")
    p.add_argument("--ic50-method", choices=["logistic", "interpolation", "linear"], default="logistic")
    p.add_argument("--conc-unit", default="µg/mL", help="DPPH concentration unit (default µg/mL)")
    p.add_argument("--list", action="store_true", help="list supported assays and their input columns")
    args = p.parse_args(argv)

    if args.list or args.folder is None:
        for a in ASSAYS.values():
            print(f"{a.key + '.csv':<18} {a.title}  [{a.group}]\n{'':<18} {a.method}\n{'':<18} columns: {a.columns}\n")
        return 0

    inputs = find_inputs(args.folder)
    if not inputs:
        print(f"No assay files found in {args.folder}. Expected names: {', '.join(k + '.csv' for k in ASSAYS)}",
              file=sys.stderr)
        return 1

    options = {"alpha": args.alpha, "cv_limit": args.cv_limit, "method": args.ic50_method, "conc_unit": args.conc_unit}
    results = []
    for key, path in inputs.items():
        try:
            results.append(ASSAYS[key].run(read_table(path), **options))
        except AssayInputError as e:
            print(f"[{path.name}] {e}", file=sys.stderr)
            return 2

    print(overview(results, args.error).to_string(index=False))
    warnings = [w for res in results for w in res.warnings]
    if warnings:
        print("\nWarnings:")
        for w in warnings:
            print(f"  ! {w}")
    files = write_report(results, args.out, args.error)
    print(f"\nWrote {len(files)} files to {args.out}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
