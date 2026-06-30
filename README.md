# Satellite Land-Cover Classifier & Deforestation Detector

Transfer-learning (ResNet50 / ImageNet) land-cover classifier trained on
**EuroSAT** (Sentinel-2, 10 classes), then applied to multi-date Sentinel-2
imagery to detect **forest loss**, validated against **Global Forest Watch**.

Built for a research-paper / science-fair submission. Trains locally on an
NVIDIA GPU (no Google Colab required).

## What's different from the typical tutorial

This project intentionally corrects several issues common to EuroSAT tutorials:

| Issue in typical guides | Fix here |
|---|---|
| `ImageFolder(transform=...)` then `random_split` leaks augmentation into val/test | Per-split transforms via a wrapper dataset (`src/data.py`) |
| Deprecated `resnet50(pretrained=True)` | Current `weights=ResNet50_Weights.DEFAULT` API |
| No fixed seed (irreproducible splits/results) | `set_seed()` everywhere; seeded split generator |
| Early stopping described but best model never saved | Best-checkpoint-by-val-accuracy in `src/train.py` |
| Retired `scihub.copernicus.eu` for imagery | Copernicus **Data Space Ecosystem** (`deforestation/`) |

## Layout

```
config.py              Central paths + hyper-parameters
download_data.py       Fetch + arrange EuroSAT (~90 MB)
src/
  data.py              Seeded split + per-split transforms
  model.py             ResNet50 transfer-learning model
  train.py             Two-phase training (freeze head -> fine-tune)
  evaluate.py          Test metrics + confusion matrix
  utils.py             Seeding / device helpers
deforestation/         Change-detection pipeline (Sentinel-2 -> forest loss)
paper/                 Paper outline + figures
```

Code lives here (OneDrive-backed). The **dataset**, **checkpoints**, and
training history live outside OneDrive (see `config.py`) to avoid sync storms.

## Setup

PyTorch is installed with the CUDA build matching the GPU driver
(CUDA <= 12.7 here -> cu126):

```powershell
# venv already created at C:\Users\josha\.venvs\satclf
& C:\Users\josha\.venvs\satclf\Scripts\Activate.ps1
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu126
pip install scikit-learn matplotlib seaborn numpy pandas tqdm rasterio
```

## Run

```powershell
python download_data.py     # one-time dataset download
python -m src.train         # two-phase training, saves best checkpoint
python -m src.evaluate      # test metrics + confusion_matrix.png
```

## Deforestation pipeline

See `deforestation/README.md`. Requires a (free) Copernicus Data Space
account and a chosen study area.
