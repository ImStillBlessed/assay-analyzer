# Using the analyzer across studies

Sample IDs are arbitrary: use your own materials, treatments and controls. The analyzer does not enforce a cottonseed study design. Qualitative observations remain separate from numerical statistics. The bundled synthetic study demonstrates the calculations; it is not published experimental data.

## Registering assays

The UI and CLI consume the same `ASSAYS` registry. A standard-curve assay can reuse calibration, validation, statistics, plots and Excel export:

```python
from assaykit import CurveAssay, register_curve_assay

register_curve_assay(CurveAssay(
    key="custom_phenolics",
    name="Phenolics by lab SOP",
    standard="Gallic acid",
    abbrev="GAE",
    wavelength_nm=765,
    reference="Laboratory SOP identifier",
))
```

Register at application startup before calling the CLI or running the Streamlit script. To ship an assay by default, add its `AssayInfo` to `src/assaykit/assays.py`, a CSV template and, optionally, a labeled synthetic demo file. Missing demo files simply leave that assay unloaded. Include a meaningful independently calculated test case.

For a different calculation family, use `register_assay(AssayInfo(...))`. Its analysis function accepts a DataFrame and returns an `AssayResult` containing calculation rows, summary, units, warnings and optional metadata. Assay keys must be unique lowercase letters/digits/underscores. Existing built-ins cannot be overwritten accidentally.

Numerical summaries should contain `sample_id`, `n`, `mean`, `sd`, `sem` and `letters`. Use `stats.summarize` and retain its comparison object under `extra['comparisons']`. Set `extra['value_col']` and `extra['alpha']`; add specialized plots in `figures_for` when necessary. This is a Python extension API, not an automatic external-plugin loader.

The Streamlit **Settings** page allows changing the reference standard, equivalent label, wavelength and concentration unit for each built-in colorimetric assay. This records the calibration actually used; it does not establish that a different chemistry is valid. For other protocols, define a new assay specification. See `guided-dashboard.md` for measurement guidance, direct entry and descriptive reference/target checks.

## Calibration and preparation conventions

- Input standard concentrations describe the concentration basis used when preparing the calibration curve. Keep standard and sample reaction conditions consistent.
- `dilution_factor` is the total correction from that calibrated concentration basis back to the extract. It defaults to 1. Do not add reaction dilution again if already included in your calibration convention.
- For extraction-based results, supply `sample_mass_g` and `extract_volume_ml`. For results per gram of extract stock, supply `extract_mg_per_ml` instead. State whether the denominator is dry material or extracted solids in your study records.
- Numeric outputs retain their units: mg/g and g/kg have the same numerical magnitude, while percent and g/kg differ by a factor of ten.
- FRAP remains calibrated mg AAE/g. A percentage result requires a separately specified method and cannot be inferred from that unit.
- Phytate exposes `mg_per_ml` and `aliquot_factor` in Python; oxalate exposes `mg_per_ml`. Confirm normality, aliquot, extraction and mass conventions before applying a different protocol. No undocumented correction to the source coefficients is made.

## Mineral imports and detection limits

Every row needs `kind`, `element` and `sample_id`. Sample rows accept:

| Input | Required preparation information |
| --- | --- |
| `absorbance` | Per-element standards, `sample_mass_g`, `digest_volume_ml`; optional `dilution_factor` |
| `reading_mg_l` | `sample_mass_g`, `digest_volume_ml`; optional `dilution_factor` |
| `result_mg_kg` | Final concentration, no conversion factors needed |
| `detection_status=nd` | No invented concentration needed |

Optional `lod_mg_l` is on the instrument-reading basis before the dilution correction. Optional `lod_mg_kg` is on the final sample basis and takes precedence. With neither supplied, absorbance calibration uses 3 × SD(blank) / slope when at least two blanks exist. Unknown LODs stay unknown and generate warnings; they are not silently replaced with zero.

Automatic detection is evaluated on each element/sample group's mean concentration against its mean normalized LOD. Keep batches and independently prepared samples distinct in sample IDs. Numeric and explicit ND replicates in the same group are reported as **Censored**, with no mean/SEM/ANOVA; the calculation sheet retains the original rows. This avoids substituting zeros for censored observations. With one observation, n=1 and SEM remains unavailable.

Example CSV:

```csv
kind,element,sample_id,replicate,result_mg_kg,lod_mg_kg,detection_status
sample,Zn,Material A,1,0.23,0.1,auto
sample,Pb,Material A,1,,,nd
```

## Data and report traceability

CSV and XLSX are supported. Convert legacy XLS files to XLSX before import. Uploads persist across section navigation within the current session and can be removed individually. They are not a durable study database.

Workbooks include calculation rows, summaries, warnings, calibration parameters, ANOVA results, pairwise Tukey p-values, and run details including source filename, study label, analysis options, selected alpha, spread convention, package version and export time. IC50 replicate estimates and unresolved bounds/notes remain available. Descriptive-only or underpowered comparisons do not get invented inferential results.

Use real replicate measurements for inferential statistics. Published means and SEM values alone cannot reconstruct the original measurements or reliably reproduce their significance letters. Technical repeat measurements should not be presented as independent biological samples.
