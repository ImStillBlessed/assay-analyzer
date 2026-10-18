"""Scientific edge cases and multi-study import/report contracts."""

import io
import os
import subprocess
import sys

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest

from assaykit import ASSAYS, AssayInputError, CurveAssay, register_curve_assay
from assaykit.calibration import analyze_minerals
from assaykit.dpph import estimate_ic50
from assaykit.io import read_table
from assaykit.plots import figures_for
from assaykit.report import overview, to_excel


def mineral(**changes):
    return pd.DataFrame([dict(kind="sample", element="Ca", sample_id="Material A",
                              reading_mg_l=1.788, digest_volume_ml=100, sample_mass_g=1, **changes)])


def test_noisy_ic50_below_mean_threshold_does_not_crash():
    result = estimate_ic50(np.array([10., 10., 20., 20., 40., 40.]),
                           np.array([10., 20., 20., 30., 45., 51.]), "interpolation")
    assert np.isnan(result["ic50"])
    assert "IC50 > 40" in result["note"]


@pytest.mark.parametrize("column,value", [("sample_mass_g", 0), ("digest_volume_ml", -1),
                                         ("dilution_factor", 0), ("reading_mg_l", np.inf)])
def test_invalid_mineral_quantities_rejected(column, value):
    data = mineral()
    data[column] = value
    with pytest.raises(AssayInputError, match=column):
        analyze_minerals(data)


@pytest.mark.parametrize("identifier", [None, "", "   ", np.nan])
def test_missing_identifiers_rejected(identifier):
    data = pd.DataFrame([dict(sample_id=identifier, sample_mass_g=5, titre_ml=1)])
    with pytest.raises(AssayInputError, match="sample_id"):
        ASSAYS["peroxide"].run(data)


def test_duplicate_normalized_headers_rejected():
    data = pd.DataFrame([["A", "B", 5, 1]], columns=["sample_id", "Sample ID", "sample_mass_g", "titre_ml"])
    with pytest.raises(AssayInputError, match="unique"):
        ASSAYS["peroxide"].run(data)


def test_direct_minerals_and_nd_preserve_single_determinations():
    data = pd.DataFrame([
        dict(kind="sample", sample_id="Water", element="Zn", result_mg_kg=0.23, lod_mg_kg=0.1),
        dict(kind="sample", sample_id="Water", element="Pb", detection_status="nd"),
    ])
    result = analyze_minerals(data)
    summary = result.summary.set_index("element")
    assert summary.loc["Zn", "mean"] == pytest.approx(0.23)
    assert summary.loc["Pb", "result"] == "ND"
    assert summary["n"].tolist() == [1, 1]
    assert summary["sem"].isna().all()
    assert result.rows.loc[result.rows.element.eq("Pb"), "mg_per_kg"].isna().all()
    assert overview([result]).set_index("assay").loc["Pb", "result"] == "ND"


def test_supplied_instrument_lod_applies_to_direct_reading():
    result = analyze_minerals(mineral(lod_mg_l=2))
    assert result.summary.iloc[0]["result"] == "ND"
    assert result.rows.iloc[0]["effective_lod_mg_kg"] == 200


def test_unknown_lod_is_explicit_and_not_replaced_with_zero():
    result = analyze_minerals(mineral())
    assert any("detection limit unknown" in warning for warning in result.warnings)
    assert result.rows["effective_lod_mg_kg"].isna().all()


def test_mixed_nd_replicates_are_censored_not_averaged():
    data = pd.DataFrame([
        dict(kind="sample", sample_id="Water", element="Pb", result_mg_kg=1.5),
        dict(kind="sample", sample_id="Water", element="Pb", detection_status="nd"),
    ])
    result = analyze_minerals(data)
    assert result.summary.iloc[0]["result"] == "Censored"
    assert result.summary.iloc[0]["n"] == 2
    assert np.isnan(result.summary.iloc[0]["mean"])
    assert overview([result]).iloc[0]["result"] == "Censored"


def test_final_result_lod_must_have_compatible_units():
    data = pd.DataFrame([dict(kind="sample", sample_id="A", element="Zn", result_mg_kg=1, lod_mg_l=0.5)])
    with pytest.raises(AssayInputError, match="use lod_mg_kg"):
        analyze_minerals(data)


def test_mineral_missing_measurement_is_input_error():
    data = mineral().drop(columns="reading_mg_l")
    with pytest.raises(AssayInputError, match="provide absorbance"):
        analyze_minerals(data)


def test_statistics_and_alpha_exported():
    data = pd.DataFrame(dict(sample_id=["A"] * 3 + ["B"] * 3,
                             sample_mass_g=[5] * 6, titre_ml=[1, 1.1, 0.9, 3, 3.1, 2.9]))
    result = ASSAYS["peroxide"].run(data, alpha=0.01)
    workbook = pd.read_excel(io.BytesIO(to_excel([result])), sheet_name=None)
    assert workbook["ANOVA"].iloc[0]["p"] < 0.01
    assert len(workbook["Tukey comparisons"]) == 1
    assert workbook["Run details"].iloc[0]["alpha"] == 0.01
    for fig in figures_for(result).values():
        assert any("α = 0.01" in text.get_text() for text in fig.texts)
        plt.close(fig)


def test_screening_is_observational_not_statistical():
    data = pd.DataFrame([dict(sample_id="Bark", test="Froth", status="present", observation="Stable foam")])
    result = ASSAYS["screening"].run(data)
    assert overview([result]).iloc[0]["result"] == "present"
    assert "mean" not in result.summary
    assert figures_for(result) == {}
    assert to_excel([result])


def test_new_curve_assay_runs_through_registry_without_frontend_changes():
    spec = CurveAssay("custom_activity", "Custom activity", "Reference", "RE", 600, "Lab SOP")
    register_curve_assay(spec)
    try:
        data = pd.DataFrame([
            *[dict(kind="standard", sample_id="Std", std_conc=c, absorbance=0.01 * c) for c in (10, 20, 30)],
            dict(kind="sample", sample_id="Broth", absorbance=0.2, sample_mass_g=1, extract_volume_ml=10),
        ])
        result = ASSAYS[spec.key].run(data)
        assert result.summary.iloc[0]["mean"] == pytest.approx(0.2)
        assert result.unit == "mg RE/g"
        with pytest.raises(ValueError, match="already registered"):
            register_curve_assay(spec)
    finally:
        ASSAYS.pop(spec.key)


@pytest.mark.parametrize("name,content", [("broken.csv", b'one,two\n"unterminated'), ("old.xls", b"not excel"),
                                         ("broken.xlsx", b"PK invalid workbook")])
def test_import_errors_are_user_facing(name, content):
    source = io.BytesIO(content)
    source.name = name
    with pytest.raises(AssayInputError):
        read_table(source)


def test_cli_lists_assays_even_with_legacy_output_encoding():
    completed = subprocess.run([sys.executable, "-m", "assaykit.cli", "--list"],
                               env={**os.environ, "PYTHONIOENCODING": "cp1252"},
                               capture_output=True, check=True)
    assert "minerals.csv" in completed.stdout.decode("utf-8")
