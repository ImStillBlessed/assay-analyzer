# Using the guided dashboard

Run `uv run streamlit run app/streamlit_app.py` from the project directory. The sidebar contains the dashboard, assay sections, Settings and a demo-data switch.

## Set up once

Open **Settings**. Under **Study & reporting**, name your study and choose the reporting spread and repeat-variation warning level. Statistical significance settings are in an advanced expander.

Under **Assay methods & comparisons**, choose one assay. Configure its standard, concentration unit, wavelength and curve-quality threshold, or its titration/other method settings where applicable. Actual blank and standard readings still belong with each experiment's data so calibration is traceable to that run. Save the settings before changing pages. Saved settings survive page navigation within the current session; they are not saved across server restarts or new sessions.

Demo measurements always use their built-in method settings. You can try result comparisons on the demo without relabeling its calibration.

## Add readings

Every assay page explains:

1. **Values you need:** the ordinary name, matching spreadsheet column and what to enter.
2. **Add your readings:** upload CSV/XLSX, or select **Enter readings here** and add rows in the table. Click **Analyze these readings** to use the entered values.
3. **Understand your results:** see units, averages, data-warning counts, comparison flags and what to check next.

Open **How do I get these readings?** for a measurement checklist. Use the laboratory's full protocol for reagent preparation and handling. For DPPH, enter measured sample and control absorbance, not a precomputed percentage. Keep repeat measurements in separate rows. When comparing a dose series, repeat IDs must match across doses.

Templates contain example rows; replace them with your measurements. Details and calculations are collapsed below the results. Readings remain available across sections until cleared or the session ends.

## Choose a meaningful comparison

In Settings, choose one of:

- **Off:** calculate results without claiming they meet a benchmark.
- **Reference sample:** enter the name of a measured reference in the same dataset and choose whether higher or lower is your target. Calibration rows are not treated as measured reference samples. DPPH comparisons match concentration; mineral comparisons match element. Missing references are flagged instead of compared across different conditions.
- **Target range:** enter inclusive lower and upper values and the exact result unit. Record where the range comes from. Mineral ranges apply only to the specified element. There is no automatic universal cutoff for arbitrary materials.

For example, compare DPPH inhibition with an ascorbic acid sample measured at the same concentration. The control absorbance used to calculate inhibition is a different input from the positive-reference sample used to compare performance. Single-dose inhibition uses `% inhibition`; IC50 uses the configured concentration unit and lower values represent a lower dose needed for 50% inhibition.

Flags describe the comparison of averages. They do not establish statistical significance or safety. ND and censored values cannot be treated as numeric zeros or marked as within a target range. Data-quality warnings are separate from comparison flags.

Download an individual assay report on its page, or a combined report from **Overview & report**. The workbook includes comparison flags, benchmark source and the selected comparison settings alongside the calculations and statistics.
