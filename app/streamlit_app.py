"""Guided laboratory dashboard: streamlit run app/streamlit_app.py."""

from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st

from assaykit import ASSAYS, AssayInputError
from assaykit.assessment import assess_results
from assaykit.calibration import CURVE_ASSAYS
from assaykit.guidance import FIELDS, guide_for
from assaykit.io import read_table
from assaykit.plots import figures_for
from assaykit.report import overview, to_excel
from assaykit.results_input import analyze_result_table

ROOT = Path(__file__).resolve().parents[1]
DEMO, TEMPLATES = ROOT / "data" / "demo", ROOT / "templates"
RESULTS_EXAMPLE = ROOT / "data" / "examples" / "provided_results.csv"
GROUPS = list(dict.fromkeys(a.group for a in ASSAYS.values()))
st.set_page_config(page_title="Assay Analyzer", page_icon="🧪", layout="wide")
_calculated_cache = None  # Reused between tabs during this run; reset on every rerun.


def defaults(key):
    spec = CURVE_ASSAYS.get(key)
    unit = {"dpph": "% inhibition", "acid_value": "mg KOH/g", "peroxide": "meq O2/kg",
            "phytate": "% phytic acid", "oxalate": "mg/g", "minerals": "mg/kg",
            "alkaloids": "%", "saponins": "g/kg"}.get(key, "")
    return {"standard": spec.standard if spec else "", "abbrev": spec.abbrev if spec else "",
            "wavelength": spec.wavelength_nm if spec else 518, "std_unit": "µg/mL", "min_r2": 0.995 if key == "minerals" else 0.99,
            "normality": 0.01 if key == "peroxide" else 0.1, "fatty_acid": "oleic",
            "mg_per_ml": 8.24 if key == "phytate" else 0.9004, "aliquot_factor": 1.0,
            "method": "logistic", "conc_unit": "µg/mL",
            "comparison": {"mode": "Off", "measurement": "Result", "reference": "",
                           "direction": "Higher is the target", "lower": 0.0, "upper": 100.0,
                           "unit": spec.unit if spec else unit, "element": "", "source": "User-defined target"}}


if "preferences" not in st.session_state:
    st.session_state["preferences"] = {"study_name": "", "err": "sem", "alpha": 0.05, "cv_limit": 10.0, "assays": {}}
prefs = st.session_state["preferences"]
for key in ASSAYS:
    prefs["assays"].setdefault(key, defaults(key))


def store_upload(key):
    upload = st.session_state.get(f"up_{key}")
    if upload is None:
        return
    try:
        st.session_state.setdefault("datasets", {})[key] = read_table(upload)
        st.session_state.setdefault("sources", {})[key] = upload.name
        st.session_state.setdefault("import_errors", {}).pop(key, None)
    except AssayInputError as exc:
        st.session_state.setdefault("datasets", {}).pop(key, None)
        st.session_state.setdefault("import_errors", {})[key] = str(exc)


def remove_dataset(key):
    for name in ("datasets", "sources", "import_errors"):
        st.session_state.get(name, {}).pop(key, None)
    for widget in (f"up_{key}", f"editor_{key}"):
        st.session_state.pop(widget, None)


with st.sidebar:
    st.title("🧪 Assay Analyzer")
    st.caption("Readings → results → clear next steps")
    page = st.radio("Go to", ["Overview & report", "Calculated results"] + GROUPS + ["Settings"])
    st.divider()
    use_demo = st.toggle("Use example data", value=True, help="Choose the supplied results tables or synthetic bench readings below. Turn off for your own data.")
    example = st.selectbox("Example dataset", ["Supplied results tables", "Synthetic bench readings"], disabled=not use_demo,
                           help="The supplied tables contain actual calculated observations. The bench-reading example is synthetic.")
    st.caption("1. Choose an assay\n\n2. Add your readings\n\n3. Review results and flags")
    if prefs["study_name"]:
        st.caption("Current study: " + prefs["study_name"])


