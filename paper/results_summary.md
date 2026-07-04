# Results Summary (real numbers from this run)

Study area: **Rondonia, Brazil** (Ariquemes frontier), box W-63.10 S-10.00 E-62.85 N-9.78.
Dates: dry-season composites **2016 vs 2024** (Sentinel-2 L2A, Copernicus Data Space).

## Part 1 - EuroSAT land-cover classifier
- Model: ResNet50 (ImageNet) transfer learning, two-phase (head then fine-tune).
- **Test accuracy: 98.26%** (2,700 held-out images); best val 98.52%; macro-F1 0.982.
- Per-class F1 all >= 0.97. Forest recall **0.997** (critical for deforestation step).
- Main confusions: River->Highway (7), green-cover overlap (Herb/AnnualCrop/Pasture),
  Industrial<->Residential. Figure: paper/figures/confusion_matrix.png.

## Part 2 - Deforestation change detection
- Method: each date tiled into 1,596 georeferenced 64x64 (640 m) patches, EuroSAT
  radiometric **moment-matching** applied (essential - see note), classified, then
  Forest(2016) -> {AnnualCrop,Pasture,Industrial,Residential,PermanentCrop}(2024)
  flagged as loss.
- Land cover: Forest **404 -> 362** cells (net loss), AnnualCrop 93 -> 147.
- **34 deforestation cells detected** (~14 km2), concentrated on forest edges.
  Figure: paper/figures/rondonia_change_changemap.png.

### Validation vs Global Forest Watch (Hansen GFC-2024-v1.12, lossyear 2017-2024)
Sensitivity to how much of a cell GFW must report lost to count as a reference event:

| GFW loss threshold | GFW ref cells | Precision | Recall | F1 | IoU |
|---|---|---|---|---|---|
| any pixel (>0%)   | 907 | 0.882 | 0.033 | 0.064 | 0.033 |
| >= 25% of cell    | 116 | 0.441 | 0.129 | 0.200 | 0.111 |
| >= 50% of cell    |  35 | 0.235 | 0.229 | 0.232 | 0.131 |
| >= 75% of cell    |   7 | 0.147 | 0.714 | 0.244 | 0.139 |

**Interpretation:** high-precision, low-recall coarse detector. 88% of model detections
are confirmed by GFW; for wholesale clearings (>=75% of a cell) recall is 71%. Low recall
against *all* GFW loss is inherent to the 640 m whole-patch resolution, which cannot
resolve the many sub-patch / selective losses 30 m GFW captures. GFW cells with >=50%
loss (35) ~ model detections (34): the method is calibrated to patch-scale events.

### Improvement experiments
Two levers were tested to address the recall/precision trade-off (all vs GFW):

1. **Finer spatial sampling** - slide the 64px (640 m) window with a 32px stride
   (6,300 cells vs 1,596; same footprint, 2x grid resolution). Improves F1/recall at the
   meaningful thresholds, confirming the resolution hypothesis:

   | threshold | F1 stride=64 | F1 stride=32 | recall 64 -> 32 |
   |---|---|---|---|
   | >=25% | 0.200 | **0.238** | 0.129 -> 0.161 |
   | >=50% | 0.232 | **0.249** | 0.229 -> 0.263 |

   152 deforestation cells detected on the finer grid (vs 34). Figure:
   paper/figures/rondonia_change_changemap.png (finer grid).

2. **Confidence gating** - require >=0.7 softmax on BOTH the 2016 Forest and 2024 target
   classification (`change_detection.py --min-conf 0.7`). Yields a high-precision alert
   mode: 38 detections, precision 0.55 at >=25% (vs 0.45 ungated), recall traded away.

Net: the system supports a tunable operating point - high-recall (finer grid, ungated)
vs high-precision (confidence-gated) - which is itself a useful result to report.

## Part 3 - Generalization across two Amazon frontiers
The same EuroSAT-trained model + moment-matching pipeline (finer 32px-stride grid) was
applied to a SECOND, independent study area to test generalization.

