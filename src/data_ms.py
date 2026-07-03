"""Multispectral (13-band) EuroSAT loading, reproducible split, per-band norm.

Mirrors src/data.py but reads 13-band uint16 GeoTIFFs and normalizes per band
with EuroSAT all-bands statistics. Same seeded 80/10/10 split and per-split
transform discipline (augmentation only on train).
"""
import glob

import numpy as np
import rasterio
import torch
from torch.utils.data import DataLoader, Dataset, random_split

import config

MEAN = np.array(config.MS_BAND_MEAN, dtype=np.float32)[:, None, None]
STD = np.array(config.MS_BAND_STD, dtype=np.float32)[:, None, None]


def _list_samples():
    """Return (filepaths, labels) sorted by class so labels match CLASS_NAMES order."""
    files, labels = [], []
    for idx, cls in enumerate(config.CLASS_NAMES):
        fs = sorted(glob.glob(str(config.MS_DATA_DIR / cls / "*.tif")))
        files += fs
        labels += [idx] * len(fs)
    if not files:
        raise FileNotFoundError(f"No MS tifs under {config.MS_DATA_DIR}")
    return files, labels


def _load_norm(path: str) -> np.ndarray:
    """Read a 13-band tif -> normalized float32 (13, 64, 64)."""
    with rasterio.open(path) as s:
        a = s.read().astype(np.float32)            # (13,64,64)
    return (a - MEAN) / STD


class _MSDataset(Dataset):
    def __init__(self, files, labels, indices, augment: bool):
        self.files = files
        self.labels = labels
        self.indices = list(indices)
        self.augment = augment

    def __len__(self):
        return len(self.indices)

    def __getitem__(self, i):
        j = self.indices[i]
        x = _load_norm(self.files[j])              # (13,64,64)
        if self.augment:
            if np.random.rand() < 0.5:
                x = x[:, :, ::-1]
            if np.random.rand() < 0.5:
                x = x[:, ::-1, :]
        x = torch.from_numpy(np.ascontiguousarray(x))
        # ResNet50 expects 224x224; upsample (bilinear) to match RGB pipeline.
        x = torch.nn.functional.interpolate(
            x.unsqueeze(0), size=(config.IMG_SIZE, config.IMG_SIZE),
            mode="bilinear", align_corners=False).squeeze(0)
        return x, self.labels[j]


def build_ms_datasets():
    files, labels = _list_samples()
    n = len(files)
    n_train = int(config.TRAIN_FRAC * n)
    n_val = int(config.VAL_FRAC * n)
    n_test = n - n_train - n_val
    g = torch.Generator().manual_seed(config.SEED)
    tr, va, te = random_split(range(n), [n_train, n_val, n_test], generator=g)
    return (_MSDataset(files, labels, tr, augment=True),
            _MSDataset(files, labels, va, augment=False),
            _MSDataset(files, labels, te, augment=False))


def build_ms_dataloaders():
    tr, va, te = build_ms_datasets()
    common = dict(num_workers=config.NUM_WORKERS, pin_memory=True)
    return (DataLoader(tr, batch_size=config.BATCH_SIZE, shuffle=True, **common),
            DataLoader(va, batch_size=config.BATCH_SIZE, shuffle=False, **common),
            DataLoader(te, batch_size=config.BATCH_SIZE, shuffle=False, **common))
