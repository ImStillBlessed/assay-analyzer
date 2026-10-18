"""Benchmarks must match the measured quantity, units and test conditions."""

import io

import numpy as np
import pandas as pd
import pytest

from assaykit import ASSAYS, AssayInputError, AssayResult
from assaykit.assessment import assess_results
from assaykit.guidance import FIELDS, GUIDES
from assaykit.report import to_excel


def result(table, assay="DPPH", unit="% inhibition"):
    return AssayResult(assay, unit, table.copy(), table)


def reference(**changes):
    return {"mode": "Reference sample", "reference": "Control", "direction": "Higher is the target", **changes}


def test_reference_comparison_matches_dpph_concentration():
    data = pd.DataFrame({"sample_id": ["A", "A", "A", "Control", "Control"],
                         "concentration": [10, 20, 30, 10, 20], "mean": [30., 80., 90., 50., 70.]})
    checks = assess_results(result(data), reference())
    assert checks["Flag"].tolist() == ["Below reference", "Meets reference", "No matching reference", "Reference", "Reference"]
    assert "not a test of statistical significance" in checks.iloc[0]["What to do"]


def test_reference_does_not_compare_different_elements():
    data = pd.DataFrame({"sample_id": ["A", "Control"], "element": ["Fe", "Zn"], "mean": [30., 50.]})
    checks = assess_results(result(data, "Minerals (AAS)", "mg/kg"), reference())
    assert checks.iloc[0]["Flag"] == "No matching reference"


def test_nd_reference_cannot_generate_a_favorable_flag():
    data = pd.DataFrame({"sample_id": ["A", "Control"], "mean": [30., np.nan]})
    checks = assess_results(result(data), reference())
    assert checks["Flag"].tolist() == ["No matching reference", "No matching reference"]


def test_target_range_includes_boundaries_but_not_missing_values():
    data = pd.DataFrame({"sample_id": list("ABCDE"), "mean": [9., 10., 20., 21., np.nan]})
    config = {"mode": "Target range", "lower": 10., "upper": 20., "unit": "% inhibition"}
    checks = assess_results(result(data), config)
    assert checks["Flag"].tolist() == ["Below target", "Within target", "Within target", "Above target", "Needs review"]


@pytest.mark.parametrize("changes", [{"unit": "mg/g"}, {"lower": 30}, {"upper": np.inf}])
def test_invalid_targets_rejected(changes):
    config = {"mode": "Target range", "lower": 10., "upper": 20., "unit": "% inhibition", **changes}
    with pytest.raises(AssayInputError):
        assess_results(result(pd.DataFrame({"sample_id": ["A"], "mean": [15.]})), config)


def test_mineral_range_applies_only_to_selected_element():
    data = pd.DataFrame({"sample_id": ["A", "A"], "element": ["Fe", "Zn"], "mean": [30., 1000.]})
    config = {"mode": "Target range", "lower": 0., "upper": 50., "unit": "mg/kg", "element": "Fe"}
    checks = assess_results(result(data, "Minerals (AAS)", "mg/kg"), config)
    assert len(checks) == 1
    assert checks.iloc[0]["Flag"] == "Within target"
    with pytest.raises(AssayInputError, match="element"):
        assess_results(result(data, unit="mg/kg"), {**config, "element": ""})


def test_ic50_uses_its_own_unit_and_lower_direction():
    res = result(pd.DataFrame({"sample_id": ["A"], "mean": [90.]}))
    res.extra = {"ic50": pd.DataFrame({"sample_id": ["A", "Control"], "mean": [20., 30.]}), "conc_unit": "µg/mL"}
    checks = assess_results(res, reference(measurement="IC50", direction="Lower is the target"))
    assert checks.iloc[0]["Flag"] == "Meets reference"
    assert checks.iloc[0]["Unit"] == "µg/mL"


def test_comparison_flags_and_source_are_exported():
    data = pd.DataFrame({"sample_id": ["Oil"] * 3, "sample_mass_g": [5.] * 3, "titre_ml": [2., 2.1, 1.9]})
    res = ASSAYS["peroxide"].run(data)
    res.extra["assessment_config"] = {"mode": "Target range", "lower": 0., "upper": 3., "unit": res.unit, "source": "Lab SOP 123"}
    res.extra["assessment"] = assess_results(res, res.extra["assessment_config"])
    workbook = pd.read_excel(io.BytesIO(to_excel([res])), sheet_name=None)
    assert workbook["PV checks"].iloc[0]["Flag"] == "Above target"
    assert workbook["PV checks"].iloc[0]["Benchmark source"] == "Lab SOP 123"
    assert "Lab SOP 123" in workbook["Run details"].iloc[0]["result_checks"]


def test_every_builtin_has_input_and_measurement_guidance():
    assert set(ASSAYS) <= set(GUIDES)
    assert all(field in FIELDS for guide in GUIDES.values() for field in guide["fields"])
