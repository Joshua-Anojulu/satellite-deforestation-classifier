# Cross-Biome Deforestation Detection with a EuroSAT Transfer Classifier: Domain Shift, Label-Free Adaptation, and a Spectral-Index Baseline

**Joshua Anojulu**
University of North Texas, Denton, TX, USA · joshanojulu@gmail.com
*(co-author / mentor to be added before submission)*

---

## Abstract

We fine-tune a ResNet50 on EuroSAT to 98.26% test accuracy (macro-F1 0.982) and show that a 13-band multispectral variant of the same model gains nothing (98.22%): RGB saturates the benchmark on its own. We then ask what that accuracy buys outside Europe. We apply the classifier to two-date Sentinel-2 imagery (2016 and 2024) at eight deforestation frontiers across three biomes and five countries, and we score the resulting Forest-to-non-Forest change against the Hansen Global Forest Change record.

The classifier loses most of that accuracy outside Europe. Without radiometric correction it labels 72% of a Rondônia rainforest scene as water, and per-channel moment matching repairs that. Even after matching, it collapses at three of the eight sites, returning zero or near-zero correct detections at both Congo Basin sites and at Gran Chaco. Our composite diagnostics rule out clouds and gaps as the cause, which leaves domain shift. Recomputing BatchNorm statistics on each target scene (AdaBN) costs one label-free forward pass and no retraining, and it removes all three collapses: at Tshopo, F1 climbs from 0.001 to 0.397 and precision from 0.02 to 0.70, with non-overlapping bootstrap intervals. AdaBN gives the steadiest detector across biomes (mean F1 0.250, sd 0.130) without giving the strongest. A classical NDVI-difference baseline with a per-scene Otsu threshold posts the highest mean F1 (0.337, sd 0.213) and wins five of eight sites, yet it fails at Santa Cruz, where it recovers 2 of 383 loss cells. The plain CNN trails NDVI across sites (Wilcoxon p=0.055, n=8). No detector wins at all eight. If you deploy such a tool, robustness across biomes will matter more to you than peak in-biome F1, and an RGB CNN carried into a new biome without adaptation buys you nothing over a spectral index.

## 1. Introduction

Tropical deforestation drives biodiversity loss and carbon emissions, and the global tree-cover record shows two decades of sustained loss concentrated in the tropics, much of it from commodity agriculture and pasture (Hansen et al., 2013; Curtis et al., 2018; FAO, 2020). The authoritative monitors, Global Forest Watch chief among them, run large processing pipelines on dedicated infrastructure. Students and small labs cannot. We therefore asked whether a lightweight convolutional model, trainable in twenty minutes on one consumer GPU, recovers a usable deforestation signal, how far that signal travels across biomes, and how it compares against an authoritative reference and a classical spectral index.

Most tutorial treatments pick one favorable study area, report agreement with GFW, and stop. We inverted that. We took a single classifier to eight frontiers, hunted for the places it breaks, diagnosed why, and tested a cheap repair. We set out to demonstrate a pipeline and ended up with a robustness study.

The paper contributes five things:

1. A reproducible EuroSAT classifier (ResNet50 transfer learning, 98.26% test accuracy) with the usual preprocessing traps removed (§2.2), plus a controlled comparison showing that 13 spectral bands add nothing over RGB (§3.1).
2. A measured account of the radiometric domain shift that breaks EuroSAT-trained models on Level-2A imagery while raising no error, and the correction for it (§2.4, §3.2).
3. A cross-biome evaluation at eight frontiers, scored against GFW with block-bootstrap intervals, which exposes reproducible out-of-biome collapses at three sites (including two independent Congo Basin frontiers) that composite diagnostics attribute to domain shift rather than bad data (§3.4).
4. A label-free adaptation (AdaBN) that repairs every collapse, motivated by a controlled ablation (§3.3) and confirmed on real target scenes (§3.4).
5. A fair classical baseline (NDVI difference with a per-scene Otsu threshold), which shows that neither the CNN nor the index dominates, and pins down where each one fails (§3.4).

## 2. Methods

### 2.1 Dataset

EuroSAT (Helber et al., 2019) holds 27,000 Sentinel-2 patches (64×64 px at 10 m/px) across 10 land-cover classes. We use the RGB version for the main pipeline and the 13-band version for the multispectral comparison (§3.1), splitting 80/10/10 into train, validation, and test under a fixed seed (42).

