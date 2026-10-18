"""Plain-language input and measurement guidance for the supported calculations.

These are measurement checklists for an established laboratory protocol, not a
replacement for that protocol's reagent preparation and handling instructions.
"""

FIELDS = {
    "sample_id": ("Sample name", "A unique name for the material or treatment, such as Tea A."),
    "replicate": ("Repeat number", "Label repeat measurements 1, 2, 3. For a dose series, keep the same repeat number across doses."),
    "kind": ("Type of reading", "standard = known concentration; sample = your material; blank = reagent background."),
    "absorbance": ("Absorbance", "Copy the instrument reading. Absorbance has no unit; do not enter a percentage."),
    "abs_sample": ("Sample absorbance", "Reading for the sample mixed with DPPH, after the protocol's incubation."),
    "abs_control": ("Control absorbance", "Reading for DPPH plus the solvent, without your sample. It must be greater than zero."),
    "abs_blank": ("Sample-colour blank (optional)", "Reading for the same extract without the colour-producing reagent; use the protocol's blank."),
    "concentration": ("Sample concentration (optional)", "Dose tested. Use the unit in Settings. Needed only for a dose-response series."),
    "std_conc": ("Known standard concentration", "Fill this for standard rows. Use the selected calibration unit in Settings."),
    "sample_mass_g": ("Sample mass (g)", "Mass of material used, in grams; for example 1.00."),
    "extract_volume_ml": ("Extract volume (mL)", "Total extract volume, not just the volume placed in the cuvette."),
    "extract_mg_per_ml": ("Extract-stock strength (mg/mL)", "Alternative to sample mass plus extract volume when reporting per gram of extract."),
    "dilution_factor": ("Dilution factor (optional)", "Enter 10 for a tenfold dilution. Leave blank for 1; include each required correction only once."),
    "titre_ml": ("Titrant used (mL)", "Final burette reading minus initial reading: the volume delivered."),
    "blank_titre_ml": ("Blank titre (mL, optional)", "Volume used by the reagent-only blank, with no sample."),
    "normality": ("Titrant strength (N, optional)", "Actual standardized reagent strength. A value in the file overrides Settings."),
    "residue_g": ("Dry residue mass (g)", "Mass left after the method's drying step, excluding the container."),
    "container_g": ("Empty container mass (g)", "Use with container_residue_g instead of entering residue_g."),
    "container_residue_g": ("Container plus dry residue (g)", "The analyzer subtracts the empty container mass."),
    "element": ("Element symbol", "For example Ca, Fe or Zn. Each element is calibrated and compared separately."),
    "reading_mg_l": ("Instrument concentration (mg/L)", "Use this instead of absorbance if the AAS already reports concentration."),
    "std_conc_mg_l": ("Mineral standard concentration (mg/L)", "Known concentration for each element's standard rows."),
    "digest_volume_ml": ("Final digest volume (mL)", "Volume after digestion and dilution to the volumetric mark."),
    "result_mg_kg": ("Final mineral concentration (mg/kg)", "Use for an already calculated result; do not convert it again."),
    "lod_mg_l": ("Instrument detection limit (mg/L)", "Optional supplied limit on the instrument-reading basis."),
    "lod_mg_kg": ("Final detection limit (mg/kg)", "Optional limit on the same basis as the reported mineral result."),
    "detection_status": ("Detection status", "auto, detected, or nd (not detected). An ND observation does not need a made-up zero."),
    "test": ("Test name", "Name the observation test used by your laboratory."),
    "status": ("Observation result", "present, absent, or indeterminate."),
    "observation": ("What you saw (optional)", "Describe the colour, precipitate, foam or other observation."),
}

GUIDES = {
    "dpph": {
        "purpose": "Measures how much of the purple DPPH signal your sample removes. The result is percentage inhibition.",
        "fields": ["sample_id", "replicate", "abs_sample", "abs_control", "abs_blank", "concentration"],
        "steps": ["Prepare a sample reaction, a solvent control and any sample-colour blank using the same laboratory protocol.",
                  "Allow the reactions to develop for the time specified by that protocol. The built-in method uses 30 minutes in the dark.",
                  "Read sample and control absorbance at 518 nm for the built-in method. Record the actual numbers, not calculated percentages.",
                  "Repeat the measurements. Enter one row per reading; if testing several doses, include concentration and matching repeat numbers."],
        "meaning": "Higher inhibition means more scavenging under the same test conditions. Compare with a measured reference such as ascorbic acid at the same dose. IC50 is available only for a concentration series; lower IC50 means less material was needed to reach 50% inhibition.",
    },
    "screening": {
        "purpose": "Records what you observed in a qualitative test, without turning observations into invented concentrations.",
        "fields": ["sample_id", "replicate", "test", "status", "observation"],
        "steps": ["Choose the test in your laboratory protocol, such as a froth or ferric chloride test.",
                  "Run the sample and the protocol's controls, then record the observation.",
                  "Mark the result present, absent or indeterminate; include what you saw."],
        "meaning": "Presence is an observation, not a measure of amount. No numerical pass/fail or ANOVA is calculated.",
    },
    "minerals": {
        "purpose": "Converts element-specific AAS measurements into mineral concentration in mg/kg, or records already calculated results.",
        "fields": ["sample_id", "replicate", "kind", "element", "absorbance", "std_conc_mg_l", "reading_mg_l", "sample_mass_g", "digest_volume_ml", "result_mg_kg", "detection_status", "lod_mg_kg"],
        "steps": ["Use the laboratory's digestion and AAS protocol, recording the sample mass and final digest volume.",
                  "Measure each element's blanks and known standards before measuring the samples.",
                  "Enter absorbance with standards, or the instrument's mg/L reading. Alternatively, enter a final result_mg_kg without converting it again.",
                  "Record a supplied detection limit when available. Use detection_status=nd for an instrument-reported non-detect."],
        "meaning": "ND means not detected, not zero. A single measurement has no standard error. Compare the same element and unit; there is no universal acceptable range for every material.",
    },
}

