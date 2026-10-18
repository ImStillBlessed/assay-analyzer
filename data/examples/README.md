# Supplied results-only example

`provided_results.csv` is a visually verified transcription of `project/cotton-result-only.pdf` (two pages), not simulated data. It contains 76 calculated observations across 13 measurements. This uses the same general long-format result input accepted for other materials and assays.

The study owner confirmed on 18 October 2026 that columns A/B/C and cotton 1/2/3 are repeat measurements. The bundled example therefore combines `group_id` values by default. For arbitrary uploaded result tables, grouping is off until the user confirms it.

## Transcription checks

- Page 1: alkaloid A is **6**, oxalate A is **0.445**, phytate A is **2.153**. Plain text extraction displaces these values; the rendered table was used to verify row assignments.
- The oil-phenolic C value is **5.299**. Its recalculated three-repeat mean is **4.959333…**, not a copied summary from the separate approved-thesis PDF.
- Page 2: FRAP reference values at 250, 200, 150, 100 and 50 µg/mL are **80.743, 69.170, 60.532, 40.221 and 33.775**. The rendered rows resolve the misplaced text-extraction order.
- The DPPH ascorbic-acid series is identical in the seed and oil tables. It is retained once, with a note identifying both tables; it is not counted as two independent reference series.
- The source prints tannin units as **g TEA/kg**. The dataset retains this label and marks the apparent typo for review instead of silently changing it to TAE.
- Mineral table zeros remain numeric **0**. This PDF has no detection-limit values or a definition proving that those zeros mean ND. Users can explicitly supply `status=nd` with an empty value for other result tables when the source establishes a non-detect.
- FRAP remains **% FRAP (reported)**. No unsupported conversion to mg AAE/g or invented calibration is made.
- Acid value, FFA and peroxide are separate supplied measurements. The app does not reconstruct titres or replace the provided FFA values with a recalculation.

## What can be calculated

Mean, SD, SEM and repeat CV are calculated for the confirmed triplicates. Samples are compared within a measurement/unit, never across different assay quantities. Each DPPH and FRAP concentration is a separate condition with one supplied value; those five conditions are not treated as n=5 replicates. Minerals are single determinations. IC50 can be estimated from a supplied DPPH series, but a single series does not provide replicate-based IC50 SEM. The seed series never reaches 50% inhibition by 250 µg/mL, so it is bounded above that tested dose, not reported as an invented exact value.

## General input columns

Required: `assay,sample_id,value,unit`.

Optional: `replicate,group_id,concentration,concentration_unit,element,status,source_page,source_table,note`.

Use the registered assay key where applicable, such as `tpc`, `frap`, `dpph`, `acid_value`, `peroxide` or `minerals`; other measurement names are also accepted as reported quantities. Use `ffa` for supplied free-fatty-acid results. Concentrations need a concentration unit. Results with different units are kept separate. The tool does not infer unit conversion from similar-looking labels.

Open **Calculated results** in the GUI. PDFs are not parsed automatically: this specific PDF was checked and converted into the reusable CSV schema. Upload equivalent CSV/XLSX files for another study.
