"""
Run the full multi-site, multi-biome evaluation and aggregate with statistical rigor.

For each study area (deforestation/sites.py) and both dates (2016, 2024):
  patchify (stride 32) -> classify THREE ways and validate each vs Global Forest Watch:
    CNN        - EuroSAT model, no adaptation (baseline transfer)
    CNN+AdaBN  - same model, BatchNorm stats recomputed per target scene (domain adapt)
    NDVI       - NDVI-difference baseline with a per-scene Otsu forest threshold

Validation is reported at two GFW loss-fraction thresholds (>=25%, >=50%). Each
per-site F1 gets a 95% BLOCK-bootstrap CI (see bootstrap_f1) and across sites we
report mean +/- sample sd, a per-site "wins" tally, and Wilcoxon signed-rank tests.
With a handful of sites the across-site tests have little power; we report them anyway.

Run:  python -m deforestation.run_all_sites
      python -m deforestation.run_all_sites --rescore   # reuse existing masks, re-score only
"""
import argparse
import json
from pathlib import Path
from statistics import mean, stdev

import numpy as np

from deforestation import patchify, classify_patches, change_detection, ndvi_baseline
from deforestation.validate_gfw import align_and_score, build_reference
from deforestation.sites import SITES, gfc_url

try:
    from scipy.stats import wilcoxon
except Exception:  # scipy always present (sklearn dep), but stay defensive
    wilcoxon = None

SITES_DIR = Path(r"C:\Users\josha\ml-data\deforestation\sites")
WORK = Path(r"C:\Users\josha\ml-data\deforestation\multi")
WORK.mkdir(parents=True, exist_ok=True)
FRACS = [0.25, 0.50]           # GFW loss-fraction thresholds to report
HEADLINE = 0.25                # threshold used for the summary table / tests
N_BOOT = 1000
BOOT_SEED = 42

STRIDE = 32                    # cell spacing for every detector in this study

# Patches are PATCH px wide but stepped STRIDE px, so each ground pixel falls in up
# to BLOCK x BLOCK cells. Cells are therefore NOT independent samples, and an i.i.d.
# bootstrap over them understates the CI (we measured ~1.9x too narrow at Tshopo).
# Resampling BLOCK x BLOCK tiles of cells restores the independent unit.
BLOCK = patchify.PATCH // STRIDE   # == 2 for the 64px/32px grid used throughout

# The CNN and NDVI detectors must land on the SAME cell grid: we build one GFW
# reference per site (from the CNN mask) and score all three detectors against it,
# which is only valid if their grids coincide. ndvi_baseline hardcodes its own
# PATCH/STRIDE, so pin them together here rather than let them drift apart silently.
assert (ndvi_baseline.PATCH, ndvi_baseline.STRIDE) == (patchify.PATCH, STRIDE), (
    f"NDVI grid ({ndvi_baseline.PATCH}px/{ndvi_baseline.STRIDE}px) does not match the CNN "
    f"grid ({patchify.PATCH}px/{STRIDE}px); the shared GFW reference would be invalid.")


def bootstrap_f1(change, ref, n=N_BOOT, seed=BOOT_SEED, block=BLOCK):
    """95% bootstrap CI on F1, resampling spatially disjoint BLOCKxBLOCK cell tiles.

    tp/fp/fn are additive over disjoint tiles, so we precompute each tile's counts
    and bootstrap over the tiles -- equivalent to resampling their cells together,
    which is what respecting the overlap requires. block=1 reduces to the naive
    (over-confident) i.i.d. cell bootstrap.
    """
    ch = np.asarray(change, dtype=bool)
    rf = np.asarray(ref, dtype=bool)
    if ch.size == 0:
        return (0.0, 0.0)
    R, C = ch.shape

    tps, fps, fns = [], [], []
    for r0 in range(0, R, block):
        for c0 in range(0, C, block):
            c_t = ch[r0:r0 + block, c0:c0 + block]
            r_t = rf[r0:r0 + block, c0:c0 + block]
            tps.append(np.count_nonzero(c_t & r_t))
            fps.append(np.count_nonzero(c_t & ~r_t))
            fns.append(np.count_nonzero(~c_t & r_t))
    tps = np.array(tps); fps = np.array(fps); fns = np.array(fns)

    rng = np.random.default_rng(seed)
    B = len(tps)
    idx = rng.integers(0, B, size=(n, B))
    tp = tps[idx].sum(1).astype(float)
    fp = fps[idx].sum(1).astype(float)
    fn = fns[idx].sum(1).astype(float)
    with np.errstate(invalid="ignore", divide="ignore"):
        p = np.where(tp + fp > 0, tp / (tp + fp), 0.0)
        r = np.where(tp + fn > 0, tp / (tp + fn), 0.0)
        f1s = np.where(p + r > 0, 2 * p * r / (p + r), 0.0)
    return (round(float(np.percentile(f1s, 2.5)), 4),
            round(float(np.percentile(f1s, 97.5)), 4))


