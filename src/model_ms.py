"""ResNet50 adapted to N-channel (multispectral) input via weight inflation.

EuroSAT all-bands has 13 Sentinel-2 bands. ImageNet weights only cover 3 input
channels, so we replace conv1 with an N-channel layer and initialize it by
inflating the pretrained 3-channel filters: each new input channel is seeded
with the mean of the pretrained RGB filters, scaled by 3/N to preserve the
expected activation magnitude. This retains ImageNet's learned spatial filters
while accepting all spectral bands.
"""
import torch
import torch.nn as nn
from torchvision import models
from torchvision.models import ResNet50_Weights

import config


def build_ms_model(in_channels: int = 13, num_classes: int = None) -> nn.Module:
    num_classes = num_classes or config.NUM_CLASSES
    weights = ResNet50_Weights.DEFAULT
    model = models.resnet50(weights=weights)

    old_conv = model.conv1                       # (64, 3, 7, 7)
    new_conv = nn.Conv2d(in_channels, old_conv.out_channels,
                         kernel_size=old_conv.kernel_size, stride=old_conv.stride,
                         padding=old_conv.padding, bias=old_conv.bias is not None)
    with torch.no_grad():
        mean_rgb = old_conv.weight.mean(dim=1, keepdim=True)            # (64,1,7,7)
        new_conv.weight.copy_(mean_rgb.repeat(1, in_channels, 1, 1) * (3.0 / in_channels))
    model.conv1 = new_conv

    # Freeze backbone; only conv1 (new) and fc (new) train in phase 1.
    for p in model.parameters():
        p.requires_grad = False
    for p in model.conv1.parameters():
        p.requires_grad = True
    model.fc = nn.Linear(model.fc.in_features, num_classes)            # trainable
    return model


def unfreeze_all(model: nn.Module) -> None:
    for p in model.parameters():
        p.requires_grad = True
