# Cross-Biome Deforestation Detection with a Lightweight EuroSAT Transfer Classifier: Domain Shift, Label-Free Adaptation, and a Spectral-Index Baseline

**Joshua Anojulu**
University of North Texas, Denton, TX, USA · joshanojulu@gmail.com
*(co-author / mentor to be added before submission)*

---

## Abstract

Automated deforestation monitoring needs tools that are accurate, reproducible, and cheap to run, but the accuracy a model reports on a benchmark rarely survives contact with new geographies. We study, end to end, how a lightweight land-cover classifier behaves when it is pushed out of its training distribution and across biomes. We fine-tune a ResNet50 (ImageNet-pretrained) on the EuroSAT Sentinel-2 dataset, reaching **98.26%** test accuracy (macro-F1 0.982), and show that a 13-band multispectral variant gives **no measurable gain** (98.22%)—RGB already saturates the benchmark. We then apply the classifier to two-date (2016 vs 2024) Sentinel-2 imagery at **eight deforestation frontiers across three biomes and five countries** (Amazon: Rondônia, São Félix do Xingu, Mato Grosso, Brazil; Indonesian peat/palm oil: Riau, Sumatra; Congo Basin: Tshopo and Mai-Ndombe, DRC; dry forest: Santa Cruz, Bolivia, and Gran Chaco, Paraguay), validating detected Forest→non-Forest change against Global Forest Watch (Hansen Global Forest Change) with bootstrap confidence intervals. Two findings drive the paper. First, **benchmark accuracy does not transfer for free**: a naïve application of the EuroSAT model to atmospherically corrected Level-2A imagery misclassifies 72% of rainforest as water until per-channel radiometric *moment matching* is applied, and even after matching the classifier **fails catastrophically at 3 of 8 sites** (both Congo sites and Gran Chaco, producing zero or all-wrong detections on verifiably clean composites)—a reproducible domain-shift failure—while excelling on an in-domain Amazon site (Mato Grosso, F1 0.480). Second, a simple, **label-free domain adaptation—AdaBN**, recomputing BatchNorm statistics on each target scene—**eliminates every catastrophic failure** (e.g. Congo/Tshopo F1 0.001→0.395, precision 0.02→0.70, non-overlapping bootstrap CIs) and yields the most *consistent* detector across biomes (lowest variance, mean F1 0.250±0.124), though recovery quality is site-dependent. Against a classical NDVI-difference baseline (per-scene Otsu threshold), no method dominates: NDVI has the highest mean F1 (0.336) but is itself site-fragile (it collapses at one dry-forest site), while the plain CNN is marginally significantly worse than NDVI overall (Wilcoxon p=0.055) yet the adapted CNN never fails catastrophically. We argue that **cross-biome robustness, not peak in-biome F1, is the metric that matters**, and that a domain-shifted RGB CNN is not a free upgrade over a spectral index without adaptation.

## 1. Introduction

Tropical deforestation is a leading driver of biodiversity loss and carbon emissions, and the global tree-cover record shows sustained forest loss over two decades, most of it in the tropics and driven substantially by commodity agriculture and pasture expansion (Hansen et al., 2013; Curtis et al., 2018; FAO, 2020). Authoritative monitoring—most prominently Global Forest Watch, built on the Hansen Global Forest Change (GFC) product—relies on large-scale processing pipelines. A complementary and pedagogically important question for students and small labs is whether a *lightweight, reproducible* convolutional model, trainable in under half an hour on a single consumer GPU, can recover a useful deforestation signal, **how far it generalizes across biomes**, and how it compares to both an authoritative reference and a classical spectral baseline.

Most student and tutorial treatments stop at a single, favorable study area and report agreement with GFW there. We deliberately do the opposite: we deploy the *same* classifier across eight frontiers spanning three biomes (each biome replicated), look for where it breaks, diagnose why, and test a cheap fix. This turns a "does it work?" demonstration into a small but rigorous **robustness and domain-adaptation study**.

This work makes five contributions:

1. A reproducible EuroSAT land-cover classifier (ResNet50 transfer learning, 98.26% test accuracy) with common preprocessing pitfalls corrected (§2.2), and a controlled test showing a **13-band multispectral variant gives no gain** over RGB (§3.1).
2. A demonstration—and fix—of the **radiometric domain shift** that silently breaks EuroSAT-trained models on modern Sentinel-2 Level-2A imagery (§2.4, §3.2).
3. A **cross-biome evaluation** of the pipeline across eight frontiers / three biomes, benchmarked against GFW with bootstrap confidence intervals, exposing **reproducible catastrophic out-of-biome failures** (zero or all-wrong detections at 3 of 8 sites, including two independent Congo Basin sites) that we show—via composite quality diagnostics—are genuine domain shift, not data degradation (§3.4).
4. A **label-free domain adaptation (AdaBN)** that recovers the failure and delivers the most consistent cross-biome detector, motivated by a controlled adaptation ablation (§3.3) and confirmed on real target imagery (§3.4).
5. A fair **classical baseline (NDVI-difference with a per-scene Otsu threshold)**, showing that neither the CNN nor the spectral index dominates across biomes and characterizing exactly where each fails (§3.4).

## 2. Methods

### 2.1 Dataset
EuroSAT (Helber et al., 2019) contains 27,000 Sentinel-2 image patches (64×64 px at 10 m/px) in 10 land-cover classes (AnnualCrop, Forest, HerbaceousVegetation, Highway, Industrial, Pasture, PermanentCrop, Residential, River, SeaLake). We use the RGB version for the main pipeline and the 13-band "all-bands" version for the multispectral comparison (§3.1). We split 80/10/10 into train/validation/test with a fixed seed (42). **Critically**, transforms are applied *per split*: training receives random horizontal/vertical flips (valid for nadir imagery), validation and test receive none. A common tutorial error attaches one transform to the dataset *before* splitting, leaking augmentation into evaluation; we avoid it with an on-the-fly per-split wrapper. Images are resized to 224×224 and normalized with ImageNet statistics.

### 2.2 Model and training
We load ResNet50 (He et al., 2016) with ImageNet weights (`weights=ResNet50_Weights.DEFAULT`; the deprecated `pretrained=True` API is avoided) and replace the final layer with a 10-way head. Training is two-phase: **Phase 1** trains only the head for 10 epochs (Adam, lr 1×10⁻³) with the backbone frozen; **Phase 2** fine-tunes all layers for 8 epochs at lr 1×10⁻⁴. We use cross-entropy, batch size 64, automatic mixed precision, and retain the best checkpoint by validation accuracy. Training took ~20 min on an NVIDIA RTX 4060 Laptop GPU (8 GB), CUDA 12.6, PyTorch 2.12, fixed seed.

For the **multispectral variant**, we replace the first convolution with a 13-channel layer initialized by *weight inflation* (each input channel seeded with the mean of the pretrained RGB filters, scaled by 3/13 to preserve activation magnitude) and normalize per band with EuroSAT all-bands statistics; training is otherwise identical.

### 2.3 Study areas and imagery
We selected eight documented deforestation frontiers, confirmed on the GFW tree-cover-loss layer, spanning three biomes and five countries, with each biome replicated for robustness testing:

| Site | Biome / country | GFC tile |
|---|---|---|
| Rondônia (Ariquemes) | Amazon (Brazil) | 00N_070W |
| São Félix do Xingu, Pará | Amazon (Brazil) | 00N_060W |
| Mato Grosso (Sinop) | Amazon (Brazil) | 10S_060W |
| Riau, Sumatra | Tropical peat / palm oil (Indonesia) | 10N_100E |
| Tshopo | Congo Basin rainforest (DRC) | 10N_020E |
| Mai-Ndombe | Congo Basin rainforest (DRC) | 00N_010E |
| Santa Cruz | Chiquitano dry forest / soy (Bolivia) | 10S_070W |
| Gran Chaco | Dry forest (Paraguay) | 20S_070W |

