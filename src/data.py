"""
Dataset loading, reproducible splitting, and preprocessing.

This module deliberately FIXES a bug present in many EuroSAT tutorials
(including the source guide for this project):

    full = datasets.ImageFolder(root, transform=train_transform)
    train, val, test = random_split(full, [...])

Because the transform is attached to the *underlying* dataset, ALL three
splits share it. That means either:
  * validation/test images get random flips (wrong - eval must be deterministic), or
  * training images get no augmentation.

The fix below loads ImageFolder WITHOUT a transform (so the base returns PIL
images), splits indices reproducibly, then wraps each split with its own
transform. Training gets augmentation; val/test do not.
"""
from typing import Tuple

import torch
from torch.utils.data import DataLoader, Dataset, random_split
from torchvision import datasets, transforms

import config


# --- Transforms ------------------------------------------------------------
def build_transforms() -> Tuple[transforms.Compose, transforms.Compose]:
    """Return (train_transform, eval_transform).

    Train: resize -> random H/V flip (valid for nadir satellite imagery, which
    has no canonical orientation) -> tensor -> ImageNet normalize.
    Eval:  resize -> tensor -> ImageNet normalize (no augmentation).
    """
    train_transform = transforms.Compose([
        transforms.Resize((config.IMG_SIZE, config.IMG_SIZE)),
        transforms.RandomHorizontalFlip(),
        transforms.RandomVerticalFlip(),
        transforms.ToTensor(),
        transforms.Normalize(mean=config.IMAGENET_MEAN, std=config.IMAGENET_STD),
    ])
    eval_transform = transforms.Compose([
        transforms.Resize((config.IMG_SIZE, config.IMG_SIZE)),
        transforms.ToTensor(),
        transforms.Normalize(mean=config.IMAGENET_MEAN, std=config.IMAGENET_STD),
    ])
    return train_transform, eval_transform


class _SplitDataset(Dataset):
    """Applies a per-split transform to a subset of an ImageFolder.

    Holds the base ImageFolder (loaded WITHOUT a transform) plus the list of
    sample indices belonging to this split, and applies its own transform on
    the fly. This is what keeps augmentation out of the eval splits.
    """

    def __init__(self, base: datasets.ImageFolder, indices, transform):
        self.base = base
        self.indices = list(indices)
        self.transform = transform

    def __len__(self) -> int:
        return len(self.indices)

    def __getitem__(self, i):
        path, label = self.base.samples[self.indices[i]]
        img = self.base.loader(path)  # PIL.Image (RGB)
        if self.transform is not None:
            img = self.transform(img)
        return img, label


def build_datasets():
    """Load EuroSAT and return reproducible (train, val, test) datasets."""
    if not config.DATA_DIR.exists():
        raise FileNotFoundError(
            f"EuroSAT not found at {config.DATA_DIR}. Run download_data.py first."
        )

    # No transform here: base returns PIL images so each split can transform itself.
    base = datasets.ImageFolder(root=str(config.DATA_DIR))

    # Sanity check: folder ordering must match config.CLASS_NAMES exactly,
    # otherwise predicted indices won't line up with class names.
    if base.classes != config.CLASS_NAMES:
        raise ValueError(
            "ImageFolder class order does not match config.CLASS_NAMES.\n"
            f"  Found:    {base.classes}\n"
            f"  Expected: {config.CLASS_NAMES}\n"
            "Check the dataset folder names."
        )

    n = len(base)
    n_train = int(config.TRAIN_FRAC * n)
    n_val = int(config.VAL_FRAC * n)
    n_test = n - n_train - n_val

    # Reproducible split via a seeded generator.
    generator = torch.Generator().manual_seed(config.SEED)
    train_idx, val_idx, test_idx = random_split(
        range(n), [n_train, n_val, n_test], generator=generator
    )

    train_transform, eval_transform = build_transforms()
    train_ds = _SplitDataset(base, train_idx, train_transform)
    val_ds = _SplitDataset(base, val_idx, eval_transform)
    test_ds = _SplitDataset(base, test_idx, eval_transform)
    return train_ds, val_ds, test_ds


def build_dataloaders():
    """Return (train_loader, val_loader, test_loader)."""
    train_ds, val_ds, test_ds = build_datasets()
    common = dict(num_workers=config.NUM_WORKERS, pin_memory=True)
    train_loader = DataLoader(train_ds, batch_size=config.BATCH_SIZE, shuffle=True, **common)
    val_loader = DataLoader(val_ds, batch_size=config.BATCH_SIZE, shuffle=False, **common)
    test_loader = DataLoader(test_ds, batch_size=config.BATCH_SIZE, shuffle=False, **common)
    return train_loader, val_loader, test_loader