def load(key):
    if use_demo:
        if example == "Supplied results tables":
            return None
        path = DEMO / f"{key}.csv"
        return pd.read_csv(path) if path.exists() else None
    return st.session_state.get("datasets", {}).get(key)


def calculated_results():
    global _calculated_cache
    if _calculated_cache is None:
        _calculated_cache = _calculate_results()
    return _calculated_cache


def _calculate_results():
    if use_demo:
        if example != "Supplied results tables":
            return [], None
        table, source = pd.read_csv(RESULTS_EXAMPLE), "cotton-result-only.pdf (verified transcription)"
        combine = st.session_state.get("example_repeats", True)
    else:
        table = st.session_state.get("results_dataset")
        if table is None:
            return [], st.session_state.get("results_import_error")
        source = st.session_state.get("results_source", "Calculated results upload")
        combine = st.session_state.get("uploaded_result_repeats", False)
    try:
        results = analyze_result_table(table, combine_repeats=combine, cv_limit=prefs["cv_limit"], alpha=prefs["alpha"],
                                      method=prefs["assays"]["dpph"]["method"])
        for result in results:
            result.extra.update(source=source, study=prefs["study_name"])
            key = result.extra["assay_key"]
            cfg = deepcopy(prefs["assays"].get(key, defaults(key))["comparison"])
            if key == "ffa" and prefs["assays"]["acid_value"]["comparison"]["measurement"] == "FFA":
                cfg = deepcopy(prefs["assays"]["acid_value"]["comparison"])
                cfg["measurement"] = "Result"
            elif key == "acid_value" and cfg["measurement"] == "FFA":
                cfg["mode"] = "Off"
            result.extra["assessment_config"] = cfg
            try:
                result.extra["assessment"] = assess_results(result, cfg)
            except AssayInputError as exc:
                result.extra["assessment_error"] = str(exc)
        return results, None
    except AssayInputError as exc:
        return [], str(exc)


def store_results_upload():
    upload = st.session_state.get("results_upload")
    if upload is None:
        return
    try:
        st.session_state["results_dataset"] = read_table(upload)
        st.session_state["results_source"] = upload.name
        st.session_state.pop("results_import_error", None)
    except AssayInputError as exc:
        st.session_state.pop("results_dataset", None)
        st.session_state["results_import_error"] = str(exc)


def analyse(key):
    raw = load(key)
    if not use_demo and key in st.session_state.get("import_errors", {}):
        return raw, AssayInputError(st.session_state["import_errors"][key])
    if raw is None:
        return None, None
    cfg = defaults(key) if use_demo else prefs["assays"][key]
    options = {"alpha": prefs["alpha"], "cv_limit": prefs["cv_limit"]}
    if key in CURVE_ASSAYS:
        options.update(assay=replace(CURVE_ASSAYS[key], standard=cfg["standard"], abbrev=cfg["abbrev"], wavelength_nm=cfg["wavelength"]),
                       std_unit=cfg["std_unit"], min_r2=cfg["min_r2"])
    if key == "dpph":
        options.update(method=cfg["method"], conc_unit=cfg["conc_unit"])
    if key == "minerals":
        options["min_r2"] = cfg["min_r2"]
    if key in ("acid_value", "peroxide"):
        options["normality"] = cfg["normality"]
    if key == "acid_value":
        options["fatty_acid"] = cfg["fatty_acid"]
    if key in ("phytate", "oxalate"):
        options["mg_per_ml"] = cfg["mg_per_ml"]
    if key == "phytate":
        options["aliquot_factor"] = cfg["aliquot_factor"]
    try:
        result = ASSAYS[key].run(raw, **options)
        result.extra["source"] = f"Synthetic demo: {key}.csv" if use_demo else st.session_state.get("sources", {}).get(key, "Manual entry")
        result.extra["study"] = prefs["study_name"]
        result.extra["assessment_config"] = deepcopy(prefs["assays"][key]["comparison"])
        try:
            result.extra["assessment"] = assess_results(result, result.extra["assessment_config"])
        except AssayInputError as exc:
            result.extra["assessment"] = pd.DataFrame()
            result.extra["assessment_error"] = str(exc)
        return raw, result
    except AssayInputError as exc:
        return raw, exc


