"""Reproducibility, device selection, and small shared helpers."""
import random

import numpy as np
import torch


def set_seed(seed: int) -> None:
    """Seed Python, NumPy and PyTorch (CPU + CUDA) for reproducible runs.

    Note: full bit-for-bit determinism on GPU is not guaranteed for all cudnn
    kernels, but this removes run-to-run variance from data shuffling/splitting
    and weight init, which is what matters for a reproducible experiment.
    """
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


def get_device() -> torch.device:
    """Return CUDA if available, otherwise CPU (with a clear warning)."""
    if torch.cuda.is_available():
        return torch.device("cuda")
    print("[WARNING] CUDA not available - falling back to CPU. Training will be slow.")
    return torch.device("cpu")


def count_trainable_params(model: torch.nn.Module) -> int:
    return sum(p.numel() for p in model.parameters() if p.requires_grad)
