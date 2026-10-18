"""Each expected value below is worked out by hand from the formula in the module docstring."""

import math

import numpy as np
import pandas as pd
import pytest

from assaykit import (
    ASSAYS,
    AssayInputError,
    analyze_acid_value,
    analyze_curve_assay,
    analyze_dpph,
    analyze_gravimetric,
    analyze_minerals,
    analyze_oxalate,
    analyze_peroxide,
    analyze_phytate,
)
from assaykit.dpph import estimate_ic50, logistic
from assaykit.stats import compact_letter_display, summarize


def one(**cols):
    return pd.DataFrame({k: [v] for k, v in cols.items()})


# ---------- titration (thesis section 3.6, 3.7) ----------


def test_acid_value_and_ffa_as_in_thesis():
    # AV = 5.00 mL × 0.1 N × 56.1 / 5.00 g = 5.61 mg KOH/g ; %FFA = 5.61 × 0.503 = 2.8218
    res = analyze_acid_value(one(sample_id="Oil", sample_mass_g=5.0, titre_ml=5.0))
    assert res.rows["acid_value_mg_koh_g"].iloc[0] == pytest.approx(5.61)
    assert res.rows["ffa_pct"].iloc[0] == pytest.approx(5.61 * 0.503)


def test_peroxide_value_with_blank():
    # (6.10 − 0.10) × 0.01 × 1000 / 5.00 = 12.0 meq O2/kg
    res = analyze_peroxide(one(sample_id="Oil", sample_mass_g=5.0, titre_ml=6.10, blank_titre_ml=0.10))
    assert res.rows["pv_meq_kg"].iloc[0] == pytest.approx(12.0)


def test_normality_column_overrides_default():
    res = analyze_peroxide(one(sample_id="Oil", sample_mass_g=5.0, titre_ml=6.0, normality=0.02))
    assert res.rows["pv_meq_kg"].iloc[0] == pytest.approx(24.0)


def test_phytate_formula():
    # 8.24 × 11.65 = 95.996 ; × 100 / (1000 × 4) = 2.3999 %
    res = analyze_phytate(one(sample_id="Seed", sample_mass_g=4.0, titre_ml=11.65))
    assert res.rows["phytate_pct"].iloc[0] == pytest.approx(2.3999)


def test_oxalate_formula():
    # 0.50 mL × 0.9004 / 1 g = 0.4502 mg/g
    res = analyze_oxalate(one(sample_id="Seed", sample_mass_g=1.0, titre_ml=0.50))
    assert res.rows["oxalate_mg_g"].iloc[0] == pytest.approx(0.4502)


def test_titre_below_blank_warns():
    res = analyze_peroxide(one(sample_id="Oil", sample_mass_g=5.0, titre_ml=0.05, blank_titre_ml=0.10))
    assert any("smaller than the blank" in w for w in res.warnings)


def test_high_peroxide_value_is_flagged_against_codex():
    res = analyze_peroxide(pd.DataFrame({"sample_id": ["Oil"] * 3, "sample_mass_g": [5.0] * 3,
                                         "titre_ml": [50.0, 50.2, 49.8]}))
    assert any("Codex" in w for w in res.warnings)


# ---------- gravimetric (3.4.2, 3.4.4) ----------


def test_gravimetric_percent_from_tare():
    # residue = 30.2750 − 30.0000 = 0.2750 g ; 0.2750 / 5.000 × 100 = 5.5 %
    res = analyze_gravimetric(one(sample_id="Seed", sample_mass_g=5.0, container_g=30.0, container_residue_g=30.275))
    assert res.rows["content"].iloc[0] == pytest.approx(5.5)


def test_gravimetric_g_per_kg():
    res = analyze_gravimetric(one(sample_id="Seed", sample_mass_g=5.0, residue_g=0.055), analyte="saponins", unit="g/kg")
    assert res.rows["content"].iloc[0] == pytest.approx(11.0)


# ---------- standard-curve assays (3.4.1, 3.4.3, 3.4.5, 3.5.2) ----------


def _standards(slope=0.002, intercept=0.01, levels=(50, 100, 200, 400)):
    return [{"kind": "standard", "sample_id": "Std", "absorbance": slope * c + intercept, "std_conc": c} for c in levels]


