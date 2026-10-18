# Thesis alignment audit

This records the original review. Subsequent implementation follows a general-purpose analyzer scope, as clarified by the user, rather than the cottonseed-specific profile and table proposals below. See `extending-assays.md` for the current behavior and extension API.

Reviewed 18 October 2026 against `../project/Blessed-Oigbochie-approved.pdf`, Chapter 3 (printed pp. 63-81) and Chapter 4 (pp. 82-89).

The calculation library already covers the twelve quantitative assays. The main unfinished work is connecting those calculations to the actual study: its sample design, published results, reporting layout, and unresolved method/report discrepancies. No application code was changed during this audit.

## Chapter coverage

| Thesis section | Existing implementation | Gap |
| --- | --- | --- |
| 3.2 Processing and extraction | Mass, extract volume and dilution fields | No study/sample record for source, matrix, extraction batch, solvent, storage or dry-weight versus extract basis |
| 3.3 Qualitative screening | None | Record Dragendorff, alkaline reagent, ferric chloride and froth observations, with present/absent/indeterminate status |
| 3.4.1 Phenolics | Standard curve, mg TAE/g | Chapter 4 presentation uses g TAE/kg; numerically equivalent, but report labels should support both |
| 3.4.2 Alkaloids | Residue/sample mass, percent | Covered; real raw-data validation still needed |
| 3.4.3 Flavonoids | Standard curve, mg QE/g | Retain extraction versus extract-mass basis and sample blank provenance |
| 3.4.4 Saponins | Gravimetric, g/kg through registry | Chapter 3 describes percent; Chapter 4 uses g/kg. Conversion is supported mathematically but not explained in reports |
| 3.4.5 Tannins | Standard curve, mg TAE/g | Explicit aliquot/reaction dilution conventions are missing |
| 3.5.1 DPPH | Single-concentration inhibition and optional IC50 | Thesis result is single-condition inhibition, whereas demo emphasizes concentration series and IC50 |
| 3.5.2 FRAP | Calibration, mg AAE/g | Chapter 4 instead reports percent; source gives no percentage calculation |
| 3.6 Phytate and oxalate | Printed formulas implemented | Extraction/aliquot conventions need explicit documentation and validation |
| 3.7 Oil quality | Acid value, derived FFA, blank-corrected peroxide | Covered; actual study has one extracted oil, demo introduces fresh-pressed and market oils |
| 3.8 Minerals | Per-element calibration or instrument mg/L, mg/kg, calculated LOD | No direct final mg/kg import or explicit instrument ND/LOD input; demo omits Ni |
| 3.9 Statistics | Mean, SD, SEM, CV, ANOVA, Tukey letters | Detailed comparisons discarded; Tukey is an implementation choice not specified in Chapter 3 |
| 4.1-4.6 Results tables | Generic long overview and per-assay sheets | Six study-specific tables, source reference values and reconciliation view missing |

## Priority 1: correctness and data retention

1. **IC50 interpolation can crash with noisy replicates.** `src/assaykit/dpph.py:189` checks for a raw reading reaching 50% before averaging by concentration. A raw reading can exceed 50% while all concentration means remain below it; `above[0]` then raises `IndexError`. Reproduced with concentrations `[10,10,20,20,40,40]` and inhibition `[10,20,20,30,45,51]`. Check the averaged response before selecting a crossing. Retain a structured not-reached result.

2. **Mineral input validation can produce infinite concentrations.** `src/assaykit/calibration.py:243` divides by sample mass without checking it is positive. Reproduced with Ca reading 1.788 mg/L, digest 100 mL and sample mass 0 g: `mg_per_kg=inf`, `detected=True`. Validate finite measurements, positive mass/volume/dilution and required readings before calibration or reporting. Apply equivalent bounds to curve-assay dilution/extract volumes.

