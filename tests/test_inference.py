"""Unit tests for src/utils/inference.py and src/models/model.py"""
import io
from pathlib import Path

import numpy as np
import pytest
import torch
from PIL import Image

import sys
sys.path.append(str(Path(__file__).resolve().parents[1]))

from src.models.model import build_model
from src.utils.inference import predict_image_bytes, load_model


@pytest.fixture
def dummy_model():
    """An untrained model is fine for testing output shape/validity, not accuracy."""
    model = build_model(num_classes=2)
    model.eval()
    return model


@pytest.fixture
def sample_image_bytes():
    arr = np.random.randint(0, 255, (200, 180, 3), dtype=np.uint8)
    img = Image.fromarray(arr)
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def test_model_forward_output_shape(dummy_model):
    x = torch.randn(4, 3, 224, 224)
    out = dummy_model(x)
    assert out.shape == (4, 2)


def test_predict_image_bytes_returns_valid_result(dummy_model, sample_image_bytes):
    result = predict_image_bytes(dummy_model, sample_image_bytes)

    assert result["label"] in ("cats", "dogs")
    assert 0.0 <= result["probability"] <= 1.0
    assert set(result["probabilities"].keys()) == {"cats", "dogs"}

    total_prob = sum(result["probabilities"].values())
    assert abs(total_prob - 1.0) < 1e-4


def test_load_model_raises_on_missing_checkpoint(tmp_path):
    missing_path = tmp_path / "does_not_exist.pt"
    with pytest.raises(FileNotFoundError):
        load_model(str(missing_path))
