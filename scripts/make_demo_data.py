"""Generate the synthetic demo dataset and the blank templates.

The demo data is NOT real thesis data. It follows the design of a cottonseed study
(seed extract, oil extract, ascorbic acid as reference; two pressed-oil samples) and is
simulated from chosen "true" values with realistic bench noise, so the right answers are
known in advance and tests can check that the analysis recovers them (TRUE below).

Run from the repo root:  python scripts/make_demo_data.py
"""

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DEMO, TEMPLATES = ROOT / "data" / "demo", ROOT / "templates"
rng = np.random.default_rng(2026)

SEED, OIL, ASC = "Cottonseed extract", "Cottonseed oil extract", "Ascorbic acid"
FRESH, MARKET = "Fresh-pressed oil", "Market oil"

TRUE = {
    # curve assays, mg standard-equivalent per g
    "tpc": {SEED: 70.0, OIL: 4.0},
    "flavonoids": {SEED: 8.0},
    "tannins": {SEED: 18.0},
    "frap": {SEED: 25.0, OIL: 12.0},
    # gravimetric
    "alkaloids": {SEED: 5.5},          # %
    "saponins": {SEED: 11.0},          # g/kg
    # titration
    "phytate": {SEED: 2.4},            # %
    "oxalate": {SEED: 0.50},           # mg/g
    "acid_value": {FRESH: 6.0, MARKET: 18.0},   # mg KOH/g
    "peroxide": {FRESH: 12.0, MARKET: 45.0},    # meq O2/kg
    # DPPH IC50, µg/mL
    "dpph_ic50": {SEED: 180.0, OIL: 260.0, ASC: 12.0},
    # minerals, mg/kg (None = absent)
    "minerals": {
        "Ca": {SEED: 1600, OIL: 12}, "K": {SEED: 8500, OIL: 9}, "Fe": {SEED: 60, OIL: 2.5},
        "Zn": {SEED: 35, OIL: 0.9}, "Mn": {SEED: 14, OIL: 0.3}, "Cu": {SEED: 6, OIL: None},
        "Pb": {SEED: None, OIL: None}, "Cd": {SEED: None, OIL: None},
    },
}
REPS = (1, 2, 3)


def noisy(x, rel=0.03):
    return x * rng.normal(1, rel)


def curve_assay(key, slope, levels, dilution, blank=0.04):
    """Standards, a reagent blank, and samples extracted as 1 g in 10 mL."""
    out = [["blank", "Reagent blank", r, round(blank + rng.normal(0, 0.002), 3), None, None, None, None] for r in (1, 2)]
    for c in levels:
        for r in (1, 2):
            out.append(["standard", "Standard", r, round(slope * c + blank + rng.normal(0, 0.006), 3), c, None, None, None])
    for sample, value in TRUE[key].items():
        dil = dilution[sample]
        for r in REPS:
            mass = round(noisy(1.0, 0.01), 4)
            cuvette = noisy(value) * mass * 1000 / 10 / dil  # mg/g → µg/mL in the cuvette
            out.append(["sample", sample, r, round(slope * cuvette + blank + rng.normal(0, 0.004), 3), None, dil, mass, 10])
    return pd.DataFrame(out, columns=["kind", "sample_id", "replicate", "absorbance", "std_conc", "dilution_factor",
                                      "sample_mass_g", "extract_volume_ml"])


def dpph():
    out = []
    series = {SEED: ([25, 50, 100, 200, 400, 800], 92, 1.3, 0.00008),
              OIL: ([25, 50, 100, 200, 400, 800], 88, 1.2, 0.00003),
              ASC: ([2.5, 5, 10, 20, 40, 80], 96, 1.6, 0.0)}
    for sample, (concs, top, hill, colour) in series.items():
        ic50 = TRUE["dpph_ic50"][sample]
        mid = ic50 * (top / 50 - 1) ** (1 / hill)
        for r in REPS:
            a0 = rng.normal(0.900, 0.008)
            for c in concs:
                inh = top / (1 + (mid / c) ** hill)
                own = colour * c
                a1 = a0 * (1 - inh / 100) + own + rng.normal(0, 0.008)
                out.append([sample, r, c, round(a1, 3), round(a0, 3), round(own + abs(rng.normal(0, 0.002)), 3)])
    return pd.DataFrame(out, columns=["sample_id", "replicate", "concentration", "abs_sample", "abs_control", "abs_blank"])


def gravimetric(key, mass, to_fraction):
    out = []
    for sample, value in TRUE[key].items():
        for r in REPS:
            m = round(noisy(mass, 0.005), 4)
            container = round(rng.uniform(28, 42), 4)
            residue = noisy(value) * to_fraction * m
            out.append([sample, r, m, container, round(container + residue, 4)])
    return pd.DataFrame(out, columns=["sample_id", "replicate", "sample_mass_g", "container_g", "container_residue_g"])