For each we retrieved cloud-filtered (≤25%) median composites of **B04, B03, B02** (RGB) plus **B08** (NIR) Sentinel-2 (Drusch et al., 2012) Level-2A for the **2016** and **2024** dry seasons (June–September) from the Copernicus Data Space Ecosystem via openEO. (The original `scihub.copernicus.eu` was retired in 2023; we use the current service.) The same dry-season window is used both years to avoid phenological false change. Scenes are ~2,700–2,800 px per side at 10 m/px, in their local UTM zones (20S–47N), confirming the pipeline is not tied to one projection or hemisphere.

**Composite quality control.** Because a poor result can reflect either the model or the data, we compute per-scene diagnostics (valid-pixel fraction, nodata, saturation, mean NDVI, brightness). All 16 evaluated composites are clean: 100% valid, ~0% nodata, <3.5% saturated. In particular the Congo scenes have healthy mean NDVI (Tshopo 0.66, Mai-Ndombe 0.58–0.61) with 58–75% high-vegetation cover, so the Congo classifier failures in §3.4 are attributable to domain shift, not clouds or gaps.

### 2.4 Radiometric moment matching (a necessary step)
EuroSAT was derived from hazier, less atmospherically corrected imagery with a pronounced blue cast (measured global RGB mean ≈ (86, 97, 103)). Modern Level-2A composites are atmospherically corrected, so a naïve reflectance-to-8-bit render is catastrophically misclassified—**72% of a Rondônia rainforest scene was labeled "SeaLake" (water)**. We correct this by per-channel *moment matching*: each channel is linearly rescaled so its mean and standard deviation match EuroSAT's global statistics, with both dates matched to the same reference (also normalizing the two dates to a common radiometry). After matching, forest classifies sensibly (forest-dominant, ~1% water).

### 2.5 Change detection and validation
Each scene is tiled into georeferenced 64×64 (640 m) patches on a 32 px stride (≈2× finer grid, ~6,300 cells) preserving the model's 640 m footprint. Every patch is classified into a land-cover grid per date. A cell is flagged as **deforestation** if classified Forest in 2016 and one of {AnnualCrop, Pasture, Industrial, Residential, PermanentCrop} in 2024. We validate against the Hansen GFC-2024-v1.12 `lossyear` raster: a reference cell counts as "loss" if a fraction *f* of its ~30 m GFC pixels record loss in (2016, 2024]. We report **f ∈ {0.25, 0.50}** and compute precision, recall, F1, and IoU. Each per-site F1 carries a **95% bootstrap CI** (1,000 resamples over grid cells, seed 42); across-site method differences use a **Wilcoxon signed-rank test** (n=8 sites).

### 2.6 Domain adaptation: AdaBN
Domain shift moves the distribution of intermediate activations, which BatchNorm normalizes using statistics estimated on the *source* (EuroSAT) domain. **AdaBN** (Li et al., 2016) replaces those with *target* statistics: we reset each BatchNorm layer to cumulative-average mode and run label-free forward passes over the target scene's patches before classifying, so each scene/date is normalized to its own radiometry. This requires no labels, no retraining, and one extra forward pass. We first validate AdaBN against alternatives in a controlled ablation (§3.3), then apply it in-pipeline (§3.4).

### 2.7 Classical baseline: NDVI-difference
As a non-learning reference we compute NDVI = (NIR − Red)/(NIR + Red) per pixel for both dates, aggregate to the same 64/32 grid (mean per cell), and flag a cell as loss if it was forest in 2016 (NDVI ≥ τ) and its NDVI dropped by ≥ 0.2 by 2024. To avoid biasing the baseline, **τ is chosen per scene by Otsu's method** (Otsu, 1979) (clamped to [0.35, 0.70]) rather than a fixed constant, so it adapts to biome phenology (dry forest has lower NDVI than wet evergreen forest). The output mask is validated against GFW identically to the CNN.

## 3. Results