def test_curve_assay_per_gram_from_extraction():
    # A = 0.002·C + 0.01 ; A = 0.71 → 350 µg/mL ; × 20 dilution × 10 mL / 1 g / 1000 = 70 mg TAE/g
    rows = _standards() + [{"kind": "sample", "sample_id": "Seed", "absorbance": 0.71, "dilution_factor": 20,
                            "sample_mass_g": 1.0, "extract_volume_ml": 10}]
    res = analyze_curve_assay(pd.DataFrame(rows), "tpc")
    assert res.extra["curve"].r2 == pytest.approx(1.0)
    assert res.extra["samples"]["result_mg_per_g"].iloc[0] == pytest.approx(70.0)
    assert res.unit == "mg TAE/g"


def test_curve_assay_per_gram_from_stock_concentration():
    # 0.01 + 0.002 × 500 = 1.01 → 500 µg/mL ÷ 2 mg/mL = 250 mg AAE/g
    rows = _standards(levels=(100, 250, 500, 750)) + [
        {"kind": "sample", "sample_id": "Seed", "absorbance": 1.01, "extract_mg_per_ml": 2.0}]
    res = analyze_curve_assay(pd.DataFrame(rows), "frap")
    assert res.extra["samples"]["result_mg_per_g"].iloc[0] == pytest.approx(250.0)
    assert res.unit == "mg AAE/g"


def test_reagent_blank_is_subtracted_and_mg_ml_standards_convert():
    rows = [{"kind": "standard", "sample_id": "Std", "absorbance": 0.002 * c + 0.05, "std_conc": c / 1000}
            for c in (100, 200, 400)]
    rows += [{"kind": "blank", "sample_id": "Blank", "absorbance": 0.05},
             {"kind": "sample", "sample_id": "X", "absorbance": 0.65}]
    res = analyze_curve_assay(pd.DataFrame(rows), "flavonoids", std_unit="mg/mL")
    assert res.extra["curve"].intercept == pytest.approx(0.0, abs=1e-9)
    assert res.extra["samples"]["conc_ug_ml"].iloc[0] == pytest.approx(300.0)
    assert any("not per gram" in w for w in res.warnings)


def test_sample_above_curve_is_flagged():
    rows = _standards() + [{"kind": "sample", "sample_id": "Seed", "absorbance": 2.5}]
    assert any("above the highest standard" in w for w in analyze_curve_assay(pd.DataFrame(rows), "tpc").warnings)


# ---------- minerals (3.8) ----------


def _mineral_rows(sample_abs):
    rows = [{"kind": "standard", "element": "Fe", "sample_id": "Std", "absorbance": 0.1 * c, "std_conc_mg_l": c}
            for c in (0.25, 0.5, 1, 2)]
    rows += [{"kind": "blank", "element": "Fe", "sample_id": "Blank", "absorbance": a} for a in (0.000, 0.001, -0.001)]
    rows += [{"kind": "sample", "element": "Fe", "sample_id": "Seed", "absorbance": sample_abs,
              "digest_volume_ml": 100, "sample_mass_g": 1.0}]
    return pd.DataFrame(rows)


def test_mineral_mg_per_kg():
    # 0.05 / 0.1 = 0.5 mg/L × 100 mL / 1 g = 50 mg/kg
    res = analyze_minerals(_mineral_rows(0.05))
    assert res.rows["mg_per_kg"].iloc[0] == pytest.approx(50.0, rel=1e-3)
    # LOD = 3 × SD(blanks) / slope = 3 × 0.001 / 0.1 = 0.03 mg/L
    assert res.extra["lods_mg_l"]["Fe"] == pytest.approx(0.03, rel=1e-3)


def test_mineral_below_detection_limit_is_nd():
    res = analyze_minerals(_mineral_rows(0.001))
    assert res.summary["result"].iloc[0] == "ND"


def test_mineral_direct_instrument_reading():
    df = one(kind="sample", element="Ca", sample_id="Seed", reading_mg_l=1.788, digest_volume_ml=100, sample_mass_g=1.0)
    assert analyze_minerals(df).rows["mg_per_kg"].iloc[0] == pytest.approx(178.8)