for key, title, wavelength, chemistry in [
    ("tpc", "phenolic content", 765, "Folin-Ciocalteu"),
    ("flavonoids", "flavonoid content", 415, "aluminium chloride"),
    ("tannins", "tannin content", 760, "Folin-Denis"),
    ("frap", "ferric reducing power", 593, "FRAP"),
]:
    GUIDES[key] = {
        "purpose": f"Estimates {title} by comparing your sample's colour signal with known reference concentrations.",
        "fields": ["sample_id", "replicate", "kind", "absorbance", "std_conc", "sample_mass_g", "extract_volume_ml", "extract_mg_per_ml", "dilution_factor", "abs_blank"],
        "steps": [f"Prepare blanks, at least three different standard concentrations and your samples using the laboratory's {chemistry} protocol.",
                  "Keep reagent volumes, development time and measurement conditions consistent between standards and samples.",
                  f"Read absorbance at {wavelength} nm for the built-in method (or your configured wavelength). Record each reading and each standard's known concentration.",
                  "Record extraction mass, volume and dilution so concentration can be expressed per gram. Repeat the sample readings."],
        "meaning": "The standard curve converts absorbance into concentration; it is not an acceptable-result threshold. Results are expressed as equivalents of the selected reference. FRAP is calibrated reducing power, not percentage inhibition.",
    }

for key, purpose in [("alkaloids", "Estimates alkaloid residue as a percentage of the starting sample mass."),
                     ("saponins", "Estimates saponin residue in grams per kilogram of starting material.")]:
    GUIDES[key] = {
        "purpose": purpose,
        "fields": ["sample_id", "replicate", "sample_mass_g", "residue_g", "container_g", "container_residue_g"],
        "steps": ["Follow the extraction, separation and drying steps in your laboratory's method.",
                  "Weigh the starting sample and the empty receiving container.",
                  "Weigh the container plus the dried residue. Enter those two masses, or enter the residue mass alone.",
                  "Record each repeat separately, in grams."],
        "meaning": "The analyzer calculates residue mass divided by starting mass. Compare only results obtained with a matching preparation method and unit.",
    }

for key, purpose, reagent in [
    ("acid_value", "Measures acid value and calculates free fatty acids from the same titration.", "KOH"),
    ("peroxide", "Measures peroxide value, an indicator of primary oil oxidation.", "sodium thiosulfate"),
    ("phytate", "Estimates phytic acid content using the selected titration factor.", "iron(III) chloride"),
    ("oxalate", "Estimates oxalate content using the selected titration factor.", "potassium permanganate"),
]:
    GUIDES[key] = {
        "purpose": purpose,
        "fields": ["sample_id", "replicate", "sample_mass_g", "titre_ml", "blank_titre_ml"] + (["normality"] if key in ("acid_value", "peroxide") else []),
        "steps": ["Weigh your sample and prepare it using the laboratory's approved method.",
                  f"Record the starting burette reading. Titrate with the method's {reagent} to its specified endpoint.",
                  "Subtract starting from final burette reading to find the volume delivered in mL. Measure the blank where required.",
                  "Enter each repeat, the sample mass, and any reagent-strength information. Confirm preparation factors in Settings."],
        "meaning": "A result above a configured upper limit is flagged for review. The suitable limit depends on the material and method. A flag alone does not establish safety or suitability.",
    }


def guide_for(key: str) -> dict:
    return GUIDES.get(key, {"purpose": "Analyze measurements using your laboratory's assay protocol.",
                            "fields": ["sample_id", "replicate"],
                            "steps": ["Follow the registered assay's protocol and enter one row per measurement."],
                            "meaning": "Interpret results using a reference appropriate to the method and material."})