We apply transforms per split. Training patches get random horizontal and vertical flips, which are valid for nadir imagery; validation and test patches get none. Many tutorials attach one transform to the dataset before splitting, which leaks augmentation into evaluation and inflates the reported number. An on-the-fly per-split wrapper avoids that. We resize to 224×224 and normalize with ImageNet statistics.

### 2.2 Model and training

We load ResNet50 (He et al., 2016) with ImageNet weights through the current `weights=ResNet50_Weights.DEFAULT` API and swap the final layer for a 10-way head. Training runs in two phases: the head alone for 10 epochs (Adam, lr 1×10⁻³) with the backbone frozen, then all layers for 8 epochs at lr 1×10⁻⁴. We use cross-entropy, batch size 64, mixed precision, and keep the best checkpoint by validation accuracy. A run takes about 20 minutes on an RTX 4060 Laptop GPU (8 GB) under CUDA 12.6 and PyTorch 2.12.

For the multispectral variant we replace the first convolution with a 13-channel layer and initialize it by weight inflation: each input channel starts from the mean of the pretrained RGB filters, scaled by 3/13 to hold activation magnitude steady. Per-band normalization uses EuroSAT all-bands statistics. Everything else matches the RGB run.

### 2.3 Study areas and imagery

We picked eight documented frontiers, each confirmed against the GFW tree-cover-loss layer, spanning three biomes and five countries, with every biome replicated so that a single site cannot carry a conclusion:

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

For each site we pulled cloud-filtered (≤25%) median composites of B04, B03, B02 (RGB) and B08 (NIR) from Sentinel-2 Level-2A (Drusch et al., 2012) for the 2016 and 2024 dry seasons (June to September), using the Copernicus Data Space Ecosystem through openEO. The older `scihub.copernicus.eu` endpoint shut down in 2023; we use its replacement. Holding the season fixed across both years keeps leaf phenology from masquerading as clearing. Scenes run 2,700 to 2,800 px per side at 10 m/px in their local UTM zones (20S to 47N), so the pipeline is not tied to one projection or hemisphere.

**Composite quality control.** A weak result can indict the model or the imagery, and we wanted to know which. Per-scene diagnostics (valid-pixel fraction, nodata, saturation, mean NDVI, brightness) show all 16 evaluated composites are clean: 100% valid, near-0% nodata, under 3.5% saturated. The Congo scenes in particular carry healthy vegetation signal (mean NDVI 0.66 at Tshopo, 0.58 to 0.61 at Mai-Ndombe, with 58% to 75% high-vegetation cover). Whatever breaks the classifier there, it is not cloud.

### 2.4 Radiometric moment matching

EuroSAT came from hazier, less atmospherically corrected imagery with a blue cast (measured global RGB mean ≈ 86, 97, 103). A modern Level-2A composite has the haze removed, so a naive reflectance-to-8-bit render looks nothing like what the model trained on. The consequence is not subtle: the classifier assigned "SeaLake" to 72% of a Rondônia rainforest scene.

We correct this by matching moments per channel, rescaling each channel so its mean and standard deviation meet EuroSAT's global statistics. Both dates match the same reference, which also puts the two years on a common radiometry. After matching, forest classifies as forest and water drops to about 1% of the scene.

### 2.5 Change detection and validation

We tile each scene into georeferenced 64×64 patches (640 m on the ground) at a 32 px stride, which doubles grid resolution while preserving the 640 m footprint the model expects. Each patch gets a land-cover label per date. A cell counts as deforestation when it reads Forest in 2016 and one of {AnnualCrop, Pasture, Industrial, Residential, PermanentCrop} in 2024.

We score against the Hansen GFC-2024-v1.12 `lossyear` raster. A reference cell counts as loss when at least a fraction *f* of its ~30 m GFC pixels record loss in the interval (2016, 2024]. We report *f* ∈ {0.25, 0.50} with precision, recall, F1, and IoU.