# ---------- DPPH (3.5.1) ----------


def test_dpph_single_volume_as_in_thesis():
    # (A₀ − A₁) / A₀ × 100 = (0.90 − 0.45) / 0.90 × 100 = 50 %
    res = analyze_dpph(one(sample_id="Seed", abs_sample=0.45, abs_control=0.90))
    assert res.rows["inhibition_pct"].iloc[0] == pytest.approx(50.0)
    assert res.extra["ic50"].empty


def test_dpph_sample_blank_removes_extract_colour():
    res = analyze_dpph(one(sample_id="Seed", abs_sample=0.50, abs_control=0.90, abs_blank=0.05))
    assert res.rows["inhibition_pct"].iloc[0] == pytest.approx(50.0)


def test_logistic_recovers_known_ic50():
    top, hill, ic50 = 95.0, 1.4, 120.0
    mid = ic50 * (top / 50 - 1) ** (1 / hill)
    x = np.array([25, 50, 100, 200, 400], dtype=float)
    assert estimate_ic50(x, logistic(x, top, mid, hill), "logistic")["ic50"] == pytest.approx(ic50, rel=1e-3)


def test_interpolation_is_on_log_concentration():
    # 40 % at 10, 60 % at 20 → halfway on a log axis = √(10 × 20)
    est = estimate_ic50(np.array([10.0, 20.0]), np.array([40.0, 60.0]), "interpolation")
    assert est["ic50"] == pytest.approx(math.sqrt(200))


def test_linear_regression_ic50():
    x = np.array([5.0, 10, 15, 20, 25])
    assert estimate_ic50(x, 2 * x + 10, "linear")["ic50"] == pytest.approx(20.0)  # 50 = 2x + 10


def test_ic50_not_reached_is_reported_not_invented():
    est = estimate_ic50(np.array([10.0, 20, 40]), np.array([10.0, 20, 35]), "logistic")
    assert math.isnan(est["ic50"]) and "not reached" in est["note"]


# ---------- statistics (3.9) ----------


def test_sem_is_sd_over_root_n():
    df = pd.DataFrame({"sample_id": ["A"] * 3, "v": [1.0, 2.0, 3.0]})
    t = summarize(df, "v")[0]
    assert t["sd"].iloc[0] == pytest.approx(1.0)
    assert t["sem"].iloc[0] == pytest.approx(1 / math.sqrt(3))


def test_compact_letters_overlapping_groups():
    p = np.array([[1, 0.2, 0.01], [0.2, 1, 0.3], [0.01, 0.3, 1]])  # only A vs C differ
    assert compact_letter_display(["A", "B", "C"], [30, 20, 10], p) == {"A": "a", "B": "ab", "C": "b"}


def test_compact_letters_all_different():
    p = np.full((3, 3), 0.001)
    assert compact_letter_display(["A", "B", "C"], [10, 30, 20], p) == {"B": "a", "C": "b", "A": "c"}


# ---------- input handling ----------


def test_missing_column_names_what_is_missing():
    with pytest.raises(AssayInputError, match="abs_control"):
        analyze_dpph(one(sample_id="A", abs_sample=0.5))


def test_non_numeric_value_reports_spreadsheet_row():
    df = pd.DataFrame({"sample_id": ["A", "A"], "sample_mass_g": [5.0, "5,02"], "titre_ml": [3.0, 3.1]})
    with pytest.raises(AssayInputError, match=r"row\(s\) 3"):
        analyze_peroxide(df)


def test_human_style_headers_are_accepted():
    df = pd.DataFrame({"Sample ID": ["A"], "Sample mass g": [5.0], "Titre mL": [6.0]})
    assert analyze_peroxide(df).rows["pv_meq_kg"].iloc[0] == pytest.approx(12.0)


def test_registry_passes_only_accepted_options():
    df = one(sample_id="Oil", sample_mass_g=5.0, titre_ml=6.0)
    res = ASSAYS["peroxide"].run(df, method="logistic", alpha=0.05, conc_unit="x")
    assert res.rows["pv_meq_kg"].iloc[0] == pytest.approx(12.0)