def _score(mask_npz, key, refs):
    """Validate a change mask at all FRACS; attach a block-bootstrap F1 CI at HEADLINE.

    `refs` maps frac -> precomputed GFW reference grid for this site (built once and
    shared across detectors, since it depends only on the cell grid).
    """
    out = {}
    for frac in FRACS:
        res, change, ref = align_and_score(mask_npz, gfc_url(key), 2016, 2024,
                                           min_loss_frac=frac, return_masks=True,
                                           ref=refs[frac], verbose=False)
        if frac == HEADLINE:
            res["f1_ci95"] = bootstrap_f1(change, ref)
        out[f"{frac:.2f}"] = res
    return out


def run_site(key, rescore=False):
    if SITES[key].get("exclude"):
        print(f"[skip] {key}: excluded (see sites.py)"); return None
    a_tif = SITES_DIR / f"{key}_2016.tif"
    b_tif = SITES_DIR / f"{key}_2024.tif"
    if not (a_tif.exists() and b_tif.exists()):
        print(f"[skip] {key}: scenes missing"); return None

    masks = {m: WORK / f"{key}_{m}_mask.npz" for m in ("cnn", "adabn", "ndvi")}

    if rescore and all(p.exists() for p in masks.values()):
        print(f"[rescore] {key}: reusing existing masks")
    else:
        pa, pb = WORK / f"{key}_pA.npz", WORK / f"{key}_pB.npz"
        patchify.patchify(str(a_tif), str(pa), stride=STRIDE)
        patchify.patchify(str(b_tif), str(pb), stride=STRIDE)

        # --- CNN (no adaptation) ---
        ga, gb = WORK / f"{key}_gA.npz", WORK / f"{key}_gB.npz"
        classify_patches.classify(str(pa), str(ga))
        classify_patches.classify(str(pb), str(gb))
        change_detection.detect(str(ga), str(gb), str(WORK / f"{key}_cnn"))

        # --- CNN + AdaBN (domain adaptation) ---
        gaz, gbz = WORK / f"{key}_gA_bn.npz", WORK / f"{key}_gB_bn.npz"
        classify_patches.classify(str(pa), str(gaz), adabn=True)
        classify_patches.classify(str(pb), str(gbz), adabn=True)
        change_detection.detect(str(gaz), str(gbz), str(WORK / f"{key}_adabn"))

        # --- NDVI baseline (per-scene Otsu threshold) ---
        ndvi_baseline.baseline(str(a_tif), str(b_tif), str(masks["ndvi"]))

    # The GFW reference depends only on the cell grid, which all three detectors
    # share, so read the (remote) GFC tile once per threshold instead of six times.
    print(f"  building GFW reference for {key} ...", flush=True)
    refs = {frac: build_reference(str(masks["cnn"]), gfc_url(key), 2016, 2024,
                                  min_loss_frac=frac) for frac in FRACS}

    return {"biome": SITES[key]["biome"],
            "cnn": _score(str(masks["cnn"]), key, refs),
            "adabn": _score(str(masks["adabn"]), key, refs),
            "ndvi": _score(str(masks["ndvi"]), key, refs)}


def _f1(site_res, method, frac=HEADLINE):
    return site_res[method][f"{frac:.2f}"]["f1"]


def _sd(xs):
    """Sample sd (n-1). The population sd understates spread on a site sample."""
    return stdev(xs) if len(xs) > 1 else 0.0