**Bootstrap over blocks, not cells.** The 32 px stride means neighboring cells share half their pixels, so each ground pixel lands in up to four cells and the cells are not independent draws. Resampling them one at a time, as a naive bootstrap would, treats roughly 7,300 correlated cells as 7,300 independent ones and reports intervals that are too tight. We measured the effect at Tshopo: the naive interval spans [0.374, 0.417] while a bootstrap over spatially disjoint units spans [0.345, 0.427], nearly twice as wide. We therefore resample 2×2 blocks of cells (1,000 resamples, seed 42), which restores the independent unit. Every interval in this paper is a block bootstrap. Across-site comparisons use a Wilcoxon signed-rank test over the eight sites.

One bias is worth naming. The interval (2016, 2024] excludes loss that Hansen labels 2016, because our date-A composite is a mid-year (June to September) median and clearing from early 2016 shows up in it. Clearing in the last months of 2016 stays invisible in composite A yet also sits outside the reference, so a detector that catches it is charged a false positive. At annual resolution neither bound is right, and we take the conservative one.

### 2.6 Domain adaptation: AdaBN

Domain shift moves the distribution of intermediate activations, and BatchNorm normalizes those activations with statistics estimated on the source domain. AdaBN (Li et al., 2016) swaps in target statistics instead. We reset each BatchNorm layer to cumulative-average mode and run label-free forward passes over the target scene's patches before classifying, so each scene and date normalizes to its own radiometry. The method needs no labels, no retraining, and one extra pass. We validate it against alternatives under a controlled shift (§3.3) before trusting it in the pipeline (§3.4).

### 2.7 Classical baseline: NDVI difference

As a non-learning reference we compute NDVI = (NIR − Red)/(NIR + Red) per pixel for both dates, aggregate to the same 64/32 grid by cell mean, and flag a cell when it was forest in 2016 (NDVI ≥ τ) and its NDVI fell by 0.2 or more by 2024. Fixing τ at a constant would hand the CNN an unearned advantage, since dry forest carries lower NDVI than wet evergreen forest and a 0.6 cutoff would miss it. We therefore choose τ per scene by Otsu's method (Otsu, 1979), clamped to [0.35, 0.70]. We then score the resulting mask against GFW on the same footing as the CNN.

## 3. Results

### 3.1 Classification, and a multispectral null result

The RGB classifier reaches 98.26% test accuracy on 2,700 held-out images (best validation 98.52%, macro-F1 0.982). Every per-class F1 clears 0.97, and Forest recall hits 0.997, which is what the downstream task depends on (Figure 1). The 13-band model reaches 98.22% (macro-F1 0.981). Ten extra spectral bands buy nothing. RGB saturates EuroSAT, and that null result justifies the RGB-only deforestation pipeline.

### 3.2 Radiometric shift is real and correctable

Without moment matching, a 98%-accurate model produces nonsense on real imagery: 72% of rainforest read as water. This is dataset shift in its plainest form, and correcting it is the one preprocessing step that decides whether anything downstream means anything.

### 3.3 Controlled adaptation ablation

We have no labeled Sentinel-2 ground truth, so we cannot measure adaptation on the real target domain. We built a controlled substitute: a nonlinear radiometric corruption (per-channel gamma, gain, offset, and haze, tuned to the measured EuroSAT-to-L2A gap) applied to the labeled EuroSAT test set. Nonlinearity matters here, since a per-channel linear method could otherwise invert the shift and the comparison would prove nothing.

| condition | accuracy | gap recovered |
|---|---|---|
| clean (upper bound) | 0.983 | n/a |
| shifted, no adaptation | 0.514 | 0% |
| shifted, per-channel moment match | 0.647 | 28% |
| shifted, per-channel histogram match | 0.504 | −2% |
| shifted, AdaBN | 0.979 | 99% |

An unadapted classifier gives up 47 points. Moment matching, the pipeline's default, recovers 28% of that under a nonlinear shift, and histogram matching recovers none. AdaBN recovers 99% without a single label, which is what sent us to test it on real scenes.

Note that moment matching and histogram matching draw their reference statistics from the clean version of the very images being scored, which is more information than either would have in deployment. The leak flatters them, so AdaBN's margin here is a floor.

### 3.4 Cross-biome detection: CNN vs AdaBN vs NDVI

We ran all three detectors at all eight sites against GFW (Table 1, Figure 2). The results do not support a simple "the CNN detects deforestation" story.

**Table 1. Per-site F1 vs GFW (loss fraction ≥ 25%), with 95% block-bootstrap CI.**