def show_settings():
    st.title("Settings")
    st.write("Set up your study once. Assay pages use these saved choices for your own readings.")
    st.caption("Settings stay in this browser session. Demo data uses built-in calibration; you can still try comparison settings on it.")
    st.caption("Calculated-results imports keep their supplied units and values. Calibration settings apply to bench readings; comparison settings apply to both input types.")
    general, methods = st.tabs(["Study & reporting", "Assay methods & comparisons"])
    with general:
        with st.form("general_settings"):
            name = st.text_input("Study name", prefs["study_name"])
            spread = st.radio("Summarize repeat measurements as", ["sem", "sd"], index=["sem", "sd"].index(prefs["err"]),
                              format_func=lambda x: "Mean ± SEM (uncertainty in the average)" if x == "sem" else "Mean ± SD (spread of readings)")
            cv = st.number_input("Flag repeats that vary by more than (%)", min_value=1.0, max_value=100.0, value=prefs["cv_limit"])
            with st.expander("Advanced: statistical comparisons"):
                alpha = st.selectbox("Significance level", [0.01, 0.05, 0.10], index=[0.01, 0.05, 0.10].index(prefs["alpha"]))
                st.caption("Controls ANOVA/Tukey comparisons. Dashboard target flags are descriptive checks, not significance tests.")
            if st.form_submit_button("Save study settings", type="primary"):
                prefs.update(study_name=name.strip(), err=spread, cv_limit=cv, alpha=alpha)
                st.success("Study settings saved.")
    with methods:
        key = st.selectbox("Choose the assay to configure", list(ASSAYS), format_func=lambda k: ASSAYS[k].title, key="settings_assay")
        cfg = deepcopy(prefs["assays"][key])
        st.info(guide_for(key)["purpose"])
        comparison = cfg["comparison"]
        if key != "screening":
            modes = ["Off", "Reference sample", "Target range"]
            comparison["mode"] = st.selectbox("Compare results with", modes, index=modes.index(comparison["mode"]), key=f"mode_{key}")
        with st.form(f"settings_{key}"):
            st.subheader("Method and calibration")
            if key in CURVE_ASSAYS:
                st.caption("A standard curve turns absorbance into concentration. It does not set an acceptable-result limit.")
                cfg["standard"] = st.text_input("Calibration standard", cfg["standard"], key=f"standard_{key}")
                cfg["abbrev"] = st.text_input("Equivalent label", cfg["abbrev"], help="For example GAE for gallic acid equivalents.", key=f"equiv_{key}")
                cfg["wavelength"] = st.number_input("Measurement wavelength (nm)", min_value=1, value=cfg["wavelength"])
                cfg["std_unit"] = st.selectbox("Known standard concentration unit", ["µg/mL", "mg/mL", "mg/L"], index=["µg/mL", "mg/mL", "mg/L"].index(cfg["std_unit"]), key=f"unit_{key}")
                cfg["min_r2"] = st.number_input("Warn if standard-curve R² is below", min_value=0.0, max_value=1.0, value=cfg["min_r2"], step=0.001, format="%.3f")
            elif key == "dpph":
                st.write("DPPH uses a measured solvent control, not a concentration calibration curve.")
                cfg["conc_unit"] = st.text_input("Dose/concentration unit", cfg["conc_unit"])
                with st.expander("Advanced: dose-response fitting"):
                    cfg["method"] = st.selectbox("IC50 method", ["logistic", "interpolation", "linear"], index=["logistic", "interpolation", "linear"].index(cfg["method"]))
            elif key in ("acid_value", "peroxide"):
                cfg["normality"] = st.number_input("Default titrant strength (N)", min_value=0.000001, value=cfg["normality"], format="%.6f")
                st.caption("A normality entered in your file takes precedence.")
                if key == "acid_value":
                    acids = ["oleic", "palmitic", "lauric", "linoleic"]
                    cfg["fatty_acid"] = st.selectbox("Express free fatty acids as", acids, index=acids.index(cfg["fatty_acid"]))
            elif key == "minerals":
                st.write("Each element uses its own standard readings from the data file. Instrument-reported concentrations and final mg/kg results can also be entered directly.")
                cfg["min_r2"] = st.number_input("Warn if element standard-curve R² is below", min_value=0.0, max_value=1.0, value=cfg["min_r2"], step=0.001, format="%.3f")
            elif key in ("phytate", "oxalate"):
                with st.expander("Preparation factors from your laboratory protocol"):
                    cfg["mg_per_ml"] = st.number_input("Conversion factor (mg per mL of titrant)", min_value=0.000001, value=cfg["mg_per_ml"], format="%.6f")
                    if key == "phytate":
                        cfg["aliquot_factor"] = st.number_input("Aliquot factor", min_value=0.000001, value=cfg["aliquot_factor"])
                    st.caption("Confirm these with your laboratory method. Do not apply an extraction correction twice.")
            else:
                st.write("No shared calibration setting is needed. Enter masses, element standards, detection limits or observations with your data.")
            if key != "screening" and comparison["mode"] != "Off":
                st.subheader("Result comparison")
                measurements = ["Result"] + (["IC50"] if key == "dpph" else ["FFA"] if key == "acid_value" else [])
                comparison["measurement"] = st.selectbox("Measurement to check", measurements, index=measurements.index(comparison["measurement"]))
                if comparison["mode"] == "Reference sample":
                    comparison["reference"] = st.text_input("Reference sample name", comparison["reference"], help="Must match a measured sample, such as Ascorbic acid. A calibration standard row is not a measured reference sample.")
                    directions = ["Higher is the target", "Lower is the target"]
                    comparison["direction"] = st.selectbox("When comparing with the reference", directions, index=directions.index(comparison["direction"]))
                else:
                    left, right = st.columns(2)
                    comparison["lower"] = left.number_input("Target range: lower value", value=float(comparison["lower"]))
                    comparison["upper"] = right.number_input("Target range: upper value", value=float(comparison["upper"]))
                    comparison["unit"] = st.text_input("Target range unit (must match the result)", comparison["unit"], help="The exact unit is shown on the result page. IC50 uses the dose unit; FFA uses % (as oleic), or the fatty acid selected above.")
                    if key == "minerals":
                        comparison["element"] = st.text_input("Element symbol for the target range", comparison["element"], help="A target range applies only to this element.")
                comparison["source"] = st.text_input("Where does this reference or range come from?", comparison["source"], help="Record a laboratory SOP, study control or a relevant standard. No universal cutoff is assumed.")
            if st.form_submit_button("Save assay settings", type="primary"):
                error = None
                if key in CURVE_ASSAYS and (not cfg["standard"].strip() or not cfg["abbrev"].strip()):
                    error = "Enter a calibration standard and equivalent label."
                elif comparison["mode"] == "Target range" and (comparison["lower"] > comparison["upper"] or not comparison["unit"].strip()):
                    error = "Enter a matching unit and a lower value no greater than the upper value."
                elif comparison["mode"] == "Target range" and key == "minerals" and not comparison["element"].strip():
                    error = "Enter the element symbol for this mineral range."
                elif comparison["mode"] == "Reference sample" and not comparison["reference"].strip():
                    error = "Enter the reference sample name."
                if error:
                    st.error(error)
                else:
                    prefs["assays"][key] = cfg
                    st.success("Assay settings saved. Return to the assay page to review the results.")