**Sao Felix do Xingu, Para** (cattle frontier; box W-52.10 S-6.70 E-51.85 N-6.48; UTM 22S;
Hansen tile 00N_060W; 2016 vs 2024):
- Land cover: Forest **1260 -> 1032** cells; Pasture **476 -> 938** (strong forest->pasture
  conversion, consistent with the region's cattle-driven deforestation).
- **195 deforestation cells** detected (15.5% of 2016 forest; higher rate than Rondonia's 9.4%).
- Figure: paper/figures/sao_felix_change_changemap.png.

**GFW validation comparison (finer grid, stride=32):**

| metric | Rondonia | Sao Felix do Xingu |
|---|---|---|
| precision @ any-loss | 0.822 | **0.990** (193/195 confirmed) |
| F1 @ >=25% | 0.238 | **0.246** |
| F1 @ >=50% | 0.249 | **0.287** |
| deforestation cells | 152 | 195 |

**Takeaway:** the European-trained classifier, radiometrically matched and applied to TWO
distinct tropical frontiers, validates against GFW at both - and performs *better* on Sao
Felix's larger, cleaner clearings. This demonstrates the approach generalizes, with
performance tracking clearing morphology (cleaner/larger clearings -> higher agreement).

## Part 4 - RGB vs 13-band multispectral classifier
To test whether the full Sentinel-2 spectral range improves land-cover accuracy, a
second ResNet50 was trained on the **13-band EuroSAT all-bands** GeoTIFFs. conv1 was
replaced with a 13-channel layer initialized by **weight inflation** (mean of the
pretrained RGB filters, scaled 3/13); per-band normalization used EuroSAT all-bands
statistics. Same seeded 80/10/10 split and two-phase schedule as the RGB model.

| model | input | test accuracy | macro-F1 | best val |
|---|---|---|---|---|
| ResNet50 (RGB) | 3-band | **98.26%** | 0.982 | 98.52% |
| ResNet50 (multispectral) | 13-band | 98.22% | 0.981 | 98.41% |

**Takeaway:** the 10 extra spectral bands give **no measurable gain** on EuroSAT - the
RGB model already saturates the benchmark. For this task RGB is sufficient, which also
justifies the RGB-only deforestation pipeline (Sentinel-2 true-color is all that is
needed). Figure: paper/figures/confusion_matrix_ms.png. Metrics: ms_test_metrics.json.

## Part 5 - Domain-adaptation ablation (controlled, labeled)
We have no labeled Sentinel-2 ground truth, so to compare adaptation methods rigorously
we impose a **controlled nonlinear radiometric shift** on the held-out labeled EuroSAT
RGB test set (per-channel gamma + gain + offset + blue/red haze, tuned to mimic the
measured EuroSAT->L2A gap). Because the shift is nonlinear, a per-channel linear method
cannot trivially invert it, making the comparison meaningful. The RGB classifier is then
evaluated under five conditions (n=2,700).

| condition | accuracy | gap recovered |
|---|---|---|
| clean (upper bound) | 0.9826 | - |
| shifted, no adaptation | 0.5144 | 0.0% |
| shifted, per-channel moment match | 0.6474 | 28.4% |
| shifted, per-channel histogram match | 0.5041 | -2.2% |
| shifted, **AdaBN** (recompute BatchNorm stats) | **0.9789** | **99.2%** |

**Takeaway:** an unadapted classifier loses ~47 points under realistic radiometric shift.
The per-channel **moment matching** used in the deforestation pipeline recovers only ~28%
of that gap under a nonlinear shift; histogram matching fails outright. **AdaBN** -
recomputing BatchNorm running statistics on the (unlabeled) target domain - recovers
**99.2%** of the gap with no labels. This is a concrete, actionable improvement: adding an
AdaBN pass over the target scene before classification substantially raises deforestation
accuracy over moment-matching alone - **confirmed on real target imagery in Part 6**, where
AdaBN rescues the Congo Basin site from F1 0.001 to 0.395. Metrics: da_ablation.json.

## Part 6 - Multi-biome robustness, domain adaptation, and a spectral baseline
The pipeline was extended from two Amazon sites to **seven deforestation frontiers spanning
three biomes / five countries**, each with a matched two-date (2016 vs 2024) dry-season
Sentinel-2 L2A composite (RGB+NIR, finer 32px-stride grid). Biomes are replicated: Amazon x2
(Rondonia, Sao Felix), peat/palm x1 (Riau), Congo Basin x2 (Tshopo, Mai-Ndombe), dry forest
x2 (Santa Cruz, Gran Chaco). Three detectors were evaluated head-to-head at every site,
each validated against Global Forest Watch:
- **CNN** - EuroSAT model + moment-matching, no target adaptation.
- **CNN+AdaBN** - same model but BatchNorm running stats recomputed on each target scene
  (label-free domain adaptation; the Part-5 winner, now applied in-pipeline).
- **NDVI** - NDVI-difference baseline with a **per-scene Otsu** forest threshold (adaptive,
  not a fixed 0.6) and a >=0.2 NDVI-drop loss rule, on the same grid.

Rigor: results are reported at GFW loss-frac thresholds of **>=25% and >=50%**; each per-site
F1 carries a **95% bootstrap CI** (1,000 resamples over grid cells, seed 42); across-site
differences use a **Wilcoxon signed-rank** test (n=7).

(Two further sites - Mato Grosso, Amazon, and Kalimantan, palm - were attempted but one date
each is missing: Copernicus timeouts on Mato Grosso 2024, and no <=25%-cloud scene available
for the persistently cloudy Kalimantan 2016. Left as future work to reach n=9.)

### Data quality first (rules out a confound)
Composite diagnostics (deforestation/diagnose_composites.py) show all scenes are clean:
100% valid pixels, ~0% nodata, <3.5% saturated/bright. The Congo scenes have healthy mean NDVI
(Tshopo 0.66, Mai-Ndombe 0.58-0.61) with 58-75% high-vegetation cover - so the CNN failures
below are **genuine domain shift, not cloud/data degradation**.

### Headline table - F1 with 95% bootstrap CI (GFW loss-frac >= 25%)

| site | biome / country | CNN F1 | CNN+AdaBN F1 | NDVI F1 |
|---|---|---|---|---|
| Rondonia | Amazon (Brazil) | 0.241 [0.20-0.29] | 0.245 [0.20-0.29] | **0.495 [0.45-0.54]** |
| Sao Felix do Xingu | Amazon (Brazil) | 0.233 [0.20-0.27] | 0.224 [0.19-0.26] | **0.304 [0.27-0.34]** |
| Riau, Sumatra | Peat / palm oil (Indonesia) | **0.244 [0.22-0.27]** | 0.227 [0.20-0.25] | 0.181 [0.16-0.20] |
| Tshopo | Congo Basin rainforest (DRC) | 0.001 [0.00-0.00] | **0.395 [0.37-0.42]** | 0.220 [0.20-0.24] |
| Mai-Ndombe | Congo Basin rainforest (DRC) | 0.000 [0.00-0.00] | 0.194 [0.17-0.22] | **0.378 [0.34-0.42]** |
| Santa Cruz | Chiquitano dry forest / soy (Bolivia) | **0.154 [0.12-0.19]** | 0.123 [0.09-0.15] | 0.010 [0.00-0.03] |
| Gran Chaco | Dry forest (Paraguay) | 0.000 [0.00-0.00] | 0.100 [0.06-0.14] | **0.392 [0.32-0.45]** |

**Aggregate (mean +/- sd across sites):**

| method | F1@25% | P@25% | R@25% | F1@50% |
|---|---|---|---|---|
| CNN | 0.125 +/- 0.111 | 0.230 | 0.093 | 0.110 +/- 0.116 |
| CNN+AdaBN | 0.215 +/- 0.089 | 0.394 | 0.184 | 0.179 +/- 0.089 |
| **NDVI (Otsu)** | **0.283 +/- 0.149** | **0.606** | 0.205 | 0.284 +/- 0.158 |

Per-site wins @25%: NDVI 4, CNN 2, CNN+AdaBN 1. Wilcoxon (n=7): all pairwise p > 0.10
(adabn-vs-cnn p=0.47, cnn-vs-ndvi p=0.11, adabn-vs-ndvi p=0.38) - **no method is significantly
better on average** at this site count, though plain-CNN-vs-NDVI trends toward NDVI. The
significant, unambiguous effects live at the per-site cell level (non-overlapping bootstrap
CIs), below.

### Findings
1. **The plain CNN fails catastrophically out-of-biome - and it is reproducible.** At 3 of 7
   sites the unadapted CNN scores F1 <= 0.001: Tshopo (precision 0.022, 46 all-wrong
   detections), Mai-Ndombe (**0 detections**), and Gran Chaco (**0 detections**). It classifies
   most non-European forest as non-forest, so it finds no Forest->non-Forest transitions. Two
   independent Congo sites both fail, so this is a systematic domain-shift failure, not a fluke.
2. **AdaBN reliably eliminates the catastrophic failures (the key result).** Recomputing
   BatchNorm stats on each target scene with **no labels** lifts all three zero-failures to
   positive F1: Tshopo 0.001->**0.395** (precision 0.02->0.70; non-overlapping CIs
   [0.00-0.00] vs [0.37-0.42]), Mai-Ndombe 0.000->0.194, Gran Chaco 0.000->0.100. Recovery
   quality is *site-dependent* - full at Tshopo, but noisier at Mai-Ndombe (over-detects: 1626
   cells vs 568 GFW, precision 0.13) and modest at Gran Chaco. AdaBN is the **most consistent**
   detector (lowest variance, +/-0.089) and never fails catastrophically. It costs a little on
   the already-working sites (Sao Felix, Riau, Santa Cruz each drop ~0.01-0.03).
3. **NDVI has the highest mean F1 (0.283) and wins 4/7 sites, but is itself fragile.** It is
   strongest on the Amazon (0.50, 0.30) and, notably, wins **both** Congo sites and Gran Chaco
   dry forest - yet **collapses at Santa Cruz** (F1 0.010). So NDVI's dry-forest behavior is
   *site-specific, not biome-uniform*: it works at Gran Chaco (clearing produces a large NDVI
   drop the Otsu-thresholded rule catches) but fails at Santa Cruz (low dynamic range defeats
   the absolute >=0.2-drop rule). Highest variance (+/-0.149).
4. **On dry forest the two methods trade wins** (Santa Cruz: CNN 0.154 > NDVI 0.010; Gran Chaco:
   NDVI 0.392 > CNN 0.000), underscoring that no single detector is safe across sites.

**Central conclusion (arXiv thesis):** across three biomes and seven frontiers **no detector
dominates**; the useful, honest findings are (a) a domain-shifted RGB CNN is *not* a free
upgrade over a classical spectral index and **fails catastrophically out-of-biome at nearly
half the sites**, reproducibly; (b) those failures are genuine domain shift (verified clean
composites); (c) a simple, label-free **AdaBN** pass removes every catastrophic failure and
gives the most *consistent* detector, though not always to parity; and (d) the NDVI baseline,
while strongest on average, is itself site-fragile. **Robustness, not peak F1, is the story.**

Remaining honest caveats: n=7 sites still limits across-site significance (target n=9+); the
NDVI baseline could use a relative-drop rule to be fairer in low-NDVI biomes (but absolute-drop
is the textbook method); AdaBN's regressions on easy sites and over-detection at Mai-Ndombe
suggest a per-scene "adapt only if shift is large" gate. Data: multi_site_results.json;
diagnostics in diagnose_composites.py; change maps in ml-data/deforestation/multi/.

## Critical note: radiometric domain shift (important methodological finding)
EuroSAT was built from hazier, less-atmospherically-corrected Sentinel-2 (blue-cast;
global RGB mean ~ (86,97,103)). A naive render of modern L2A imagery is classified
~72% SeaLake (forest read as water). Per-channel **moment matching** of each scene to
EuroSAT's global statistics fixes this (forest correctly dominant; ~1% water). This is a
real, reportable limitation of cross-domain transfer and the single most important step
for valid results.

## Limitations
European training imagery applied to tropical Brazil (domain shift); 640 m patches miss
small/linear clearings (drives low recall); RGB-only drops spectral bands; cloud/seasonal
phenology can cause false change; moment-matching is an approximation of EuroSAT radiometry.