3. **Missing sample IDs can disappear silently.** `src/assaykit/common.py:68` converts IDs without explicitly rejecting missing/empty IDs. A one-row peroxide input with `sample_id=None` returned an empty summary in this environment. Reject missing identifiers before conversion/grouping; reject ambiguous duplicate normalized column names and check replicate identifiers.

4. **Uploaded study data is tied to transient widgets.** `app/streamlit_app.py:46` reads uploader widget keys directly; uploaders are rendered only for the selected section. There is no independent persistent dataset store. Streamlit widget cleanup makes cross-section collection fragile, especially when navigating through several assay sections before Overview. This is a code-review finding; upload/navigation behavior was not exercised with real files. Copy parsed inputs into independent session data and add an upload/navigation integration check.

5. **File parsing escapes the app's error handler.** `analyse()` calls `load()` before its try block and catches only `AssayInputError`. Malformed CSV/Excel uploads can therefore raise uncaught parsing exceptions. Both app and CLI advertise `.xls`, but the declared dependencies contain openpyxl and no legacy `.xls` reader. Restrict supported formats or provide the appropriate reader, with useful import errors.

6. **Figure significance captions ignore the selected alpha.** `src/assaykit/plots.py:80` always prints `p < 0.05` even when the user selects 0.01 or 0.10. Carry the chosen alpha through result metadata, captions and exports.

## Priority 2: actual project alignment

### Preserve source results separately from raw observations

Add a curated Chapter 4 reference dataset with mean, SEM, unit, n, table, matrix and source status. This is a published-summary dataset, not reconstructed bench readings. Do not invent triplicates or absorbances from mean/SEM.

Useful acceptance anchors:

| Table | Reference values |
| --- | --- |
| 4.1 | Phenolics 82.35 ± 0.40 g TAE/kg; flavonoids 9.16 ± 1.23 g QE/kg; tannins 21.22 ± 1.78 g TAE/kg; saponins 9.45 ± 0.09 g/kg; alkaloids 6.67 ± 0.34% |
| 4.2 | Oxalate 0.44 ± 0.00 mg/g; phytate 2.12 ± 0.02% |
| 4.3 | TPC oil 4.94 ± 0.19 and seed 82.35 ± 0.40 g TAE/kg |
| 4.4 | DPPH seed 38.79 ± 3.41%, oil 51.39 ± 6.23%, reference 64.17 ± 7.89%; reported FRAP oil 35.18 ± 5.79%, reference 56.89 ± 8.79%; seed FRAP shown as a dash |
| 4.5 | Acid value 23.30 ± 3.02 mg KOH/g; FFA 11.72 ± 1.51%; peroxide 99.58 ± 0.80 meq/kg |
| 4.6 | Seed/oil respectively: Fe 33.3/ND; Zn 1.401/0.23; K 117.7/1.081; Ni 0.061/0.008; Pb ND/ND; Ca 178.8/0.98; Cu 0.085/ND; Cd ND/ND; Mn 0.133/0.08 mg/kg |

Tables 4.1-4.5 state mean ± SEM, n=3. Table 4.6 explicitly states single determinations, overriding the general triplicate statement for those results. A dash for seed FRAP should remain unavailable/not reported, not zero or ND. Oxalate SEM 0.00 is a rounded published value, not proof of zero variability.

### Resolve source discrepancies explicitly

- **FRAP:** retain the existing mg AAE/g calculation because it follows section 3.5.2. Store Chapter 4 percentages as reported with an unresolved-basis note. Obtain the original calculation sheet before implementing any percentage conversion. These units are not interchangeable.
- **Phytate:** the procedure extracts 4 g into 100 mL and titrates a 25 mL aliquot, but the printed equation omits an explicit aliquot factor. The code defaults to the printed equation and permits a global factor through Python. Record the chosen convention and establish whether the supplied sample mass represents the entire extraction or the titrated portion before applying another factor.
- **Oxalate:** the procedure describes 75 mL extraction, 25 mL aliquot and 0.1 N KMnO4; the printed equation is simply titre × 0.9004. Code follows that coefficient and adds mass normalization. Its physical derivation and aliquot/normality convention require confirmation from bench records; avoid silently changing it.
- **Calibration basis:** the curve docstring calls concentrations cuvette concentrations while conversion relies on a manually supplied dilution factor. Specify whether standard concentrations mean stock/extract concentration before reaction or final reaction-mixture concentration. Apply reaction dilution only when required by that convention, consistently for standards and samples.
- **Statistical letters:** Tables 4.1, 4.2 and 4.5 display comparisons across different measurements/units. The current code compares samples within an assay. Preserve that boundary for newly calculated statistics; do not reproduce cross-measurement significance letters as if the software independently validated them. Acid value and FFA are also deterministically linked, not independent measurements.

