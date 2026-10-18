"""Smoke test: every page of the Streamlit app renders with demo data and shows no errors."""

from pathlib import Path
import pandas as pd

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

from assaykit.assays import ASSAYS  # noqa: E402

APP = str(Path(__file__).resolve().parents[1] / "app" / "streamlit_app.py")
PAGES = ["Overview & report", "Calculated results"] + list(dict.fromkeys(a.group for a in ASSAYS.values())) + ["Settings"]


@pytest.mark.parametrize("page", PAGES)
def test_page_renders_without_errors(page):
    at = AppTest.from_file(APP, default_timeout=120)
    at.run()
    at.sidebar.radio[0].set_value(page).run()
    assert not at.exception, at.exception
    assert not at.error, [e.value for e in at.error]


def test_uploaded_datasets_survive_section_navigation():
    at = AppTest.from_file(APP, default_timeout=120).run()
    at.sidebar.toggle[0].set_value(False).run()
    at.session_state["datasets"] = {
        "peroxide": pd.DataFrame([dict(sample_id="Water-study oil", sample_mass_g=5, titre_ml=2)]),
        "alkaloids": pd.DataFrame([dict(sample_id="Bark", sample_mass_g=5, residue_g=0.1)]),
    }
    at.session_state["sources"] = {"peroxide": "oil.csv", "alkaloids": "bark.csv"}
    for page in ["Oil quality", "Phytochemicals", "Minerals", "Overview & report"]:
        at.sidebar.radio[0].set_value(page).run()
        assert not at.exception
        assert len(at.session_state["datasets"]) == 2
    assert not at.error
    assert set(at.dataframe[0].value["sample"]) == {"Water-study oil", "Bark"}


def test_per_assay_calibration_settings_apply_to_uploaded_data():
    at = AppTest.from_file(APP, default_timeout=120).run()
    at.sidebar.toggle[0].set_value(False).run()
    at.session_state["datasets"] = {"tpc": pd.DataFrame([
        *[dict(kind="standard", sample_id="Standard", std_conc=c, absorbance=c * 2) for c in (0.1, 0.2, 0.3)],
        dict(kind="sample", sample_id="Tea", absorbance=0.4, sample_mass_g=1, extract_volume_ml=10),
    ])}
    at.session_state["sources"] = {"tpc": "tea.csv"}
    at.sidebar.radio[0].set_value("Settings").run()
    at.selectbox(key="settings_assay").set_value("tpc").run()
    at.text_input(key="standard_tpc").set_value("Gallic acid")
    at.text_input(key="equiv_tpc").set_value("GAE")
    at.selectbox(key="unit_tpc").set_value("mg/mL")
    next(button for button in at.button if button.label == "Save assay settings").click().run()
    at.sidebar.radio[0].set_value("Phytochemicals").run()
    at.sidebar.radio[0].set_value("Overview & report").run()
    assert not at.exception
    assert not at.error
    row = at.dataframe[0].value.iloc[0]
    assert row["unit"] == "mg GAE/g"
    assert row["result"].startswith("2")


def test_all_assay_settings_render_and_preserve_saved_reference():
    at = AppTest.from_file(APP, default_timeout=120).run()
    at.sidebar.radio[0].set_value("Settings").run()
    for key in ASSAYS:
        at.selectbox(key="settings_assay").set_value(key).run()
        assert not at.exception, (key, at.exception)
    at.selectbox(key="settings_assay").set_value("dpph").run()
    at.selectbox(key="mode_dpph").set_value("Reference sample").run()
    next(field for field in at.text_input if field.label == "Reference sample name").set_value("Ascorbic acid")
    next(button for button in at.button if button.label == "Save assay settings").click().run()
    assert not at.error
    at.sidebar.radio[0].set_value("Antioxidant activity").run()
    assert not at.exception
    assert any("Reference and target checks" in element.value for element in at.markdown)
    at.sidebar.radio[0].set_value("Settings").run()
    at.selectbox(key="settings_assay").set_value("dpph").run()
    assert next(field for field in at.text_input if field.label == "Reference sample name").value == "Ascorbic acid"


def test_manual_entry_editor_renders_and_guidance_is_collapsible():
    at = AppTest.from_file(APP, default_timeout=120).run()
    at.sidebar.toggle[0].set_value(False).run()
    at.sidebar.radio[0].set_value("Antioxidant activity").run()
    at.radio(key="entry_dpph").set_value("Enter readings here").run()
    assert not at.exception
    assert any(button.label == "Analyze these readings" for button in at.button)
    assert any(expander.label == "How do I get these readings?" for expander in at.expander)
    guide = at.dataframe[0].value
    assert "Sample absorbance" in guide["Value"].tolist()


def test_manual_dpph_readings_are_analyzed_and_retained():
    at = AppTest.from_file(APP, default_timeout=120).run()
    at.sidebar.toggle[0].set_value(False).run()
    at.sidebar.radio[0].set_value("Antioxidant activity").run()
    at.radio(key="entry_dpph").set_value("Enter readings here").run()
    at.session_state["editor_dpph"] = {"edited_rows": {}, "deleted_rows": [], "added_rows": [
        {"sample_id": "Tea", "replicate": "1", "abs_sample": "0.4", "abs_control": "0.8"}
    ]}
    next(button for button in at.button if button.label == "Analyze these readings").click().run()
    assert not at.exception
    assert not at.error
    at.sidebar.radio[0].set_value("Overview & report").run()
    table = at.dataframe[0].value
    assert table.iloc[0]["sample"] == "Tea"
    assert table.iloc[0]["result"] == "50"


def test_provided_results_example_is_loaded_and_reference_checks_work():
    at = AppTest.from_file(APP, default_timeout=120).run()
    assert at.sidebar.selectbox[0].value == "Supplied results tables"
    assert any("sample" in frame.value and frame.value["sample"].eq("Cottonseed").any() for frame in at.dataframe)
    at.sidebar.radio[0].set_value("Calculated results").run()
    next(button for button in at.button if button.label.startswith("Compare DPPH and FRAP")).click().run()
    assert not at.exception
    assert not at.error
    checks = [frame.value for frame in at.dataframe if "Flag" in frame.value.columns]
    assert len(checks) == 2
    assert any("Below reference" in frame["Flag"].tolist() for frame in checks)
    assert all("No matching reference" not in frame["Flag"].tolist() for frame in checks)
