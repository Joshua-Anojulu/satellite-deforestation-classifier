"""
Two-phase transfer-learning training for EuroSAT.

Phase 1: freeze ResNet50 backbone, train only the new head (lr=1e-3).
Phase 2: unfreeze all layers, fine-tune gently (lr=1e-4).

Improvements over the source guide:
  * Reproducible seeding.
  * Mixed-precision (AMP) for speed + lower VRAM on the RTX 4060.
  * Best-model checkpointing by validation accuracy (the guide only described
    early stopping in prose, never saved the best weights).
  * Training history saved to JSON for the paper's learning-curve figure.

Run from the project root:
    python -m src.train
"""
import json
import time

import torch
import torch.nn as nn
import torch.optim as optim

import config
from src.data import build_dataloaders
from src.model import build_model, unfreeze_all
from src.utils import count_trainable_params, get_device, set_seed


def _run_epoch(model, loader, criterion, optimizer, device, scaler, train: bool):
    """Run one epoch. Returns (avg_loss, accuracy)."""
    model.train() if train else model.eval()
    running_loss, correct, total = 0.0, 0, 0

    for images, labels in loader:
        images = images.to(device, non_blocking=True)
        labels = labels.to(device, non_blocking=True)

        with torch.set_grad_enabled(train):
            with torch.autocast(device_type=device.type, enabled=(device.type == "cuda")):
                outputs = model(images)
                loss = criterion(outputs, labels)

            if train:
                optimizer.zero_grad(set_to_none=True)
                scaler.scale(loss).backward()
                scaler.step(optimizer)
                scaler.update()

        running_loss += loss.item() * images.size(0)
        _, predicted = torch.max(outputs, 1)
        correct += (predicted == labels).sum().item()
        total += labels.size(0)

    return running_loss / total, correct / total


def _train_phase(model, loaders, criterion, optimizer, device, scaler,
                 epochs, phase_name, history, best_acc):
    """Train for `epochs`, checkpointing the best val accuracy seen so far."""
    train_loader, val_loader = loaders
    for epoch in range(1, epochs + 1):
        t0 = time.time()
        train_loss, train_acc = _run_epoch(
            model, train_loader, criterion, optimizer, device, scaler, train=True)
        val_loss, val_acc = _run_epoch(
            model, val_loader, criterion, optimizer, device, scaler, train=False)
        dt = time.time() - t0

        history.append({
            "phase": phase_name, "epoch": epoch,
            "train_loss": train_loss, "train_acc": train_acc,
            "val_loss": val_loss, "val_acc": val_acc, "seconds": dt,
        })
        flag = ""
        if val_acc > best_acc:
            best_acc = val_acc
            config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            torch.save({"model_state": model.state_dict(),
                        "val_acc": val_acc,
                        "class_names": config.CLASS_NAMES}, config.BEST_CKPT)
            flag = "  <- best, saved"
        print(f"[{phase_name}] epoch {epoch:2d}/{epochs}  "
              f"train_loss={train_loss:.4f} train_acc={train_acc:.4f}  "
              f"val_loss={val_loss:.4f} val_acc={val_acc:.4f}  ({dt:.0f}s){flag}")
    return best_acc


def main():
    set_seed(config.SEED)
    device = get_device()
    print(f"Device: {device}")

    train_loader, val_loader, test_loader = build_dataloaders()
    print(f"Batches - train: {len(train_loader)}, val: {len(val_loader)}, test: {len(test_loader)}")

    model = build_model().to(device)
    criterion = nn.CrossEntropyLoss()
    scaler = torch.amp.GradScaler(enabled=(device.type == "cuda"))
    history, best_acc = [], 0.0

    # ----- Phase 1: train head only -----
    print(f"\n=== Phase 1: head only ({count_trainable_params(model):,} trainable params) ===")
    optimizer = optim.Adam(filter(lambda p: p.requires_grad, model.parameters()), lr=config.HEAD_LR)
    best_acc = _train_phase(model, (train_loader, val_loader), criterion, optimizer,
                            device, scaler, config.HEAD_EPOCHS, "head", history, best_acc)

    # ----- Phase 2: fine-tune everything -----
    unfreeze_all(model)
    print(f"\n=== Phase 2: fine-tune all ({count_trainable_params(model):,} trainable params) ===")
    optimizer = optim.Adam(model.parameters(), lr=config.FINETUNE_LR)
    best_acc = _train_phase(model, (train_loader, val_loader), criterion, optimizer,
                            device, scaler, config.FINETUNE_EPOCHS, "finetune", history, best_acc)

    # Save training history for the learning-curve figure.
    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(config.OUTPUT_DIR / "training_history.json", "w") as f:
        json.dump(history, f, indent=2)

    print(f"\nBest validation accuracy: {best_acc:.4f}")
    print(f"Best checkpoint: {config.BEST_CKPT}")
    print("Run `python -m src.evaluate` for test-set metrics + confusion matrix.")


if __name__ == "__main__":
    main()