### Make the study the default workflow

Add a cottonseed study profile defining seed extract, oil extract, extracted oil and ascorbic acid reference, with eligible assays and expected replicate counts. Keep reference standards distinct from calibration levels. Provide report tables corresponding to Tables 4.1-4.6, including side-by-side seed/oil minerals and antioxidant results. Show missing assays without manufacturing observations. Retain the general analyzer underneath this profile.

Keep current synthetic data clearly labeled as a general demonstration. It uses different values/design, includes seed FRAP and two oil-quality groups, emphasizes IC50 and omits Ni. It should not serve as evidence of reproducing Chapter 4.

### Handle mineral ND as a first-class result

The current direct instrument-reading path does not accept an instrument LOD or ND flag. A positive reading below an instrument's actual LOD is treated as detected when no calculated LOD exists. Add element/batch LOD values with explicit units and provenance, a censoring status, and a final mg/kg import route for existing results. An unknown detection limit should remain unknown; ND must not require entering a fabricated zero. Preserve n=1 for the published mineral results and avoid SEM/inferential comparisons for them.

## Priority 3: reproducible outputs

- Retain `Comparison` objects returned by `summarize()` instead of discarding them in assay handlers. Export ANOVA F/p, group membership and Tukey pairwise p-values alongside letters.
- Export calibration slope/intercept/R², concentration units, blanks, LODs, dilution assumptions, alpha, error convention, application version and input provenance. Current workbook has calculation rows and a generic methods sheet, but not this complete run record.
- Include IC50 bounds/notes in the overview and plotted labels. The overview currently formats missing IC50 as a dash while bounds are available elsewhere; a downloadable summary should retain the actual reason.
- Distinguish technical replicates from independent biological samples/batches. Three repeat readings should not automatically imply three independent biological observations.
- Add tests for real-data import/navigation, ND input, missing data, invalid bounds, alpha captions and published-summary rendering. Use genuine raw notebook data for end-to-end numerical reconciliation when available. Preserve rounded source values separately from unrounded recalculations.

## Suggested implementation order

1. Fix reproduced numerical/input bugs and persist uploaded datasets across navigation.
2. Add a study profile and curated Chapter 4 summary reference, with unresolved source issues recorded.
3. Implement explicit mineral ND/LOD/final-result import and n=1 reporting.
4. Build the six study tables and a recalculated-versus-published comparison view.
5. Retain/export detailed statistics, calibration and run provenance.
6. Add the qualitative screening log. Keep IC50 as an optional extension.

## Verification performed

- Read the complete extracted Chapter 3 and Chapter 4 text, including methods, table notes and mineral sample-size exception. PDF page rendering was unavailable with the installed command-line tools; visual table layout was not independently checked.
- Read application, CLI, calculation, plotting, reporting, data generator, templates and tests.
- Existing test suite: **48 passed in 30.48 seconds**, using the existing virtual environment and disabling pytest's cache provider. A temporary-directory permission error appeared during interpreter shutdown after the successful test result.
- Additional read-only Python probes reproduced the IC50 interpolation IndexError, infinite mineral concentration from zero mass, and empty summary for a missing sample ID.
- No scientific formula changes made. No external standards review performed; this is a comparison with the supplied project and the implementation.
