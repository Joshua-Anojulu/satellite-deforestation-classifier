"""
Download the EuroSAT RGB dataset (~90 MB, 27,000 images, 10 classes) and
arrange it at config.DATA_DIR with one sub-folder per class.

Uses torchvision's built-in EuroSAT downloader so we rely on the URL the
torchvision maintainers keep current, rather than hardcoding a link that may
go stale (the original guide's host has had downtime).

Run from the project root:
    python download_data.py
"""
import shutil
from pathlib import Path

from torchvision.datasets import EuroSAT

import config

EXPECTED = set(config.CLASS_NAMES)


def _find_class_root(start: Path) -> Path:
    """Find the directory that directly contains the 10 EuroSAT class folders."""
    for d in [start, *[p for p in start.rglob("*") if p.is_dir()]]:
        subdirs = {p.name for p in d.iterdir() if p.is_dir()}
        if EXPECTED.issubset(subdirs):
            return d
    raise RuntimeError(f"Could not locate the 10 class folders under {start}")


def main():
    target = config.DATA_DIR
    if target.exists() and EXPECTED.issubset({p.name for p in target.iterdir() if p.is_dir()}):
        counts = {c: len(list((target / c).glob('*'))) for c in config.CLASS_NAMES}
        print(f"Dataset already present at {target}")
        print(f"Total images: {sum(counts.values())}")
        return

    download_root = target.parent / "_download"
    download_root.mkdir(parents=True, exist_ok=True)
    print(f"Downloading EuroSAT into {download_root} (this may take a minute)...")
    EuroSAT(root=str(download_root), download=True)  # fetch + extract

    class_root = _find_class_root(download_root)
    print(f"Found class folders at: {class_root}")

    target.mkdir(parents=True, exist_ok=True)
    for cls in config.CLASS_NAMES:
        src = class_root / cls
        dst = target / cls
        if not dst.exists():
            shutil.move(str(src), str(dst))

    counts = {c: len(list((target / c).glob('*'))) for c in config.CLASS_NAMES}
    total = sum(counts.values())
    print(f"\nArranged dataset at {target}")
    for c in config.CLASS_NAMES:
        print(f"  {c:22s}: {counts[c]}")
    print(f"  {'TOTAL':22s}: {total}")
    if total != 27000:
        print(f"[WARNING] Expected 27,000 images, found {total}.")

    # Clean up the now-empty download scratch area.
    shutil.rmtree(download_root, ignore_errors=True)


if __name__ == "__main__":
    main()
