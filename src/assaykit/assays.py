"""Shared, extensible catalogue of laboratory assays.

The CLI and the app both read from here: an input file named `<key>.csv` (or .xlsx)
is analysed by the matching entry.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from functools import partial
from typing import Callable

import pandas as pd

from assaykit.calibration import CurveAssay, analyze_curve_assay, analyze_minerals
from assaykit.common import AssayResult
from assaykit.dpph import analyze_dpph
from assaykit.screening import analyze_screening
from assaykit.gravimetric import analyze_gravimetric
from assaykit.titration import analyze_acid_value, analyze_oxalate, analyze_peroxide, analyze_phytate


@dataclass(frozen=True)
class AssayInfo:
    key: str
    title: str
    group: str
    method: str
    columns: str
    analyze: Callable[..., AssayResult]

    def run(self, df: pd.DataFrame, **options) -> AssayResult:
        """Call the analysis, passing only the options it accepts."""
        target = self.analyze.func if isinstance(self.analyze, partial) else self.analyze
        accepted = inspect.signature(target).parameters
        selected = {k: v for k, v in options.items() if k in accepted and v is not None}
        result = self.analyze(df, **selected)
        result.extra["assay_key"] = self.key
        defaults = {name: param.default for name, param in inspect.signature(self.analyze).parameters.items()
                    if param.default is not inspect.Parameter.empty}
        result.extra["options"] = {**defaults, **selected}
        return result


CURVE_COLUMNS = ("kind (standard / sample / blank), sample_id, replicate, absorbance, std_conc; for per-gram "
                 "results also sample_mass_g + extract_volume_ml (or extract_mg_per_ml); optional dilution_factor, abs_blank")
TITRE_COLUMNS = "sample_id, replicate, sample_mass_g, titre_ml, blank_titre_ml (optional)"

ASSAYS: dict[str, AssayInfo] = {
    a.key: a
    for a in [
        AssayInfo("screening", "Qualitative screening", "Qualitative screening",
                  "Recorded presence, absence or indeterminate observations; no inferential statistics",
                  "sample_id, test, status (present / absent / indeterminate); optional observation, replicate",
                  analyze_screening),
        AssayInfo("tpc", "Total phenolics", "Phytochemicals",
                  "Folin–Ciocalteu, 765 nm, tannic acid standard → mg TAE/g", CURVE_COLUMNS,
                  partial(analyze_curve_assay, assay="tpc")),
        AssayInfo("flavonoids", "Total flavonoids", "Phytochemicals",
                  "Aluminium chloride, 415 nm, quercetin standard → mg QE/g", CURVE_COLUMNS,
                  partial(analyze_curve_assay, assay="flavonoids")),
        AssayInfo("tannins", "Total tannins", "Phytochemicals",
                  "Folin–Denis, 760 nm, tannic acid standard → mg TAE/g", CURVE_COLUMNS,
                  partial(analyze_curve_assay, assay="tannins")),
        AssayInfo("alkaloids", "Alkaloids", "Phytochemicals",
                  "Gravimetric: NH4OH precipitate, dried and weighed → %",
                  "sample_id, replicate, sample_mass_g, residue_g (or container_g + container_residue_g)",
                  partial(analyze_gravimetric, analyte="alkaloids")),
        AssayInfo("saponins", "Saponins", "Phytochemicals",
                  "Gravimetric: n-butanol fraction, evaporated and weighed → g/kg",
                  "sample_id, replicate, sample_mass_g, residue_g (or container_g + container_residue_g)",
                  partial(analyze_gravimetric, analyte="saponins", unit="g/kg")),
        AssayInfo("dpph", "DPPH scavenging", "Antioxidant activity",
                  "(A₀ − A₁) / A₀ × 100 at 518 nm; IC50 when a dilution series is given",
                  "sample_id, replicate, abs_sample, abs_control; optional concentration, abs_blank",
                  analyze_dpph),
        AssayInfo("frap", "FRAP", "Antioxidant activity",
                  "Fe³⁺-TPTZ reduction, 593 nm, ascorbic acid standard → mg AAE/g", CURVE_COLUMNS,
                  partial(analyze_curve_assay, assay="frap")),
        AssayInfo("phytate", "Phytate", "Anti-nutrients",
                  "FeCl3 titration, thiocyanate indicator → % phytic acid", TITRE_COLUMNS, analyze_phytate),
        AssayInfo("oxalate", "Oxalate", "Anti-nutrients",
                  "Hot KMnO4 titration (0.1 N) → mg/g", TITRE_COLUMNS, analyze_oxalate),
        AssayInfo("acid_value", "Acid value & %FFA", "Oil quality",
                  "KOH titration (0.1 N) → mg KOH/g; %FFA = AV × 0.503 (as oleic)",
                  TITRE_COLUMNS + ", normality (optional, default 0.1)", analyze_acid_value),
        AssayInfo("peroxide", "Peroxide value", "Oil quality",
                  "Iodometric, Na2S2O3 titration (0.01 N) → meq O2/kg",
                  TITRE_COLUMNS + ", normality (optional, default 0.01)", analyze_peroxide),
        AssayInfo("minerals", "Minerals (AAS)", "Minerals",
                  "Wet digestion (HNO3:HClO4 4:1), AAS, per-element curves → mg/kg; ND below detection limit",
                  "kind, element, sample_id, replicate, absorbance (or reading_mg_l), std_conc_mg_l, "
                  "digest_volume_ml, sample_mass_g; or result_mg_kg / detection_status=nd; optional dilution_factor, lod_mg_l, lod_mg_kg",
                  analyze_minerals),
    ]
}


def register_assay(info: AssayInfo) -> None:
    """Extend the shared UI/CLI catalogue without changing either front end."""
    if not info.key or not all(c.islower() or c.isdigit() or c == "_" for c in info.key):
        raise ValueError("Assay keys must use lowercase letters, digits and underscores.")
    if info.key in ASSAYS:
        raise ValueError(f"Assay '{info.key}' is already registered.")
    ASSAYS[info.key] = info


def register_curve_assay(spec: CurveAssay, group: str = "Standard-curve assays") -> None:
    """Register any assay following concentration × extract volume / sample mass."""
    register_assay(AssayInfo(spec.key, spec.name, group,
                            f"{spec.standard}, {spec.wavelength_nm} nm → {spec.unit}", CURVE_COLUMNS,
                            partial(analyze_curve_assay, assay=spec)))
