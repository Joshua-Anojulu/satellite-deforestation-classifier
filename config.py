"""
Central configuration for the EuroSAT land-cover classifier and the
deforestation change-detection pipeline.

All paths and hyper-parameters live here so experiments are reproducible and
easy to tweak in one place. Large artifacts (dataset, model checkpoints) are
deliberately kept OUTSIDE the OneDrive-synced project folder to avoid sync
storms; small figures that belong in the paper stay inside the project.
"""
from pathlib import Path

# --- Paths -----------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent

# Dataset lives outside OneDrive (large, regenerable). After extraction this
# folder must contain the 10 class sub-folders (AnnualCrop/, Forest/, ...).
DATA_DIR = Path(r"C:\Users\josha\ml-data\EuroSAT\EuroSAT_RGB")

# Checkpoints can be ~100 MB each -> keep outside OneDrive.
OUTPUT_DIR = Path(r"C:\Users\josha\ml-data\satclf-outputs")

# Figures are small and belong in the paper -> keep inside the project.
FIGURE_DIR = PROJECT_ROOT / "paper" / "figures"

BEST_CKPT = OUTPUT_DIR / "resnet50_eurosat_best.pt"

# --- Reproducibility -------------------------------------------------------
SEED = 42

# --- Data split (matches the guide: 80/10/10) ------------------------------
TRAIN_FRAC = 0.80
VAL_FRAC = 0.10
# test = remainder

# --- ImageNet normalization (required for pretrained ResNet50) -------------
IMAGENET_MEAN = [0.485, 0.456, 0.406]
IMAGENET_STD = [0.229, 0.224, 0.225]

# --- Input / training hyper-parameters -------------------------------------
IMG_SIZE = 224           # ResNet50 native input size
BATCH_SIZE = 64          # comfortable for 8 GB VRAM with AMP
NUM_WORKERS = 4          # DataLoader workers (Windows-safe under __main__ guard)

# Phase 1: train only the new classification head (backbone frozen)
HEAD_EPOCHS = 10
HEAD_LR = 1e-3

# Phase 2: unfreeze everything and fine-tune gently
FINETUNE_EPOCHS = 8
FINETUNE_LR = 1e-4

# --- Class names (alphabetical = torchvision ImageFolder ordering) ---------
# IMPORTANT: ImageFolder assigns labels by sorted folder name. These MUST be
# kept in sorted order to line up with the model's output indices.
CLASS_NAMES = [
    "AnnualCrop",
    "Forest",
    "HerbaceousVegetation",
    "Highway",
    "Industrial",
    "Pasture",
    "PermanentCrop",
    "Residential",
    "River",
    "SeaLake",
]
NUM_CLASSES = len(CLASS_NAMES)

# Which classes count as "forest" for deforestation change-detection.
FOREST_CLASSES = {"Forest"}
# A transition from Forest -> any of these flags a likely deforestation event.
DEFORESTATION_TARGETS = {"AnnualCrop", "Pasture", "Industrial", "Residential", "PermanentCrop"}
