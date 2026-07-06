"""
Run the full multi-site, multi-biome evaluation and aggregate with statistical rigor.

For each study area (deforestation/sites.py) and both dates (2016, 2024):
  patchify (stride 32) -> classify THREE ways and validate each vs Global Forest Watch:
    CNN        - EuroSAT model, no adaptation (baseline transfer)
    CNN+AdaBN  - same model, BatchNorm stats recomputed per target scene (domain adapt)
    NDVI       - NDVI-difference baseline with a per-scene Otsu forest threshold

Validation is reported at two GFW loss-fraction thresholds (>=25%, >=50%). Each
per-site F1 gets a 95% bootstrap CI (resampling grid cells). Across sites we report
mean +/- sd, a per-site "wins" tally, and Wilcoxon signed-rank tests (CNN+AdaBN vs
CNN, and best-CNN vs NDVI). n=5 sites -> low inferential power, reported honestly.

Run:  python -m deforestation.run_all_sites
"""
import json
from pathlib import Path
from statistics import mean, pstdev

import numpy as np

from deforestation import patchify, classify_patches, change_detection, ndvi_baseline
from deforestation.validate_gfw import align_and_score
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


def bootstrap_f1(change, ref, n=N_BOOT, seed=BOOT_SEED):
    """95% bootstrap CI on F1 by resampling grid cells with replacement."""
    ch = np.asarray(change).ravel()
    rf = np.asarray(ref).ravel()
    N = ch.size
    if N == 0:
        return (0.0, 0.0)
    rng = np.random.default_rng(seed)
    f1s = np.empty(n)
    for i in range(n):
        idx = rng.integers(0, N, N)
        c, r = ch[idx], rf[idx]
        tp = np.count_nonzero(c & r)
        fp = np.count_nonzero(c & ~r)
        fn = np.count_nonzero(~c & r)
        p = tp / (tp + fp) if (tp + fp) else 0.0
        rr = tp / (tp + fn) if (tp + fn) else 0.0
        f1s[i] = 2 * p * rr / (p + rr) if (p + rr) else 0.0
    return (round(float(np.percentile(f1s, 2.5)), 4),
            round(float(np.percentile(f1s, 97.5)), 4))


def _score(mask_npz, key, tag):
    """Validate a change mask at all FRACS; attach a bootstrap F1 CI at HEADLINE."""
    out = {}
    for frac in FRACS:
        res, change, ref = align_and_score(mask_npz, gfc_url(key), 2016, 2024,
                                           min_loss_frac=frac, return_masks=True)
        if frac == HEADLINE:
            res["f1_ci95"] = bootstrap_f1(change, ref)
        out[f"{frac:.2f}"] = res
    return out


def run_site(key):
    if SITES[key].get("exclude"):
        print(f"[skip] {key}: excluded (see sites.py)"); return None
    a_tif = SITES_DIR / f"{key}_2016.tif"
    b_tif = SITES_DIR / f"{key}_2024.tif"
    if not (a_tif.exists() and b_tif.exists()):
        print(f"[skip] {key}: scenes missing"); return None

    pa, pb = WORK / f"{key}_pA.npz", WORK / f"{key}_pB.npz"
    patchify.patchify(str(a_tif), str(pa), stride=32)
    patchify.patchify(str(b_tif), str(pb), stride=32)

    # --- CNN (no adaptation) ---
    ga, gb = WORK / f"{key}_gA.npz", WORK / f"{key}_gB.npz"
    classify_patches.classify(str(pa), str(ga))
    classify_patches.classify(str(pb), str(gb))
    change_detection.detect(str(ga), str(gb), str(WORK / f"{key}_cnn"))
    cnn = _score(str(WORK / f"{key}_cnn_mask.npz"), key, "cnn")

    # --- CNN + AdaBN (domain adaptation) ---
    gaz, gbz = WORK / f"{key}_gA_bn.npz", WORK / f"{key}_gB_bn.npz"
    classify_patches.classify(str(pa), str(gaz), adabn=True)
    classify_patches.classify(str(pb), str(gbz), adabn=True)
    change_detection.detect(str(gaz), str(gbz), str(WORK / f"{key}_adabn"))
    adabn = _score(str(WORK / f"{key}_adabn_mask.npz"), key, "adabn")

    # --- NDVI baseline (per-scene Otsu threshold) ---
    ndvi_baseline.baseline(str(a_tif), str(b_tif), str(WORK / f"{key}_ndvi_mask.npz"))
    ndvi = _score(str(WORK / f"{key}_ndvi_mask.npz"), key, "ndvi")

    return {"biome": SITES[key]["biome"], "cnn": cnn, "adabn": adabn, "ndvi": ndvi}


def _f1(site_res, method, frac=HEADLINE):
    return site_res[method][f"{frac:.2f}"]["f1"]


def main():
    results = {}
    for key in SITES:
        print(f"\n========== {key} ==========")
        r = run_site(key)
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
                print(f"{label:10s} @{frac:.0%}  F1 {mean(f1s):.3f}+/-{pstdev(f1s):.3f}  "
                      f"P {mean(ps):.3f}+/-{pstdev(ps):.3f}  R {mean(rs):.3f}+/-{pstdev(rs):.3f}")

        # Per-site wins at headline threshold
        wins = {m[0]: 0 for m in methods}
        for k in keys:
            best = max(methods, key=lambda m: _f1(results[k], m[1]))
            wins[best[0]] += 1
        print(f"\nPer-site wins @{HEADLINE:.0%}: " + ", ".join(f"{k}={v}" for k, v in wins.items()))

        # Paired signed-rank tests across sites (n=5 -> low power; reported honestly)
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

        out = {"headline_frac": HEADLINE, "n_sites": len(keys),
               "per_site": results, "wins_at_headline": wins, "paired_tests": tests}
        with open(WORK / "multi_site_results.json", "w") as f:
            json.dump(out, f, indent=2)
        print(f"\nSaved -> {WORK / 'multi_site_results.json'}")


if __name__ == "__main__":
    main()