| Site | Biome | CNN | CNN+AdaBN | NDVI |
|---|---|---|---|---|
| Rondônia | Amazon | 0.234 [0.17–0.30] | 0.242 [0.17–0.31] | 0.495 [0.42–0.56] |
| São Félix | Amazon | 0.232 [0.19–0.27] | 0.229 [0.19–0.27] | 0.304 [0.26–0.35] |
| Mato Grosso | Amazon | 0.479 [0.40–0.56] | 0.486 [0.39–0.57] | 0.711 [0.64–0.77] |
| Riau | Peat / palm | 0.248 [0.21–0.28] | 0.222 [0.19–0.26] | 0.177 [0.14–0.21] |
| Tshopo | Congo | 0.001 [0.00–0.00] | 0.397 [0.37–0.43] | 0.220 [0.19–0.25] |
| Mai-Ndombe | Congo | 0.000 [0.00–0.00] | 0.198 [0.17–0.23] | 0.384 [0.32–0.45] |
| Santa Cruz | Dry forest | 0.156 [0.11–0.20] | 0.126 [0.08–0.17] | 0.010 [0.00–0.03] |
| Gran Chaco | Dry forest | 0.000 [0.00–0.00] | 0.100 [0.05–0.15] | 0.392 [0.28–0.49] |
| **mean ± sd** | | 0.169 ± 0.168 | 0.250 ± 0.130 | 0.337 ± 0.213 |

**(a) The CNN is bimodal. It collapses out of biome and shines in it.** At three of eight sites the plain CNN scores F1 ≤ 0.001. Tshopo produces 46 detections of which one is correct (precision 0.022). Mai-Ndombe and Gran Chaco produce none at all. The model labels most non-European forest as something other than Forest, so it finds no Forest-to-non-Forest transitions to report. Both Congo sites fail independently, and §2.3 shows their composites are clean, which makes this a systematic domain-shift failure rather than an artifact. A single-site study would never have surfaced it.

The same model then posts its best score at Mato Grosso (F1 0.479, precision 0.574, recall 0.412), a mechanized soy and pasture frontier whose large rectangular clearings sit closest to EuroSAT's European domain. Strong where the domain is near, absent where it is far: that split is what drives the CNN's sd of 0.168, the widest of the three detectors.

**(b) AdaBN repairs every collapse.** Label-free BatchNorm adaptation lifts all three zeros into positive territory. Tshopo goes from 0.001 to 0.397, with precision climbing from 0.022 to 0.702 and 672 of 958 detections landing on real loss; the CNN and AdaBN intervals ([0.00–0.00] and [0.37–0.43]) do not overlap. Mai-Ndombe goes from 0.000 to 0.198 and Gran Chaco from 0.000 to 0.100, and neither of those intervals overlaps its CNN counterpart either.

Recovery quality varies by site. At Tshopo the model recovers with its precision intact. At Mai-Ndombe it over-fires, hitting 1,626 cells against 570 in the GFW reference, so recall reaches 0.381 while precision sits at 0.134. The model now sees forest, and it over-calls the change. That is a different failure from seeing nothing, and a more tractable one.

**(c) AdaBN buys consistency.** It carries the lowest spread (sd 0.130) and never collapses, yet its mean F1 (0.250) trails NDVI's. On the easy sites it moves little (Mato Grosso 0.479 to 0.486), and it costs a couple of points at Riau and Santa Cruz. AdaBN pays off in proportion to how badly the domain has shifted, which suggests an obvious refinement: gate the adaptation on a measured shift magnitude instead of applying it always.

**(d) NDVI leads on average and still cannot be trusted alone.** It takes the highest mean F1 (0.337), wins five of eight sites, and leads across the Amazon (Mato Grosso 0.711, Rondônia 0.495), both Congo sites, and Gran Chaco. Then it falls apart at Santa Cruz, where it returns 2 detections against 383 reference loss cells: both are correct, giving a precision of 1.000 that means nothing next to a recall of 0.005. Its dry-forest behavior is site-specific rather than biome-uniform, since it wins Gran Chaco and loses Santa Cruz, where the compressed NDVI dynamic range defeats an absolute 0.2-drop rule even with an adaptive threshold. NDVI also carries the widest spread of the three (sd 0.213). On dry forest the two families trade wins: Santa Cruz goes to the CNN (0.156 against 0.010), Gran Chaco to NDVI (0.392 against 0.000).

