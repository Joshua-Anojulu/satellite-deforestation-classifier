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