def titration(key, mass, titre_from_value, normality=None, blank=0.0):
    out = []
    for sample, value in TRUE[key].items():
        for r in REPS:
            m = round(noisy(mass, 0.01), 3)
            row = [sample, r, m, round(titre_from_value(noisy(value), m) + blank, 2), blank]
            out.append(row + ([normality] if normality else []))
    cols = ["sample_id", "replicate", "sample_mass_g", "titre_ml", "blank_titre_ml"] + (["normality"] if normality else [])
    return pd.DataFrame(out, columns=cols)


def minerals():
    """1 g sample digested to 100 mL; Ca and K diluted 10× before reading."""
    levels = {"Ca": [1, 2, 4, 8, 12], "K": [2, 5, 10, 50, 100], "Fe": [0.1, 0.25, 0.5, 1, 2],
              "Zn": [0.05, 0.1, 0.25, 0.5, 1], "Mn": [0.02, 0.05, 0.1, 0.2, 0.4], "Cu": [0.02, 0.05, 0.1, 0.2, 0.4],
              "Pb": [0.05, 0.1, 0.2, 0.5, 1], "Cd": [0.01, 0.02, 0.05, 0.1, 0.2]}
    slopes = {"Ca": 0.045, "K": 0.009, "Fe": 0.085, "Zn": 0.42, "Mn": 0.21, "Cu": 0.19, "Pb": 0.035, "Cd": 0.45}
    out = []
    for el, std_levels in levels.items():
        slope = slopes[el]
        for r in range(1, 8):  # 7 reagent blanks per element for a stable detection limit
            out.append(["blank", el, "Reagent blank", r, round(0.002 + rng.normal(0, 0.0008), 4), None, None, None, None])
        for c in std_levels:
            out.append(["standard", el, "Standard", 1, round(slope * c + 0.002 + rng.normal(0, 0.0015), 4), c, None, None, None])
        for sample, value in TRUE["minerals"][el].items():
            for r in REPS:
                mass = round(noisy(1.0, 0.005), 4)
                dil = 10 if el in ("Ca", "K") and sample == SEED else 1
                digest = (noisy(value) * mass / 100) if value else 0.0
                a = slope * digest / dil + 0.002 + rng.normal(0, 0.0008)
                out.append(["sample", el, sample, r, round(a, 4), None, dil, 100, mass])
    return pd.DataFrame(out, columns=["kind", "element", "sample_id", "replicate", "absorbance", "std_conc_mg_l",
                                      "dilution_factor", "digest_volume_ml", "sample_mass_g"])


def main():
    DEMO.mkdir(parents=True, exist_ok=True)
    TEMPLATES.mkdir(parents=True, exist_ok=True)
    tables = {
        "tpc": curve_assay("tpc", 0.0021, [25, 50, 100, 200, 300, 400], {SEED: 20, OIL: 2}),
        "flavonoids": curve_assay("flavonoids", 0.0026, [25, 50, 100, 200, 300], {SEED: 4}),
        "tannins": curve_assay("tannins", 0.0031, [20, 50, 100, 200, 300], {SEED: 10}),
        "frap": curve_assay("frap", 0.0042, [10, 25, 50, 100, 150, 200], {SEED: 20, OIL: 10}),
        "alkaloids": gravimetric("alkaloids", 5.0, 1 / 100),
        "saponins": gravimetric("saponins", 5.0, 1 / 1000),
        # % = 8.24 × t × 100 / (1000 × W)  →  t = % × 1000 × W / 824
        "phytate": titration("phytate", 4.0, lambda v, w: v * 1000 * w / 824),
        # mg/g = t × 0.9004 / W
        "oxalate": titration("oxalate", 1.0, lambda v, w: v * w / 0.9004),
        # AV = V × N × 56.1 / W
        "acid_value": titration("acid_value", 5.0, lambda v, w: v * w / (0.1 * 56.1), normality=0.1),
        # PV = (Vs − Vb) × N × 1000 / W
        "peroxide": titration("peroxide", 5.0, lambda v, w: v * w / (0.01 * 1000), normality=0.01, blank=0.10),
        "dpph": dpph(),
        "minerals": minerals(),
    }
    for name, df in tables.items():
        df.to_csv(DEMO / f"{name}.csv", index=False)
        example = df.groupby("kind", sort=False).head(2) if "kind" in df.columns else df.head(4)
        example.to_csv(TEMPLATES / f"{name}_template.csv", index=False)
        print(f"wrote {name}: {len(df)} rows")


if __name__ == "__main__":
    main()