def show_guidance(key):
    guide = guide_for(key)
    st.write(guide["purpose"])
    with st.expander("How do I get these readings?"):
        for number, step in enumerate(guide["steps"], 1):
            st.markdown(f"**{number}.** {step}")
        st.caption("Use your laboratory's full protocol for reagent preparation and handling. This checklist explains the observations to record.")
    st.subheader("1 · Values you need")
    st.dataframe(pd.DataFrame([{"Value": FIELDS[field][0], "Column in your file": field, "What to enter": FIELDS[field][1]}
                               for field in guide["fields"] if field in FIELDS]), hide_index=True, use_container_width=True)
    st.caption("One row = one measurement. Keep repeats separate; the analyzer calculates their average.")


def show_inputs(key):
    st.subheader("2 · Add your readings")
    template = TEMPLATES / f"{key}_template.csv"
    st.download_button("Download a data-entry template", template.read_bytes() if template.exists() else b"sample_id,replicate\n", f"{key}_template.csv", "text/csv", key=f"tpl_{key}")
    st.caption("The download contains example rows. Replace them with your own measurements before uploading.")
    if use_demo:
        st.info("The supplied example uses calculated observations, not bench readings. Use Calculated results to review it." if example == "Supplied results tables" else "Practice mode: simulated readings are loaded. Turn off Use example data to enter your own measurements.")
        return
    choice = st.radio("How would you like to add data?", ["Upload a file", "Enter readings here"], horizontal=True, key=f"entry_{key}")
    if choice == "Upload a file":
        st.file_uploader("Choose a CSV or Excel (.xlsx) file", type=["csv", "xlsx"], key=f"up_{key}", on_change=store_upload, args=(key,))
    else:
        saved = st.session_state.get("datasets", {}).get(key)
        blank = pd.read_csv(template, nrows=0) if template.exists() else pd.DataFrame(columns=["sample_id", "replicate"])
        with st.form(f"manual_{key}"):
            columns = saved.columns if saved is not None else blank.columns
            labels = {name: st.column_config.Column(FIELDS[name][0], help=FIELDS[name][1]) for name in columns if name in FIELDS}
            edited = st.data_editor(saved if saved is not None else blank, num_rows="dynamic", hide_index=True,
                                    use_container_width=True, column_config=labels, key=f"editor_{key}")
            st.caption("Add rows using the + row control. Use the column guide above; leave optional values blank.")
            if st.form_submit_button("Analyze these readings", type="primary"):
                st.session_state.setdefault("datasets", {})[key] = edited.copy()
                st.session_state.setdefault("sources", {})[key] = "Manual entry"
                st.session_state.setdefault("import_errors", {}).pop(key, None)
    if key in st.session_state.get("datasets", {}):
        st.caption("Loaded: " + st.session_state.get("sources", {}).get(key, "Manual entry"))
        st.button("Clear these readings", key=f"remove_{key}", on_click=remove_dataset, args=(key,))


