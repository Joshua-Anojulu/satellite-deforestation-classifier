"""ResNet50 transfer-learning model for EuroSAT.

Uses the current torchvision weights API (`weights=ResNet50_Weights.DEFAULT`)
instead of the deprecated `pretrained=True` from the source guide.
"""
import torch.nn as nn
from torchvision import models
from torchvision.models import ResNet50_Weights

import config


def build_model() -> nn.Module:
    """ResNet50 pretrained on ImageNet with the final layer replaced for
    `config.NUM_CLASSES` outputs. Backbone starts frozen (Phase 1)."""
    weights = ResNet50_Weights.DEFAULT  # current best ImageNet weights
    model = models.resnet50(weights=weights)

    # Freeze the entire backbone first.
    for param in model.parameters():
        param.requires_grad = False

    # Replace the classification head (trainable by default).
    num_features = model.fc.in_features
    model.fc = nn.Linear(num_features, config.NUM_CLASSES)
    return model


def unfreeze_all(model: nn.Module) -> None:
    """Unfreeze every parameter for Phase 2 fine-tuning."""
    for param in model.parameters():
        param.requires_grad = True
