# Research Paper Scaffold

Working title: *A Lightweight Transfer-Learning Approach to Sentinel-2 Land-Cover
Classification for Reproducible Deforestation Detection*

> Fill bracketed `[...]` placeholders from your actual run outputs
> (`outputs/test_metrics.txt`, the confusion matrix, and the change-detection /
> GFW validation results). Target venues from the guide: Journal of Emerging
> Investigators, Journal of Student Research, Columbia Junior Science Journal.

---

## Abstract (150-250 words)
- Problem: deforestation monitoring needs efficient, reproducible automated tools.
- Method: transfer learning with ResNet50 (ImageNet) on EuroSAT RGB; applied to
  two-date Sentinel-2 imagery of [STUDY AREA] for change detection.
- Results: test accuracy [XX.X%]; detected [N] forest-loss cells; agreement with
  Global Forest Watch precision [P], recall [R], F1 [F1].
- Conclusion: a lightweight, fully reproducible pipeline approximates an
  industry reference; limitations and next steps identified.

## 1. Introduction
- Why deforestation monitoring matters (cite global forest-loss statistics).
- Existing methods: manual interpretation; Global Forest Watch / Hansen GFC.
- Contribution: a reproducible, GPU-light CNN pipeline validated against
  official data, with explicit methodological corrections (see Methods).

## 2. Methods
- **Dataset:** EuroSAT (Helber et al., 2019, IEEE JSTARS), 27,000 Sentinel-2
  patches, 10 classes, 64x64 px @ 10 m, RGB version.
- **Split:** seeded 80/10/10 train/val/test; per-split transforms so
  augmentation never contaminates evaluation (a common tutorial bug, corrected).
- **Model:** ResNet50, ImageNet weights (`weights=DEFAULT`), final layer ->
  10 classes. Phase 1 trains the head (lr=1e-3, [HEAD_EPOCHS] epochs); Phase 2
  fine-tunes all layers (lr=1e-4, [FT_EPOCHS] epochs). AMP; Adam; CE loss.
  Best checkpoint by validation accuracy.
- **Hardware/Reproducibility:** NVIDIA RTX 4060 (8 GB), CUDA 12.6, PyTorch
  2.12, seed=42. [Total training time: ~XX min.]
- **Change detection:** Sentinel-2 L2A true-color for [STUDY AREA] at [YEAR_A]
  and [YEAR_B] (Copernicus Data Space Ecosystem); tiled into georeferenced
  64x64 patches; per-patch classification; Forest->{AnnualCrop, Pasture,
  Industrial, Residential, PermanentCrop} flagged as loss.
- **Validation:** Hansen GFC lossyear raster aggregated to the patch grid;
  precision/recall/F1/IoU vs model detections.

## 3. Results
- Overall **test accuracy 98.26%** (2,700 held-out images); best val 98.52%.
  Macro-avg F1 0.982. Per-class F1 all >= 0.97 (Table 1).
  - Near-perfect: SeaLake 0.998, Forest 0.995, Residential 0.986, AnnualCrop 0.985.
  - Lowest: PermanentCrop 0.969, River 0.971, Highway 0.972.
- Confusion matrix (Fig. 1 = paper/figures/confusion_matrix.png). Observed
  confusions match expectation: **River->Highway (7)** (thin linear features);
  **HerbaceousVegetation->PermanentCrop/Forest/Pasture (9)** and
  **AnnualCrop->PermanentCrop (4)** (green ground cover); **Industrial<->
  Residential (4)** (built-up). Forest recall 0.997 (296/297) — critical for the
  downstream deforestation task.
- Land-cover maps for both dates; change map (Fig. 2).
- [N] detected loss cells; GFW agreement: P=[..], R=[..], F1=[..], IoU=[..].

## 4. Discussion
- What worked / what didn't and why.
- Limitations (state honestly):
  - Trained on European scenes (EuroSAT); applied to [STUDY AREA] -> domain shift.
  - Radiometric mismatch between EuroSAT JPEGs and Sentinel-2 reflectance
    (mitigated by true-color rescaling, but approximate).
  - 64x64 @ 10 m patches miss small/linear clearings.
  - RGB-only discards informative spectral bands.
  - Cloud/seasonal effects can cause false change (crops, deciduous phenology).

## 5. Conclusion & Future Work
- Summary of findings.
- Next steps: 13-band multispectral input; region-matched training data;
  multi-temporal sequences rather than two snapshots; finer patch size.

## References
- Helber et al., "EuroSAT: A Novel Dataset and Deep Learning Benchmark for Land
  Use and Land Cover Classification," IEEE JSTARS, 2019.
- Hansen et al., "High-Resolution Global Maps of 21st-Century Forest Cover
  Change," Science, 2013. (Global Forest Watch data source.)
- He et al., "Deep Residual Learning for Image Recognition" (ResNet), 2016.