**What the statistics support.** Across eight sites the plain CNN trails NDVI at the edge of significance (Wilcoxon p=0.055). No other pair separates (AdaBN vs CNN p=0.31, AdaBN vs NDVI p=0.20; per-site wins NDVI 5, CNN 2, AdaBN 1). Eight sites give a signed-rank test little power, and we will not dress that up. The firm results in this paper are the per-site ones, where the block-bootstrap intervals separate cleanly. We claim biome-dependence and robustness, and we do not claim a winning method.

## 4. Discussion

In-benchmark accuracy tells you little about cross-biome behavior. Our 98%-accurate classifier fails two ways once it leaves Europe. Uncorrected radiometry turns rainforest into water and raises no error along the way. Then, at three of eight sites, the model stops finding anything at all, and it does so at two Congo frontiers that share nothing beyond a biome. Evaluating on one site would have hidden both failures. We found them by taking the same model to eight sites and looking for the breaks, which is also what made the repair testable.

The repair is cheap. AdaBN wants no labels, no retraining, and one forward pass, and it clears every collapse while producing the steadiest detector we tested. For an operational screening tool that trade is worth taking, because a blind spot covering an entire biome costs more than a few points of mean F1 elsewhere. NDVI's higher average does not change that.

The NDVI comparison keeps the CNN honest. A 1979 spectral index beats a fine-tuned ResNet50 on mean F1 across our sites, and anyone proposing a CNN here owes that baseline an answer. But the index breaks too, collapsing at one of the two dry-forest sites while winning the other. The methods are complements. NDVI excels where clearing leaves a strong spectral signature; the adapted CNN is the safer default where it does not, as in plantation regrowth, unfamiliar radiometry, and low-NDVI dry forest.

**Limitations.** Eight sites limit across-site power, and more frontiers per biome would sharpen the significance testing. A ninth site, Kalimantan, was acquired and then excluded: its only obtainable 2016 composite was cloud-degraded and not radiometrically comparable to 2024. Patches of 640 m miss small and linear clearings, which caps recall against fine-grained GFW loss and explains why recall runs highest for wholesale clearing. The NDVI baseline uses an absolute-drop rule, and a relative-drop variant might treat dry forest more fairly, though absolute NDVI difference is the textbook method. Moment matching is an approximation and AdaBN adjusts only second-order statistics, so deeper shift (label shift, unseen classes) goes unaddressed. Our reference interval excludes Hansen loss labeled 2016, which charges a false positive for any late-2016 clearing a detector catches (§2.5). Finally, the pipeline classifies tropical imagery with a model trained on European scenes; region-matched labels would shrink the underlying shift instead of correcting for it after the fact.

## 5. Conclusion and Future Work

A lightweight ResNet50/EuroSAT pipeline recovers a deforestation signal that agrees with Global Forest Watch, but only inside its comfort zone. Across eight frontiers it fails outright at three, and we trace that failure to domain shift and repair it with a label-free AdaBN pass that leaves us with the most consistent detector across three biomes. A classical NDVI baseline still posts the highest mean F1 and still breaks at a site of its own. No detector dominates, and robustness across biomes deserves more weight than peak in-biome F1.

Five directions follow. Add sites per biome for statistical power. Gate adaptation on a measured shift magnitude. Push past BatchNorm to feature alignment and region-matched fine-tuning. Move to finer patches or segmentation to recover sub-patch clearings. Replace the two-snapshot design with multi-temporal sequences.

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

*Figures.* Figure 1: EuroSAT confusion matrix (`confusion_matrix.png`). Figure 2: cross-biome F1 comparison with block-bootstrap CIs (`multisite_f1_comparison.png`). Per-site change maps in `ml-data/deforestation/multi/`.

*Reproducibility:* code, configuration, and figures live in this repository. The dataset and checkpoints regenerate via `download_data.py`, `python -m src.train`, and `python -m src.train_ms`. The multi-site evaluation runs as `python -m deforestation.run_all_sites` (add `--rescore` to recompute scores from existing masks); composite diagnostics run as `python -m deforestation.diagnose_composites`. Full numerical tables are in `paper/results_summary.md`.
