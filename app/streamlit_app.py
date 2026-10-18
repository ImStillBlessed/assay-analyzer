"""Point-and-click front end for lab users.  Run:  streamlit run app/streamlit_app.py"""

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st

from assaykit import ASSAYS, AssayInputError
from assaykit.plots import figures_for
from assaykit.report import overview, to_excel

ROOT = Path(__file__).resolve().parents[1]
DEMO, TEMPLATES = ROOT / "data" / "demo", ROOT / "templates"
GROUPS = list(dict.fromkeys(a.group for a in ASSAYS.values()))

st.set_page_config(page_title="Assay Analyzer", page_icon="🧪", layout="wide")


def read_upload(upload) -> pd.DataFrame:
    return pd.read_excel(upload) if upload.name.lower().endswith((".xlsx", ".xls")) else pd.read_csv(upload)


with st.sidebar:
    st.title("🧪 Assay Analyzer")
    page = st.radio("Section", ["Overview & report"] + GROUPS)
    st.divider()
    use_demo = st.toggle("Use demo data", value=True, help="Synthetic data with known answers. "
                         "Turn off to upload your own files.")
    err = st.radio("Report ± as", ["sem", "sd"], format_func=str.upper, horizontal=True)
    alpha = st.select_slider("Significance level (α)", [0.01, 0.05, 0.10], value=0.05)
    cv_limit = st.number_input("Flag replicate CV above (%)", 1.0, 50.0, 10.0, 1.0)
    with st.expander("DPPH options"):
        method = st.selectbox("IC50 method", ["logistic", "interpolation", "linear"],
                              help="Used only when a sample has a dilution series.")
        conc_unit = st.text_input("Concentration unit", "µg/mL")
    with st.expander("Standard-curve options"):
        std_unit = st.selectbox("Standard concentrations entered in", ["µg/mL", "mg/mL"])

options = {"alpha": alpha, "cv_limit": cv_limit, "method": method, "conc_unit": conc_unit, "std_unit": std_unit}


def load(key: str) -> pd.DataFrame | None:
    if use_demo:
        return pd.read_csv(DEMO / f"{key}.csv")
    upload = st.session_state.get(f"up_{key}")
    return read_upload(upload) if upload is not None else None


def analyse(key: str):
    raw = load(key)
    if raw is None:
        return None, None
    try:
        return raw, ASSAYS[key].run(raw, **options)
    except AssayInputError as e:
        return raw, e


def show_assay(key: str):
    info = ASSAYS[key]
    st.markdown(f"**{info.method}**")
    c1, c2 = st.columns([4, 1])
    c1.caption(f"Columns: {info.columns}")
    c2.download_button("Template", (TEMPLATES / f"{key}_template.csv").read_bytes(), f"{key}_template.csv",
                       "text/csv", key=f"tpl_{key}")
    if not use_demo:
        st.file_uploader("Data file (.csv or .xlsx)", type=["csv", "xlsx", "xls"], key=f"up_{key}")
    raw, res = analyse(key)
    if raw is None:
        st.info("Upload a file, or switch on demo data in the sidebar.")
        return
    with st.expander("Raw data"):
        st.dataframe(raw, use_container_width=True, hide_index=True)
    if isinstance(res, AssayInputError):
        st.error(str(res))
        return
    for w in res.warnings:
        st.warning(w, icon="⚠️")
    st.subheader(f"Results ({res.unit})")
    st.dataframe(res.summary.round(4), use_container_width=True, hide_index=True)
    for fig in figures_for(res, err).values():
        st.pyplot(fig, use_container_width=True)
        plt.close(fig)
    if key == "dpph" and not res.extra["ic50"].empty:
        st.subheader("IC50 by three methods")
        st.caption("Pooled fit per sample. Linear regression through a sigmoidal curve can be far off; "
                   "say which method you used.")
        st.dataframe(res.extra["method_comparison"].round(2), use_container_width=True, hide_index=True)
    with st.expander("Per-measurement calculations"):
        st.dataframe(res.rows.round(4), use_container_width=True, hide_index=True)


if page == "Overview & report":
    st.title("Overview")
    st.caption("Phytochemicals, antioxidant activity, anti-nutrients, oil quality and minerals of a seed and its "
               "oil, from raw readings to a thesis-ready table. Calculations run locally; data never leaves this machine.")
    results, failed = [], []
    for key in ASSAYS:
        raw, res = analyse(key)
        if isinstance(res, AssayInputError):
            failed.append(f"{ASSAYS[key].title}: {res}")
        elif res is not None:
            results.append(res)
    for f in failed:
        st.error(f)
    if not results:
        st.info("No results yet. Add data in the sections on the left.")
    else:
        table = overview(results, err)
        st.dataframe(table, use_container_width=True, hide_index=True, height=min(38 * len(table) + 40, 900))
        st.caption(f"Mean ± {err.upper()}. Within each assay, samples sharing a superscript letter are not "
                   f"significantly different (one-way ANOVA, Tukey HSD, α = {alpha}).")
        st.download_button("Download Excel report", to_excel(results, err), "assay_report.xlsx",
                           "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", type="primary")
else:
    st.title(page)
    keys = [k for k, a in ASSAYS.items() if a.group == page]
    for tab, key in zip(st.tabs([ASSAYS[k].title for k in keys]), keys):
        with tab:
            show_assay(key)
