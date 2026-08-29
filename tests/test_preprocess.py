"""Unit tests for src/data/preprocess.py"""
import shutil
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

import sys
sys.path.append(str(Path(__file__).resolve().parents[1]))

from src.data.preprocess import preprocess, split_indices


@pytest.fixture
def tiny_raw_dataset(tmp_path):
    """Create a tiny synthetic raw dataset: 6 cat images + 6 dog images of varying sizes."""
    raw_dir = tmp_path / "raw"
    for cls, color in [("cats", (255, 0, 0)), ("dogs", (0, 0, 255))]:
        class_dir = raw_dir / cls
        class_dir.mkdir(parents=True)
        for i in range(6):
            size = (100 + i * 10, 120 + i * 5)  # non-square, varying sizes
            arr = np.full((size[1], size[0], 3), color, dtype=np.uint8)
            Image.fromarray(arr).save(class_dir / f"{cls}_{i}.jpg")
    return raw_dir


def test_split_indices_proportions():
    train_idx, val_idx, test_idx = split_indices(100, 0.8, 0.1, seed=42)
    assert len(train_idx) == 80
    assert len(val_idx) == 10
    assert len(test_idx) == 10
    # No overlap between splits
    assert set(train_idx).isdisjoint(val_idx)
    assert set(train_idx).isdisjoint(test_idx)
    assert set(val_idx).isdisjoint(test_idx)


def test_preprocess_resizes_to_224_rgb(tmp_path, tiny_raw_dataset):
    output_dir = tmp_path / "processed"
    summary = preprocess(
        tiny_raw_dataset, output_dir, img_size=224,
        train_split=0.5, val_split=0.25, test_split=0.25, seed=0,
    )

    # Every class has counts for every split
    assert set(summary.keys()) == {"cats", "dogs"}
    for cls_counts in summary.values():
        assert cls_counts["train"] + cls_counts["val"] + cls_counts["test"] == 6

    # Spot-check output images: correct size, correct mode
    sample_files = list((output_dir / "train" / "cats").glob("*.jpg"))
    assert len(sample_files) > 0
    with Image.open(sample_files[0]) as img:
        assert img.size == (224, 224)
        assert img.mode == "RGB"


def test_preprocess_raises_on_missing_class(tmp_path):
    raw_dir = tmp_path / "raw_missing"
    (raw_dir / "cats").mkdir(parents=True)
    Image.fromarray(np.zeros((50, 50, 3), dtype=np.uint8)).save(raw_dir / "cats" / "a.jpg")
    # no "dogs" folder created

    with pytest.raises(FileNotFoundError):
        preprocess(raw_dir, tmp_path / "out", 224, 0.8, 0.1, 0.1)