def main(rescore=False):
    results = {}
    for key in SITES:
        print(f"\n========== {key} ==========")
        r = run_site(key, rescore=rescore)
        if r:
            results[key] = r

    keys = list(results)
    methods = [("CNN", "cnn"), ("CNN+AdaBN", "adabn"), ("NDVI", "ndvi")]

    print(f"\n\n============ SUMMARY (GFW loss-frac >= {HEADLINE:.0%}) ============")
    print(f"{'site':20s} {'biome':30s} " + " ".join(f"{m[0]:>16s}" for m in methods))
    for k in keys:
        cells = []
        for _, mm in methods:
            f1 = _f1(results[k], mm)
            lo, hi = results[k][mm][f"{HEADLINE:.2f}"]["f1_ci95"]
            cells.append(f"{f1:.3f}[{lo:.2f}-{hi:.2f}]")
        print(f"{k:20s} {results[k]['biome'][:29]:30s} " + " ".join(f"{c:>16s}" for c in cells))

    if keys:
        print("-" * 96)
        for label, mm in methods:
            for frac in FRACS:
                f1s = [_f1(results[k], mm, frac) for k in keys]
                ps = [results[k][mm][f"{frac:.2f}"]["precision"] for k in keys]
                rs = [results[k][mm][f"{frac:.2f}"]["recall"] for k in keys]
                print(f"{label:10s} @{frac:.0%}  F1 {mean(f1s):.3f}+/-{_sd(f1s):.3f}  "
                      f"P {mean(ps):.3f}+/-{_sd(ps):.3f}  R {mean(rs):.3f}+/-{_sd(rs):.3f}")

        # Per-site wins at headline threshold
        wins = {m[0]: 0 for m in methods}
        for k in keys:
            best = max(methods, key=lambda m: _f1(results[k], m[1]))
            wins[best[0]] += 1
        print(f"\nPer-site wins @{HEADLINE:.0%}: " + ", ".join(f"{k}={v}" for k, v in wins.items()))

        # Paired signed-rank tests across sites (few sites -> low power; reported honestly)
        def paired(a_m, b_m):
            a = [_f1(results[k], a_m) for k in keys]
            b = [_f1(results[k], b_m) for k in keys]
            diff = [ai - bi for ai, bi in zip(a, b)]
            stat = pval = None
            if wilcoxon is not None and any(d != 0 for d in diff):
                try:
                    stat, pval = wilcoxon(a, b)
                except Exception:
                    pass
            return {"mean_diff": round(mean(diff), 4),
                    "wilcoxon_stat": None if stat is None else float(stat),
                    "wilcoxon_p": None if pval is None else round(float(pval), 4)}

        tests = {"adabn_vs_cnn": paired("adabn", "cnn"),
                 "adabn_vs_ndvi": paired("adabn", "ndvi"),
                 "cnn_vs_ndvi": paired("cnn", "ndvi")}
        print("\nPaired tests across sites (Wilcoxon signed-rank, n={}):".format(len(keys)))
        for name, t in tests.items():
            print(f"  {name:16s} mean_diff={t['mean_diff']:+.4f}  "
                  f"W={t['wilcoxon_stat']}  p={t['wilcoxon_p']}")

        summary = {}
        for label, mm in methods:
            f1s = [_f1(results[k], mm) for k in keys]
            summary[mm] = {"mean_f1": round(mean(f1s), 4), "sd_f1": round(_sd(f1s), 4)}

        out = {"headline_frac": HEADLINE, "n_sites": len(keys),
               "bootstrap": {"n_resamples": N_BOOT, "seed": BOOT_SEED,
                             "unit": f"{BLOCK}x{BLOCK} cell block (stride-32 overlap)"},
               "per_site": results, "summary_at_headline": summary,
               "wins_at_headline": wins, "paired_tests": tests}
        with open(WORK / "multi_site_results.json", "w") as f:
            json.dump(out, f, indent=2)
        print(f"\nSaved -> {WORK / 'multi_site_results.json'}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Multi-site cross-biome evaluation.")
    ap.add_argument("--rescore", action="store_true",
                    help="Reuse existing change masks; recompute scores/CIs only.")
    args = ap.parse_args()
    main(rescore=args.rescore)
