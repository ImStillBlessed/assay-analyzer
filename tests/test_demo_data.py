"""End-to-end: the demo data was simulated from known true values (scripts/make_demo_data.py),
so analysing it must recover them."""

import importlib.util
from pathlib import Path

import pandas as pd
import pytest

from assaykit import ASSAYS

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("make_demo_data", ROOT / "scripts" / "make_demo_data.py")
demo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(demo)
TRUE = demo.TRUE


def run(key):
    return ASSAYS[key].run(pd.read_csv(ROOT / "data" / "demo" / f"{key}.csv"))


@pytest.mark.parametrize("key", ["tpc", "flavonoids", "tannins", "frap", "alkaloids", "saponins", "phytate",
                                 "oxalate", "acid_value", "peroxide"])
def test_recovers_true_values(key):
    summary = run(key).summary.set_index("sample_id")
    for sample, value in TRUE[key].items():
        assert summary.loc[sample, "mean"] == pytest.approx(value, rel=0.08), sample


def test_dpph_ic50():
    ic50 = run("dpph").extra["ic50"].set_index("sample_id")
    for sample, value in TRUE["dpph_ic50"].items():
        assert ic50.loc[sample, "mean"] == pytest.approx(value, rel=0.15), sample
    assert ic50.loc["Ascorbic acid", "letters"].startswith("a")


def test_minerals_detect_present_and_report_absent_as_nd():
    res = run("minerals")
    s = res.summary.set_index(["element", "sample_id"])
    for element, samples in TRUE["minerals"].items():
        lod = res.extra["lods_mg_l"][element]
        for sample, value in samples.items():
            row = s.loc[(element, sample)]
            if value is None:
                assert row["result"] == "ND", (element, sample)
            elif value / 100 > 10 * lod:  # digest (1 g in 100 mL) well above the detection limit
                assert row["mean"] == pytest.approx(value, rel=0.15), (element, sample)


def test_every_demo_file_runs_without_errors():
    for key in ASSAYS:
        assert run(key).summary is not None
