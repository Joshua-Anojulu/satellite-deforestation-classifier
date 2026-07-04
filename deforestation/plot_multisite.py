"""
Publication figure: per-site F1 (GFW loss-frac >= 25%) for the three detectors
- CNN, CNN+AdaBN, NDVI(Otsu) - with 95% bootstrap CI error bars, across the five
frontiers / three biomes. Reads multi_site_results.json (written by run_all_sites).

Colorblind-safe categorical palette (Okabe-Ito subset), validated with the dataviz
skill's checker (all checks pass; worst adjacent CVD dE 55.7).

Run:  python -m deforestation.plot_multisite
"""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

import config

RESULTS = Path(r"C:\Users\josha\ml-data\deforestation\multi\multi_site_results.json")
HEADLINE = "0.25"

METHODS = [("cnn", "CNN", "#D55E00"),
           ("adabn", "CNN+AdaBN", "#0072B2"),
           ("ndvi", "NDVI (Otsu)", "#009E73")]

SITE_LABELS = {
    "rondonia": "Rondonia\n(Amazon)",
    "sao_felix_xingu": "Sao Felix\n(Amazon)",
    "riau_sumatra": "Riau\n(peat/palm)",
    "tshopo_drc": "Tshopo\n(Congo)",
    "mai_ndombe_drc": "Mai-Ndombe\n(Congo)",
    "santa_cruz_bolivia": "Santa Cruz\n(dry forest)",
    "gran_chaco_paraguay": "Gran Chaco\n(dry forest)",
}


def main():
    d = json.load(open(RESULTS))
    ps = d["per_site"]
    sites = [s for s in SITE_LABELS if s in ps]
    x = np.arange(len(sites))
    width = 0.26

    fig, ax = plt.subplots(figsize=(13, 5.4))
    for i, (mk, label, color) in enumerate(METHODS):
        f1 = np.array([ps[s][mk][HEADLINE]["f1"] for s in sites])
        ci = np.array([ps[s][mk][HEADLINE].get("f1_ci95", [f, f])
                       for s, f in zip(sites, f1)], dtype=float)
        lo = np.clip(f1 - ci[:, 0], 0, None)
        hi = np.clip(ci[:, 1] - f1, 0, None)
        off = (i - 1) * width
        bars = ax.bar(x + off, f1, width, label=label, color=color,
                      yerr=[lo, hi], capsize=3, error_kw=dict(lw=1, ecolor="#444444"))
        for b, v, h in zip(bars, f1, hi):
            ax.text(b.get_x() + b.get_width() / 2, v + h + 0.014,
                    f"{v:.2f}", ha="center", va="bottom", fontsize=8, color="#222222")

    ax.set_xticks(x)
    ax.set_xticklabels([SITE_LABELS[s] for s in sites], fontsize=9)
    ax.set_ylabel("F1 vs Global Forest Watch (loss-frac ≥ 25%)")
    ax.set_ylim(0, 0.62)
    ax.set_title("Cross-biome deforestation detection: CNN vs AdaBN vs NDVI baseline\n"
                 "(bars = F1, whiskers = 95% bootstrap CI)", fontsize=11)
    ax.legend(frameon=False, ncol=3, loc="upper center", fontsize=9)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", color="#e6e6e6", lw=0.8)
    ax.set_axisbelow(True)

    # Annotate the headline AdaBN recovery at Congo.
    if "tshopo_drc" in sites:
        xi = sites.index("tshopo_drc")
        ax.annotate("AdaBN rescues\nCongo (0.00→0.40)",
                    xy=(xi + 0 * width, 0.40), xytext=(xi - 0.15, 0.55),
                    fontsize=8, color="#0072B2", ha="center",
                    arrowprops=dict(arrowstyle="->", color="#0072B2", lw=1))

    fig.tight_layout()
    out = config.FIGURE_DIR / "multisite_f1_comparison.png"
    config.FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=200)
    print(f"Saved -> {out}")


if __name__ == "__main__":
    main()
