"""Known-answer recovery from visually checked results-only tables."""

import io
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from assaykit import AssayInputError
from assaykit.results_input import analyze_result_table
from assaykit.report import overview, to_excel
from assaykit.plots import figures_for
import matplotlib.pyplot as plt

EXAMPLE = Path(__file__).resolve().parents[1] / "data/examples/provided_results.csv"


def examples(combine=True):
    return analyze_result_table(pd.read_csv(EXAMPLE), combine_repeats=combine)


def find(results, key):
    return next(result for result in results if result.extra["assay_key"] == key)


def test_all_76_observations_are_retained_without_recreating_bench_readings():
    results = examples()
    assert sum(len(result.rows) for result in results) == 76
    assert len(results) == 13
    assert all(result.extra["input_basis"] == "calculated_results" for result in results)
    assert all("abs_control" not in result.rows and "titre_ml" not in result.rows for result in results)
    assert len(overview(results)) > 10
    assert to_excel(results)


def test_confirmed_repeats_match_independently_calculated_statistics():
    results = examples()
    tpc = find(results, "tpc").summary.set_index("sample_id")
    assert tpc.loc["Cottonseed", "mean"] == pytest.approx((81.545 + 82.803 + 82.703) / 3)
    assert tpc.loc["Cottonseed", "n"] == 3
    assert tpc.loc["Cottonseed", "sem"] == pytest.approx(np.std([81.545, 82.803, 82.703], ddof=1) / np.sqrt(3))
    acid = find(results, "acid_value").summary.iloc[0]
    assert acid["mean"] == pytest.approx((26.297 + 17.262 + 26.354) / 3)
    assert acid["n"] == 3
    assert find(results, "alkaloids").rows["value"].tolist() == [6., 6.85, 7.15]
    assert find(results, "oxalate").rows["value"].tolist() == [0.445, 0.435, 0.435]


def test_grouping_is_opt_in_for_general_inputs():
    result = find(examples(False), "tpc")
    assert len(result.summary) == 6
    assert result.summary["n"].eq(1).all()
    assert result.summary["sem"].isna().all()


def test_dpph_series_are_not_five_replicates_and_no_false_significance():
    res = find(examples(), "dpph")
    assert len(res.rows) == 15  # the identical ascorbic acid series is not counted twice
    assert res.summary["n"].eq(1).all()
    assert res.summary["sem"].isna().all()
    assert res.summary["letters"].eq("").all()
    ic50 = res.extra["ic50"].set_index("sample_id")
    assert np.isnan(ic50.loc["Cottonseed", "mean"])
    assert "IC50 > 250" in ic50.loc["Cottonseed", "note"]
    assert ic50.loc["Cottonseed oil", "n"] == 1
    assert np.isnan(ic50.loc["Cottonseed oil", "sem"])


def test_frap_percent_and_mineral_zeros_keep_source_meaning():
    results = examples()
    frap = find(results, "frap")
    assert frap.unit == "% FRAP (reported)"
    assert any("normalization formula is unknown" in warning for warning in frap.warnings)
    assert frap.rows["value"].tolist()[-5:] == [80.743, 69.170, 60.532, 40.221, 33.775]
    minerals = find(results, "minerals")
    assert len(minerals.rows) == 18
    assert minerals.rows["value"].eq(0).sum() == 6
    assert minerals.summary["n"].eq(1).all()
    assert minerals.summary["result"].eq("numeric").all()
    assert any("no LOD is inferred" in warning for warning in minerals.warnings)


def test_plot_and_workbook_support_every_reported_assay():
    results = examples()
    for result in results:
        for figure in figures_for(result).values():
            assert figure.axes
            plt.close(figure)
    book = pd.read_excel(io.BytesIO(to_excel(results)), sheet_name=None)
    assert book["Run details"]["input_basis"].eq("calculated_results").all()
    assert book["Calibrations"].empty


@pytest.mark.parametrize("change", [{"unit": ""}, {"value": np.inf}, {"value": None}, {"status": "nd"}])
def test_invalid_calculated_inputs_are_rejected(change):
    row = {"assay": "activity", "sample_id": "A", "value": 10., "unit": "U/g", **change}
    with pytest.raises(AssayInputError):
        analyze_result_table(pd.DataFrame([row]))


def test_unknown_future_measurements_and_explicit_nd_can_be_imported():
    data = pd.DataFrame([dict(assay="new_activity", sample_id="A", value=10, unit="U/g"),
                         dict(assay="new_activity", sample_id="B", value=np.nan, unit="U/g", status="nd")])
    res = analyze_result_table(data)[0]
    assert res.unit == "U/g"
    assert res.summary.set_index("sample_id").loc["B", "result"] == "ND"
