"""Reusable laboratory assay calculations, validation, statistics and reports.

See `assaykit.assays.ASSAYS` for supported assays and registration helpers.
"""

from assaykit.assays import ASSAYS, AssayInfo, register_assay, register_curve_assay
from assaykit.calibration import CurveAssay, analyze_curve_assay, analyze_minerals
from assaykit.screening import analyze_screening
from assaykit.common import AssayInputError, AssayResult
from assaykit.dpph import analyze_dpph
from assaykit.dpph import analyze_dpph_inhibition
from assaykit.results_input import analyze_result_table
from assaykit.gravimetric import analyze_gravimetric
from assaykit.titration import analyze_acid_value, analyze_oxalate, analyze_peroxide, analyze_phytate

__version__ = "0.2.0"

__all__ = [
    "ASSAYS",
    "AssayInfo",
    "CurveAssay",
    "register_assay",
    "register_curve_assay",
    "analyze_screening",
    "AssayInputError",
    "AssayResult",
    "analyze_acid_value",
    "analyze_curve_assay",
    "analyze_dpph",
    "analyze_dpph_inhibition",
    "analyze_result_table",
    "analyze_gravimetric",
    "analyze_minerals",
    "analyze_oxalate",
    "analyze_peroxide",
    "analyze_phytate",
]
