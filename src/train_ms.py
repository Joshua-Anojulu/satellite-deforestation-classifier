"""
Two-phase training for the 13-band multispectral EuroSAT classifier.

Phase 1: train new conv1 + head (rest frozen). Phase 2: fine-tune all.
Saves the best checkpoint by val accuracy to config.MS_BEST_CKPT and reports
test-set accuracy so it can be compared to the RGB baseline.

Run:  python -m src.train_ms
"""
import json
import time

import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from sklearn.metrics import classification_report

import config
from src.data_ms import build_ms_dataloaders
from src.model_ms import build_ms_model, unfreeze_all
from src.utils import get_device, set_seed


def _run_epoch(model, loader, criterion, optimizer, device, scaler, train):
    model.train() if train else model.eval()
    loss_sum, correct, total = 0.0, 0, 0
    for x, y in loader:
        x = x.to(device, non_blocking=True)
        y = y.to(device, non_blocking=True)
        with torch.set_grad_enabled(train):
            with torch.autocast(device_type=device.type, enabled=(device.type == "cuda")):
                out = model(x)
                loss = criterion(out, y)
            if train:
                optimizer.zero_grad(set_to_none=True)
                scaler.scale(loss).backward()
                scaler.step(optimizer)
                scaler.update()
        loss_sum += loss.item() * x.size(0)
        correct += (out.argmax(1) == y).sum().item()
        total += y.size(0)
    return loss_sum / total, correct / total


def _phase(model, tr, va, criterion, optimizer, device, scaler, epochs, name, hist, best):
    for e in range(1, epochs + 1):
        t0 = time.time()
        trl, tra = _run_epoch(model, tr, criterion, optimizer, device, scaler, True)
        vol, voa = _run_epoch(model, va, criterion, optimizer, device, scaler, False)
        hist.append({"phase": name, "epoch": e, "train_acc": tra, "val_acc": voa})
        flag = ""
        if voa > best:
            best = voa
            config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            torch.save({"model_state": model.state_dict(), "val_acc": voa,
                        "class_names": config.CLASS_NAMES, "in_channels": config.MS_NUM_BANDS},
                       config.MS_BEST_CKPT)
            flag = "  <- best, saved"
        print(f"[{name}] {e:2d}/{epochs}  train_acc={tra:.4f}  val_acc={voa:.4f}  "
              f"({time.time()-t0:.0f}s){flag}")
    return best


def main():
    set_seed(config.SEED)
    device = get_device()
    print(f"Device: {device}  | 13-band multispectral")
    tr, va, te = build_ms_dataloaders()
    print(f"Batches - train {len(tr)}, val {len(va)}, test {len(te)}")

    model = build_ms_model(in_channels=config.MS_NUM_BANDS).to(device)
    criterion = nn.CrossEntropyLoss()
    scaler = torch.amp.GradScaler(enabled=(device.type == "cuda"))
    hist, best = [], 0.0

    print("\n=== Phase 1: conv1 + head ===")
    opt = optim.Adam(filter(lambda p: p.requires_grad, model.parameters()), lr=config.HEAD_LR)
    best = _phase(model, tr, va, criterion, opt, device, scaler, config.HEAD_EPOCHS, "head", hist, best)

    unfreeze_all(model)
    print("\n=== Phase 2: fine-tune all ===")
    opt = optim.Adam(model.parameters(), lr=config.FINETUNE_LR)
    best = _phase(model, tr, va, criterion, opt, device, scaler, config.FINETUNE_EPOCHS, "finetune", hist, best)

    # Test-set evaluation with best checkpoint.
    ck = torch.load(config.MS_BEST_CKPT, map_location=device)
    model.load_state_dict(ck["model_state"])
    model.eval()
    preds, labels = [], []
    with torch.no_grad():
        for x, y in te:
            x = x.to(device)
            with torch.autocast(device_type=device.type, enabled=(device.type == "cuda")):
                out = model(x)
            preds.extend(out.argmax(1).cpu().numpy()); labels.extend(y.numpy())
    preds, labels = np.array(preds), np.array(labels)
    acc = (preds == labels).mean()
    print(f"\nMS best val acc: {best:.4f}")
    print(f"MS TEST accuracy: {acc:.4f}  (n={len(labels)})\n")
    rep = classification_report(labels, preds, target_names=config.CLASS_NAMES, digits=4)
    print(rep)
    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(config.OUTPUT_DIR / "ms_test_metrics.txt", "w") as f:
        f.write(f"MS test accuracy: {acc:.4f} (n={len(labels)})\n\n{rep}\n")
    with open(config.OUTPUT_DIR / "ms_training_history.json", "w") as f:
        json.dump(hist, f, indent=2)


if __name__ == "__main__":
    main()
