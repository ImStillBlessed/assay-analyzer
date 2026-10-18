"""Write results to an Excel workbook and PNG figures."""

from __future__ import annotations

import io
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from assaykit.assays import ASSAYS
from assaykit.common import AssayResult
from assaykit.plots import figures_for

SUPERSCRIPT = str.maketrans("abcdefghijklmnopqrstuvwxyz", "ᵃᵇᶜᵈᵉᶠᵍʰⁱʲᵏˡᵐⁿᵒᵖqʳˢᵗᵘᵛʷˣʸᶻ")  # no superscript q exists


def _fmt(mean, spread, letters="") -> str:
    if pd.isna(mean):
        return "—"
    text = f"{mean:.4g}" if pd.isna(spread) else f"{mean:.4g} ± {spread:.2g}"
    return text + (letters.translate(SUPERSCRIPT) if isinstance(letters, str) else "")


def overview(results: list[AssayResult], err: str = "sem") -> pd.DataFrame:
    """One line per sample per measurement, formatted like a thesis table: 82.35 ± 0.40ᵃ."""
    lines = []

    def add(assay, sample, table_row, unit, mean="mean", spread=None, letters="letters"):
        r = table_row
        lines.append({"assay": assay, "sample": sample, "unit": unit, "n": r.get("n"),
                      "result": _fmt(r.get(mean), r.get(spread or err), r.get(letters, ""))})

    for res in results:
        # Samples with a dilution series are summarised by IC50; their per-concentration
        # inhibition stays in the DPPH sheets.
        with_ic50 = set(res.extra["ic50"]["sample_id"]) if res.assay == "DPPH" and not res.extra["ic50"].empty else set()
        for _, r in res.summary.iterrows():
            if res.assay == "DPPH":
                if r["sample_id"] in with_ic50:
                    continue
                conc = r.get("concentration")
                sample = r["sample_id"] if pd.isna(conc) else f"{r['sample_id']} @ {conc:g} {res.extra['conc_unit']}"
                add("DPPH", sample, r, res.unit)
            elif res.assay == "Minerals (AAS)":
                lines.append({"assay": f"{r['element']}", "sample": r["sample_id"], "unit": "mg/kg", "n": r.get("n"),
                              "result": "ND" if r["result"] == "ND" else _fmt(r.get("mean"), r.get(err), r.get("letters", ""))})
            elif res.assay == "Acid value":
                add("Acid value", r["sample_id"], r, res.unit)
                add("% FFA", r["sample_id"], r, f"% (as {res.extra['fatty_acid']})", mean="ffa_mean",
                    spread=f"ffa_{err}")
            else:
                add(res.assay, r["sample_id"], r, res.unit)
        if res.assay == "DPPH" and not res.extra["ic50"].empty:
            for _, r in res.extra["ic50"].iterrows():
                add("DPPH IC50", r["sample_id"], r, res.extra["conc_unit"])
    table = pd.DataFrame(lines)
    if not table.empty:
        table["n"] = pd.to_numeric(table["n"], errors="coerce").astype("Int64")
    return table


def methods_table() -> pd.DataFrame:
    rows = [{"assay": a.title, "group": a.group, "method": a.method, "input columns": a.columns} for a in ASSAYS.values()]
    rows.append({"assay": "Statistics", "group": "", "method": "Mean ± SEM (or SD) of replicates; one-way ANOVA then "
                 "Tukey HSD between samples of the same assay; samples sharing a letter do not differ at the chosen α.",
                 "input columns": ""})
    return pd.DataFrame(rows)


def to_excel(results: list[AssayResult], err: str = "sem") -> bytes:
    buf = io.BytesIO()
    used: set[str] = set()

    def sheet(name: str) -> str:
        name = name.replace("/", "-")[:31]
        while name in used:
            name = name[:29] + str(len(used))
        used.add(name)
        return name

    with pd.ExcelWriter(buf, engine="openpyxl") as xl:
        overview(results, err).to_excel(xl, sheet_name=sheet("Overview"), index=False)
        for res in results:
            short = res.assay.replace("Minerals (AAS)", "Minerals").replace("Peroxide value", "PV")
            res.summary.round(4).to_excel(xl, sheet_name=sheet(f"{short} summary"), index=False)
            res.rows.round(4).to_excel(xl, sheet_name=sheet(f"{short} calc"), index=False)
            if res.assay == "DPPH" and not res.extra["ic50"].empty:
                res.extra["ic50"].round(4).to_excel(xl, sheet_name=sheet("DPPH IC50"), index=False)
                res.extra["method_comparison"].round(3).to_excel(xl, sheet_name=sheet("DPPH IC50 methods"), index=False)
        warnings = [{"assay": r.assay, "warning": w} for r in results for w in r.warnings]
        pd.DataFrame(warnings or [{"assay": "", "warning": "No warnings."}]).to_excel(
            xl, sheet_name=sheet("Warnings"), index=False)
        methods_table().to_excel(xl, sheet_name=sheet("Methods"), index=False)
        for ws in xl.book.worksheets:
            for col in ws.columns:
                width = max(len(str(c.value)) if c.value is not None else 0 for c in col)
                ws.column_dimensions[col[0].column_letter].width = min(max(10, width + 2), 70)
    return buf.getvalue()


def write_report(results: list[AssayResult], out_dir: Path, err: str = "sem") -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written = [out_dir / "assay_report.xlsx"]
    written[0].write_bytes(to_excel(results, err))
    for res in results:
        for name, fig in figures_for(res, err).items():
            path = out_dir / f"{name}.png"
            fig.savefig(path, dpi=200)
            plt.close(fig)
            written.append(path)
    return written
