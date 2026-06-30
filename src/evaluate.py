"""
Evaluate the best checkpoint on the held-out TEST set.

Produces:
  * overall test accuracy
  * per-class precision / recall / F1 (sklearn classification_report)
  * a confusion-matrix figure saved into paper/figures/

Run from project root (after training):
    python -m src.evaluate
"""
import json

import matplotlib
matplotlib.use("Agg")  # headless: write files, don't open a window
import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns
import torch
from sklearn.metrics import classification_report, confusion_matrix

import config
from src.data import build_dataloaders
from src.model import build_model
from src.utils import get_device, set_seed


def collect_predictions(model, loader, device):
    model.eval()
    all_preds, all_labels = [], []
    with torch.no_grad():
        for images, labels in loader:
            images = images.to(device, non_blocking=True)
            with torch.autocast(device_type=device.type, enabled=(device.type == "cuda")):
                outputs = model(images)
            _, predicted = torch.max(outputs, 1)
            all_preds.extend(predicted.cpu().numpy())
            all_labels.extend(labels.numpy())
    return np.array(all_labels), np.array(all_preds)


def main():
    set_seed(config.SEED)  # same seed -> identical split -> same held-out test set
    device = get_device()

    if not config.BEST_CKPT.exists():
        raise FileNotFoundError(f"No checkpoint at {config.BEST_CKPT}. Train first.")

    _, _, test_loader = build_dataloaders()
    model = build_model().to(device)
    ckpt = torch.load(config.BEST_CKPT, map_location=device)
    model.load_state_dict(ckpt["model_state"])
    print(f"Loaded checkpoint (val_acc={ckpt.get('val_acc'):.4f})")

    labels, preds = collect_predictions(model, test_loader, device)
    acc = (labels == preds).mean()
    print(f"\nTest accuracy: {acc:.4f}  (n={len(labels)})\n")

    report = classification_report(labels, preds, target_names=config.CLASS_NAMES, digits=4)
    print(report)

    # Persist text metrics for the paper.
    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(config.OUTPUT_DIR / "test_metrics.txt", "w") as f:
        f.write(f"Test accuracy: {acc:.4f}  (n={len(labels)})\n\n{report}\n")
    report_dict = classification_report(
        labels, preds, target_names=config.CLASS_NAMES, output_dict=True)
    with open(config.OUTPUT_DIR / "test_metrics.json", "w") as f:
        json.dump({"test_accuracy": float(acc), "report": report_dict}, f, indent=2)

    # Confusion matrix figure.
    cm = confusion_matrix(labels, preds)
    plt.figure(figsize=(10, 8))
    sns.heatmap(cm, annot=True, fmt="d", cmap="Blues",
                xticklabels=config.CLASS_NAMES, yticklabels=config.CLASS_NAMES)
    plt.xlabel("Predicted")
    plt.ylabel("Actual")
    plt.title(f"EuroSAT Confusion Matrix (test acc = {acc:.3f})")
    plt.xticks(rotation=45, ha="right")
    plt.yticks(rotation=0)
    plt.tight_layout()
    config.FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    fig_path = config.FIGURE_DIR / "confusion_matrix.png"
    plt.savefig(fig_path, dpi=150)
    print(f"\nSaved confusion matrix -> {fig_path}")
    print(f"Saved metrics -> {config.OUTPUT_DIR / 'test_metrics.txt'}")


if __name__ == "__main__":
    main()