### 3.1 Classification, and an RGB-vs-multispectral null result
The RGB classifier reaches **98.26%** test accuracy (2,700 images; best val 98.52%; macro-F1 0.982); all per-class F1 ≥ 0.97, and Forest recall is 0.997—essential for the downstream task (Figure 1: confusion matrix). The 13-band **multispectral** model reaches **98.22%** (macro-F1 0.981): statistically indistinguishable. The ten extra spectral bands give no gain—RGB already saturates EuroSAT—which also justifies the RGB-only deforestation pipeline.

### 3.2 Radiometric domain shift is real and correctable
Without moment matching, the 98%-accurate model produces meaningless output on real imagery (72% of rainforest → water). This is a concrete, quantified instance of dataset shift and the single most important preprocessing step for valid downstream results; §2.4 documents the fix.

### 3.3 Controlled domain-adaptation ablation
Because we lack labeled Sentinel-2 ground truth, we compare adaptation methods on a *controlled* shift: a nonlinear radiometric corruption (per-channel gamma + gain + offset + haze, tuned to mimic the measured EuroSAT→L2A gap) applied to the labeled EuroSAT test set. Nonlinearity ensures a per-channel linear method cannot trivially invert it.

| condition | accuracy | gap recovered |
|---|---|---|
| clean (upper bound) | 0.983 | — |
| shifted, no adaptation | 0.514 | 0% |
| shifted, per-channel moment match | 0.647 | 28% |
| shifted, per-channel histogram match | 0.504 | −2% |
| shifted, **AdaBN** | **0.979** | **99%** |

