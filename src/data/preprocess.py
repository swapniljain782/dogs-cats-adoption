"""
Preprocess raw Cats-vs-Dogs images into 224x224 RGB train/val/test splits.

Expected input layout:
    data/raw/cats/*.jpg
    data/raw/dogs/*.jpg

Output layout:
    data/processed/train/{cats,dogs}/*.jpg
    data/processed/val/{cats,dogs}/*.jpg
    data/processed/test/{cats,dogs}/*.jpg
"""
import argparse
import random
import shutil
from pathlib import Path

from PIL import Image

IMG_SIZE_DEFAULT = 224
CLASSES = ["cats", "dogs"]


def list_images(class_dir: Path):
    exts = {".jpg", ".jpeg", ".png"}
    return sorted(p for p in class_dir.iterdir() if p.suffix.lower() in exts)


def split_indices(n: int, train_split: float, val_split: float, seed: int = 42):
    idx = list(range(n))
    random.Random(seed).shuffle(idx)
    n_train = int(n * train_split)
    n_val = int(n * val_split)
    return idx[:n_train], idx[n_train:n_train + n_val], idx[n_train + n_val:]


def resize_and_save(src_path: Path, dst_path: Path, img_size: int):
    with Image.open(src_path) as img:
        img = img.convert("RGB")
        img = img.resize((img_size, img_size), Image.BILINEAR)
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        img.save(dst_path, quality=95)


def preprocess(input_dir: Path, output_dir: Path, img_size: int,
                train_split: float, val_split: float, test_split: float, seed: int = 42):
    assert abs(train_split + val_split + test_split - 1.0) < 1e-6, \
        "splits must sum to 1.0"

    summary = {}
    for cls in CLASSES:
        class_dir = input_dir / cls
        if not class_dir.exists():
            raise FileNotFoundError(f"Expected class folder not found: {class_dir}")

        images = list_images(class_dir)
        if not images:
            raise ValueError(f"No images found in {class_dir}")

        train_idx, val_idx, test_idx = split_indices(
            len(images), train_split, val_split, seed=seed
        )

        for split_name, indices in [("train", train_idx), ("val", val_idx), ("test", test_idx)]:
            for i in indices:
                src = images[i]
                dst = output_dir / split_name / cls / src.name
                resize_and_save(src, dst, img_size)

        summary[cls] = {"train": len(train_idx), "val": len(val_idx), "test": len(test_idx)}

    return summary


def main():
    parser = argparse.ArgumentParser(description="Preprocess Cats vs Dogs dataset")
    parser.add_argument("--input", type=str, default="data/raw")
    parser.add_argument("--output", type=str, default="data/processed")
    parser.add_argument("--img-size", type=int, default=IMG_SIZE_DEFAULT)
    parser.add_argument("--train-split", type=float, default=0.8)
    parser.add_argument("--val-split", type=float, default=0.1)
    parser.add_argument("--test-split", type=float, default=0.1)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    input_dir = Path(args.input)
    output_dir = Path(args.output)

    if output_dir.exists():
        shutil.rmtree(output_dir)

    summary = preprocess(
        input_dir, output_dir, args.img_size,
        args.train_split, args.val_split, args.test_split, args.seed,
    )

    print("Preprocessing complete:")
    for cls, counts in summary.items():
        print(f"  {cls}: {counts}")


if __name__ == "__main__":
    main()
