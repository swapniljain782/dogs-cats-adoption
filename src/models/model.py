"""A small CNN baseline for Cats vs Dogs binary classification (224x224 RGB input)."""
import torch
import torch.nn as nn


class SimpleCNN(nn.Module):
    """~4 conv blocks -> global average pool -> linear head.

    Deliberately small so it trains quickly on CPU for demo purposes, while still
    being a real convolutional baseline (not logistic regression on flattened pixels).
    """

    def __init__(self, num_classes: int = 2):
        super().__init__()
        self.features = nn.Sequential(
            self._conv_block(3, 32),
            self._conv_block(32, 64),
            self._conv_block(64, 128),
            self._conv_block(128, 256),
        )
        self.pool = nn.AdaptiveAvgPool2d(1)
        self.classifier = nn.Sequential(
            nn.Flatten(),
            nn.Dropout(0.3),
            nn.Linear(256, num_classes),
        )

    @staticmethod
    def _conv_block(in_ch: int, out_ch: int) -> nn.Sequential:
        return nn.Sequential(
            nn.Conv2d(in_ch, out_ch, kernel_size=3, padding=1),
            nn.BatchNorm2d(out_ch),
            nn.ReLU(inplace=True),
            nn.MaxPool2d(2),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = self.features(x)
        x = self.pool(x)
        x = self.classifier(x)
        return x


def build_model(num_classes: int = 2) -> SimpleCNN:
    return SimpleCNN(num_classes=num_classes)
