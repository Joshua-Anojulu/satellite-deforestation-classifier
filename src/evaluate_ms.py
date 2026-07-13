"""
Evaluate the best 13-band multispectral checkpoint on the held-out TEST set.

Mirrors src/evaluate.py (RGB) so the multispectral model is scored on the same
seeded split with the same metrics, enabling a fair RGB-vs-multispectral
comparison for the paper.

Produces:
  * overall test accuracy
  * per-class precision / recall / F1 (sklearn classification_report)
  * a confusion-matrix figure saved into paper/figures/confusion_matrix_ms.png
  * ms_test_metrics.txt / ms_test_metrics.json in the outputs dir

Run from project root (after training src.train_ms):
    python -m src.evaluate_ms
"""
import json

import matplotlib
matplotlib.use("Agg")  # headless
import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns
import torch
from sklearn.metrics import classification_report, confusion_matrix

import config
from src.data_ms import build_ms_dataloaders
from src.model_ms import build_ms_model
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

    if not config.MS_BEST_CKPT.exists():
        raise FileNotFoundError(f"No checkpoint at {config.MS_BEST_CKPT}. Train first (python -m src.train_ms).")

    _, _, test_loader = build_ms_dataloaders()
    model = build_ms_model(in_channels=config.MS_NUM_BANDS).to(device)
    ckpt = torch.load(config.MS_BEST_CKPT, map_location=device)
    model.load_state_dict(ckpt["model_state"])
    val_acc = ckpt.get("val_acc")
    print(f"Loaded MS checkpoint (val_acc={val_acc:.4f})" if val_acc is not None
          else "Loaded MS checkpoint (no val_acc recorded)")

    labels, preds = collect_predictions(model, test_loader, device)
    acc = (labels == preds).mean()
    print(f"\nMS test accuracy: {acc:.4f}  (n={len(labels)})\n")

    report = classification_report(labels, preds, target_names=config.CLASS_NAMES, digits=4)
    print(report)

    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(config.OUTPUT_DIR / "ms_test_metrics.txt", "w") as f:
        f.write(f"MS test accuracy: {acc:.4f}  (n={len(labels)})\n\n{report}\n")
    report_dict = classification_report(
        labels, preds, target_names=config.CLASS_NAMES, output_dict=True)
    with open(config.OUTPUT_DIR / "ms_test_metrics.json", "w") as f:
        json.dump({"test_accuracy": float(acc), "report": report_dict}, f, indent=2)

    cm = confusion_matrix(labels, preds)
    plt.figure(figsize=(10, 8))
    sns.heatmap(cm, annot=True, fmt="d", cmap="Greens",
                xticklabels=config.CLASS_NAMES, yticklabels=config.CLASS_NAMES)
    plt.xlabel("Predicted")
    plt.ylabel("Actual")
    plt.title(f"EuroSAT 13-band Confusion Matrix (test acc = {acc:.3f})")
    plt.xticks(rotation=45, ha="right")
    plt.yticks(rotation=0)
    plt.tight_layout()
    config.FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    fig_path = config.FIGURE_DIR / "confusion_matrix_ms.png"
    plt.savefig(fig_path, dpi=150)
    print(f"\nSaved confusion matrix -> {fig_path}")
    print(f"Saved metrics -> {config.OUTPUT_DIR / 'ms_test_metrics.txt'}")


if __name__ == "__main__":
    main()