An unadapted classifier loses ~47 points; moment matching (the pipeline's default) recovers only ~28% under a nonlinear shift; **AdaBN recovers 99% with no labels**, motivating its use on real target scenes.

### 3.4 Cross-biome detection: CNN vs AdaBN vs NDVI
We evaluate three detectors—CNN, CNN+AdaBN, and NDVI(Otsu)—at all eight sites against GFW (Figure 2; Table 1). The results overturn a simple "CNN detects deforestation" narrative.

**Table 1. Per-site F1 vs GFW (loss-frac ≥ 25%), with 95% bootstrap CI.**

| Site | Biome | CNN | CNN+AdaBN | NDVI |
|---|---|---|---|---|
| Rondônia | Amazon | 0.241 [0.20–0.29] | 0.245 [0.20–0.29] | **0.495 [0.45–0.54]** |
| São Félix | Amazon | 0.233 [0.20–0.27] | 0.224 [0.19–0.26] | **0.304 [0.27–0.34]** |
| Mato Grosso | Amazon | 0.480 [0.42–0.53] | 0.492 [0.44–0.55] | **0.712 [0.67–0.75]** |
| Riau | Peat/palm | **0.244 [0.22–0.27]** | 0.227 [0.20–0.25] | 0.181 [0.16–0.20] |
| Tshopo | Congo | 0.001 [0.00–0.00] | **0.395 [0.37–0.42]** | 0.220 [0.20–0.24] |
| Mai-Ndombe | Congo | 0.000 [0.00–0.00] | 0.194 [0.17–0.22] | **0.378 [0.34–0.42]** |
| Santa Cruz | Dry forest | **0.154 [0.12–0.19]** | 0.123 [0.09–0.15] | 0.010 [0.00–0.03] |
| Gran Chaco | Dry forest | 0.000 [0.00–0.00] | 0.100 [0.06–0.14] | **0.392 [0.32–0.45]** |
| **mean ± sd** | | 0.169 ± 0.157 | 0.250 ± 0.124 | **0.336 ± 0.199** |

Four findings:

**(a) The CNN is bimodal: it fails catastrophically out-of-biome (reproducibly) yet excels in-domain.** At **3 of 8 sites** the plain CNN scores F1 ≤ 0.001: Tshopo (precision 0.022, 46 all-wrong detections), Mai-Ndombe (**zero** detections), and Gran Chaco (**zero** detections). It classifies most non-European forest as non-forest, so it finds no Forest→non-Forest transitions. Both independent Congo sites fail, and the composites are clean (§2.3), so this is a systematic domain-shift failure—the most important negative result in the paper, and one single-site studies never surface. Yet at **Mato Grosso**—a mechanized Amazon soy/pasture frontier with large, clean clearings closest to EuroSAT's domain—the same CNN scores its *best* (F1 0.480, precision 0.574). The CNN is strong where the domain is near-EuroSAT and near-zero where it is far, which drives its large variance (±0.157).

**(b) AdaBN eliminates every catastrophic failure.** Label-free BatchNorm adaptation lifts all three zero-failures to positive F1: Tshopo 0.001→**0.395** (precision 0.02→**0.699**; non-overlapping CIs [0.00–0.00] vs [0.37–0.42]), Mai-Ndombe 0.000→0.194, Gran Chaco 0.000→0.100. Recovery quality is *site-dependent*—full at Tshopo, but noisier at Mai-Ndombe (it over-detects: 1,626 cells vs 568 GFW, precision 0.13). This reproduces §3.3's controlled result on real imagery.

**(c) AdaBN buys robustness, not a universal win.** It is the **most consistent** detector (lowest variance, ±0.124) and *never* fails catastrophically, but its mean F1 (0.250) trails NDVI. It is neutral-to-slightly-positive on the easy sites (Mato Grosso 0.480→0.492) and costs ~0.01–0.03 on a couple of others. AdaBN helps most exactly where shift is most severe; a "adapt only if the shift is large" gate is a natural refinement.

**(d) NDVI has the highest mean F1 (0.336) and wins 5/8 sites, but is itself site-fragile.** It leads on the Amazon (Mato Grosso 0.71, Rondônia 0.50) and on both Congo sites and Gran Chaco—yet **collapses at Santa Cruz** (0.010). So its dry-forest behavior is *site-specific, not biome-uniform*: it works at Gran Chaco but fails at Santa Cruz, where the low NDVI dynamic range defeats the absolute ≥0.2-drop rule even with the adaptive Otsu threshold. NDVI has the highest variance (±0.199). On dry forest the two methods trade wins (Santa Cruz: CNN 0.154 > NDVI 0.010; Gran Chaco: NDVI 0.392 > CNN 0.000).

**Statistical honesty.** With n=8 sites the plain CNN is now **marginally significantly worse than NDVI** (Wilcoxon p=0.055); no other pair is significant (AdaBN-vs-CNN p=0.38, AdaBN-vs-NDVI p=0.20; per-site wins NDVI 5 / CNN 2 / AdaBN 1). The strongest, unambiguous effects are per-site (non-overlapping cell-bootstrap CIs), above. We therefore claim *robustness and biome-dependence*, not a single winning method.

## 4. Discussion

The headline lesson is that **in-benchmark accuracy is a poor predictor of cross-biome behavior**. A 98%-accurate classifier fails two ways in the wild—silently (radiometric shift → forest as water) and catastrophically out-of-biome, at nearly half our sites and reproducibly across two independent Congo frontiers—and single-site evaluation hides both. Deploying the same model across biomes and *looking for where it breaks* is what makes the failures visible and the fix testable.

The fix is cheap. AdaBN needs no labels, no retraining, and one forward pass, yet it eliminates every catastrophic failure and makes the detector the most consistent across biomes (lowest variance, no zero-scores). This is a favorable trade for an operational screening tool, where a catastrophic blind spot in one biome is far worse than a few points of mean F1 elsewhere—even though, on our sites, NDVI's mean F1 is higher.

The NDVI comparison keeps the CNN honest: a classical index has the highest mean F1 and should not be dismissed. But it is itself site-fragile (it collapses at one dry-forest site while winning the other), so the useful synthesis is that the methods are complementary and none is safe alone—NDVI excels where the spectral signal of clearing is strong; the adapted CNN is the safer default where it is not (plantation regrowth, unseen radiometry, low-NDVI dry forest).

**Limitations.** (i) n=8 sites still limits across-site statistical power; more frontiers per biome would enable stronger significance testing (a ninth site, Kalimantan, was acquired but excluded for data quality—its only obtainable 2016 composite was cloud-degraded and radiometrically non-comparable to 2024). (ii) 640 m patches miss small/linear clearings, capping recall against all GFW loss (recall is highest for wholesale clearings). (iii) The NDVI baseline uses an absolute-drop rule; a relative-drop variant might be fairer in dry forest, though absolute NDVI-difference is the textbook method. (iv) Moment matching approximates, and AdaBN adapts only second-order (BN) statistics—deeper shift (label/prior shift, unseen classes) is unaddressed. (v) The pipeline classifies Sentinel-2 with a model trained on European scenes; region-matched labels would reduce the underlying shift.

## 5. Conclusion and Future Work

A lightweight, fully reproducible ResNet50/EuroSAT pipeline can recover a deforestation signal that agrees with Global Forest Watch—but only within its comfort zone. Pushed across eight frontiers it fails outright at three of them (both Congo Basin sites and a dry-forest site), a reproducible failure we attribute to genuine domain shift and repair with a label-free AdaBN pass, yielding the most consistent detector across three biomes; a classical NDVI baseline has the highest mean F1 yet is itself site-fragile. No detector dominates. **Robustness across biomes, not peak in-biome F1, is the metric that matters.** Future work: (1) more sites per biome for statistical power; (2) a shift-magnitude gate for selective adaptation; (3) region-matched fine-tuning and deeper adaptation (e.g., feature alignment) beyond BatchNorm; (4) finer patches or segmentation for sub-patch recall; (5) multi-temporal sequences beyond two snapshots.

## References
1. P. Helber, B. Bischke, A. Dengel, D. Borth. "EuroSAT: A Novel Dataset and Deep Learning Benchmark for Land Use and Land Cover Classification." *IEEE JSTARS*, 12(7):2217–2226, 2019.
2. M. C. Hansen et al. "High-Resolution Global Maps of 21st-Century Forest Cover Change." *Science*, 342(6160):850–853, 2013. (Global Forest Watch data source.)
3. K. He, X. Zhang, S. Ren, J. Sun. "Deep Residual Learning for Image Recognition." *CVPR*, 2016.
4. P. G. Curtis, C. M. Slay, N. L. Harris, A. Tyukavina, M. C. Hansen. "Classifying drivers of global forest loss." *Science*, 361(6407):1108–1111, 2018.
5. FAO. *Global Forest Resources Assessment 2020: Main report.* Rome, 2020.
6. M. Drusch et al. "Sentinel-2: ESA's Optical High-Resolution Mission for GMES Operational Services." *Remote Sensing of Environment*, 120:25–36, 2012.
7. J. Deng et al. "ImageNet: A Large-Scale Hierarchical Image Database." *CVPR*, 2009.
8. Y. Li, N. Wang, J. Shi, J. Liu, X. Hou. "Revisiting Batch Normalization for Practical Domain Adaptation." *ICLR Workshop*, 2017 (arXiv:1603.04779, 2016).
9. S. Ioffe, C. Szegedy. "Batch Normalization: Accelerating Deep Network Training by Reducing Internal Covariate Shift." *ICML*, 2015.
10. N. Otsu. "A Threshold Selection Method from Gray-Level Histograms." *IEEE Trans. Systems, Man, and Cybernetics*, 9(1):62–66, 1979.
11. C. J. Tucker. "Red and Photographic Infrared Linear Combinations for Monitoring Vegetation." *Remote Sensing of Environment*, 8(2):127–150, 1979. (NDVI.)

---

*Figures.* Figure 1: EuroSAT confusion matrix (`confusion_matrix.png`). Figure 2: cross-biome F1 comparison with bootstrap CIs (`multisite_f1_comparison.png`). Per-site change maps in `ml-data/deforestation/multi/`.

*Reproducibility:* code, configuration, and figures are in this repository. Dataset and checkpoints are regenerable via `download_data.py`, `python -m src.train`, and `python -m src.train_ms`. The multi-site evaluation is `python -m deforestation.run_all_sites`; composite diagnostics `python -m deforestation.diagnose_composites`. Numerical results and full tables are in `paper/results_summary.md`.
