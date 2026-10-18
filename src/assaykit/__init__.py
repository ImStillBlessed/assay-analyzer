"""assaykit: turn raw bench readings into thesis-ready results.

Covers the phytochemical, antioxidant, anti-nutrient, oil-quality and mineral assays of a
seed and seed-oil study. See `assaykit.assays.ASSAYS` for the full list.
"""

from assaykit.assays import ASSAYS
from assaykit.calibration import analyze_curve_assay, analyze_minerals
from assaykit.common import AssayInputError, AssayResult
from assaykit.dpph import analyze_dpph
from assaykit.gravimetric import analyze_gravimetric
from assaykit.titration import analyze_acid_value, analyze_oxalate, analyze_peroxide, analyze_phytate

__version__ = "0.2.0"

__all__ = [
    "ASSAYS",
    "AssayInputError",
    "AssayResult",
    "analyze_acid_value",
    "analyze_curve_assay",
    "analyze_dpph",
    "analyze_gravimetric",
    "analyze_minerals",
    "analyze_oxalate",
    "analyze_peroxide",
    "analyze_phytate",
]