def show_checks(result):
    checks = result.extra.get("assessment", pd.DataFrame())
    if result.extra.get("assessment_error"):
        st.warning("Comparison needs a settings change: " + result.extra["assessment_error"])
    elif checks.empty:
        if result.unit != "observation":
            st.info("Want to compare with a standard? Open Settings → Assay methods & comparisons and choose a measured reference or a target range.")
    if not checks.empty:
        st.markdown("**Reference and target checks**")
        display = checks.drop(columns=[name for name in ("Element", "Concentration") if checks[name].isna().all() or checks[name].eq("").all()])
        def flag_style(flag):
            color = "#dcfce7" if flag in ("Within target", "Meets reference") else "#dbeafe" if flag == "Reference" else "#fef3c7"
            return f"background-color: {color}; color: #172033; font-weight: 600"
        st.dataframe(display.style.map(flag_style, subset=["Flag"]), hide_index=True, use_container_width=True)
        st.caption("Flags compare averages with your chosen reference or range. They do not establish statistical significance, safety or suitability.")


def show_assay(key):
    show_guidance(key)
    show_inputs(key)
    raw, result = analyse(key)
    if isinstance(result, AssayInputError):
        st.error("Check your readings: " + str(result))
        return
    if result is None:
        imported, error = calculated_results()
        matches = [item for item in imported if item.extra["assay_key"] == key]
        if error:
            st.warning(error)
        if matches:
            st.info("These results were supplied already calculated. No absorbance or calibration readings were invented.")
            result, raw = matches[0], matches[0].rows
    if result is None:
        st.info("Add readings above to see calculated results here.")
        return
    st.subheader("3 · Understand your results")
    checks = result.extra.get("assessment", pd.DataFrame())
    attention = len(checks[~checks["Flag"].isin(["Within target", "Meets reference", "Reference"])]) if not checks.empty else 0
    a, b, c = st.columns(3)
    a.metric("Samples", result.summary["sample_id"].nunique())
    b.metric("Data warnings", len(result.warnings))
    configured = result.extra.get("assessment_config", {}).get("mode", "Off") != "Off"
    c.metric("Comparison flags", "Needs setup" if result.extra.get("assessment_error") else attention if configured else "Not set")
    st.write(guide_for(key)["meaning"])
    st.caption("Result unit: " + result.unit)
    st.dataframe(overview([result], prefs["err"]), use_container_width=True, hide_index=True)
    show_checks(result)
    if result.warnings:
        st.warning(f"{len(result.warnings)} data or method checks need attention. Review them before using these results.")
        with st.expander("What should I check?"):
            for warning in result.warnings:
                st.write("• " + warning)
    else:
        st.success("No automatic data warnings were found. Check the method and reference before drawing a conclusion.")
    with st.expander("Charts", expanded=True):
        for figure in figures_for(result, prefs["err"]).values():
            st.pyplot(figure, use_container_width=True)
            plt.close(figure)
    with st.expander("Details: readings, repeat statistics and calculations"):
        st.markdown("**Original readings**")
        st.dataframe(raw, use_container_width=True, hide_index=True)
        st.markdown("**Repeat statistics**")
        st.dataframe(result.summary.round(4), use_container_width=True, hide_index=True)
        st.markdown("**Calculated rows**")
        st.dataframe(result.rows.round(4), use_container_width=True, hide_index=True)
        if key == "dpph" and not result.extra["ic50"].empty:
            st.markdown("**IC50 estimates by fitting method**")
            st.dataframe(result.extra["method_comparison"].round(3), use_container_width=True, hide_index=True)
    st.download_button("Download this assay's report", to_excel([result], prefs["err"]), f"{key}_report.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key=f"report_{key}")


def show_calculated_page():
    st.title("Calculated results")
    st.write("Already have concentrations, percentage inhibition or other calculated values? Use them directly—absorbance readings are not required.")
    if use_demo and example == "Supplied results tables":
        st.info("Loaded: 76 observations transcribed from cotton-result-only.pdf. The study owner confirmed A/B/C and cotton 1/2/3 are repeat measurements.")
        st.checkbox("Combine the confirmed repeat measurements", value=True, key="example_repeats")
        st.download_button("Download the supplied results as CSV", RESULTS_EXAMPLE.read_bytes(), "provided_results.csv", "text/csv")
        if st.button("Compare DPPH and FRAP with the supplied ascorbic acid reference"):
            for key in ("dpph", "frap"):
                prefs["assays"][key]["comparison"].update(mode="Reference sample", measurement="Result",
                    reference="Ascorbic acid", direction="Higher is the target", source="Measured reference series in cotton-result-only.pdf")
            st.success("Reference comparisons enabled at matching concentrations. Change them in Settings at any time.")
    elif use_demo:
        st.info("Select Supplied results tables in the sidebar to inspect the results-only example, or turn off demo data to upload your own results.")
    else:
        st.file_uploader("Upload calculated results (.csv or .xlsx)", type=["csv", "xlsx"], key="results_upload", on_change=store_results_upload)
        st.checkbox("group_id labels confirmed repeats of the same material", value=False, key="uploaded_result_repeats")
    with st.expander("How should a results table be arranged?"):
        st.write("One row per calculated observation. Required columns: assay, sample_id, value, unit. Optional: replicate, group_id, concentration, concentration_unit, element, status, source_page and note.")
        st.write("Use group_id only to identify confirmed repeat groups. Different concentrations are different conditions, not repeats. For a non-detect, use status=nd and leave value empty. Numeric zero stays zero.")
        st.write("This path accepts CSV/XLSX. The supplied PDF was checked visually and transcribed; arbitrary PDFs are not automatically parsed.")
    results, error = calculated_results()
    if error:
        st.error(error)
        return
    if not results:
        return
    a, b, c = st.columns(3)
    a.metric("Calculated observations", sum(len(result.rows) for result in results))
    b.metric("Measurements", len(results))
    c.metric("Raw absorbance required", "No")
    st.dataframe(overview(results, prefs["err"]), hide_index=True, use_container_width=True)
    st.caption("SEM is calculated only from confirmed repeats. Each supplied DPPH/FRAP concentration has one observation, so it has no repeat-based SEM. IC50 is a fitted estimate from a single series.")
    for result in results:
        with st.expander(result.assay + " · " + result.unit):
            st.dataframe(result.summary, hide_index=True, use_container_width=True)
            show_checks(result)
            for warning in result.warnings:
                st.write("• " + warning)
            st.markdown("**Source observations**")
            st.dataframe(result.rows, hide_index=True, use_container_width=True)
    st.download_button("Download calculated-results report", to_excel(results, prefs["err"]), "calculated_results_report.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", type="primary")


if page == "Settings":
    show_settings()
elif page == "Calculated results":
    show_calculated_page()
elif page == "Overview & report":
    st.title(prefs["study_name"] or "Your assay dashboard")
    st.write("Choose an assay, add the readings from your experiment, then review results and suggested checks.")
    if use_demo:
        st.info("Supplied results example · Verified transcription of calculated observations from cotton-result-only.pdf." if example == "Supplied results tables" else "Practice mode · All loaded readings are simulated, not real study results.")
    results, calculated_error = calculated_results()
    failed = [calculated_error] if calculated_error else []
    for key in ASSAYS:
        _, result = analyse(key)
        if isinstance(result, AssayInputError):
            failed.append(f"{ASSAYS[key].title}: {result}")
        elif result is not None:
            results.append(result)
    a, b, c = st.columns(3)
    a.metric("Assays with results", len(results))
    b.metric("Samples", len({sample for result in results for sample in result.summary["sample_id"]}))
    c.metric("Data warnings", sum(len(result.warnings) for result in results) + len(failed))
    with st.expander("Start here", expanded=not results):
        st.markdown("**1. Set up:** use Settings for calibration, repeat checks and comparison targets.\n\n**2. Add data:** choose a section on the left. Each assay explains the values to enter and how to measure them.\n\n**3. Review:** inspect result flags and warnings, then download your report.")
    for failure in failed:
        st.error(failure)
    if results:
        st.subheader("Results at a glance")
        st.dataframe(overview(results, prefs["err"]), use_container_width=True, hide_index=True)
        st.caption(f"Numeric results show mean ± {prefs['err'].upper()}. ND = not detected. Open an assay for the full explanation and calculations.")
        for result in results:
            if not result.extra.get("assessment", pd.DataFrame()).empty or result.extra.get("assessment_error"):
                with st.expander(result.assay + " · comparison checks"):
                    show_checks(result)
        st.download_button("Download all results", to_excel(results, prefs["err"]), "assay_report.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", type="primary")
    else:
        st.info("Your dashboard is ready. Choose an assay section to add your first readings.")
else:
    st.title(page)
    st.caption("Follow the three steps for each assay. Calibration and comparison options live on Settings.")
    keys = [key for key, assay in ASSAYS.items() if assay.group == page]
    for tab, key in zip(st.tabs([ASSAYS[key].title for key in keys]), keys):
        with tab:
            show_assay(key)
