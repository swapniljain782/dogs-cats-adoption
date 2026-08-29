"""PyTorch Dataset for the preprocessed Cats vs Dogs splits."""
from pathlib import Path

from PIL import Image
from torch.utils.data import Dataset, DataLoader
from torchvision import transforms

CLASS_TO_IDX = {"cats": 0, "dogs": 1}
IDX_TO_CLASS = {v: k for k, v in CLASS_TO_IDX.items()}

IMAGENET_MEAN = [0.485, 0.456, 0.406]
IMAGENET_STD = [0.229, 0.224, 0.225]


def build_transforms(img_size: int = 224, train: bool = False):
    if train:
        return transforms.Compose([
            transforms.Resize((img_size, img_size)),
            transforms.RandomHorizontalFlip(p=0.5),
            transforms.RandomRotation(15),
            transforms.ColorJitter(brightness=0.2, contrast=0.2, saturation=0.2),
            transforms.ToTensor(),
            transforms.Normalize(IMAGENET_MEAN, IMAGENET_STD),
        ])
    return transforms.Compose([
        transforms.Resize((img_size, img_size)),
        transforms.ToTensor(),
        transforms.Normalize(IMAGENET_MEAN, IMAGENET_STD),
    ])


class CatsDogsDataset(Dataset):
    def __init__(self, root: str, split: str, img_size: int = 224, train: bool = False):
        self.root = Path(root) / split
        self.samples = []
        for cls, label in CLASS_TO_IDX.items():
            class_dir = self.root / cls
            if not class_dir.exists():
                continue
            for p in sorted(class_dir.iterdir()):
                if p.suffix.lower() in {".jpg", ".jpeg", ".png"}:
                    self.samples.append((p, label))
        self.transform = build_transforms(img_size, train=train)

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        path, label = self.samples[idx]
        with Image.open(path) as img:
            img = img.convert("RGB")
            img = self.transform(img)
        return img, label


def get_dataloaders(data_dir: str, img_size: int = 224, batch_size: int = 32, num_workers: int = 2):
    train_ds = CatsDogsDataset(data_dir, "train", img_size, train=True)
    val_ds = CatsDogsDataset(data_dir, "val", img_size, train=False)
    test_ds = CatsDogsDataset(data_dir, "test", img_size, train=False)

    train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=True, num_workers=num_workers)
    val_loader = DataLoader(val_ds, batch_size=batch_size, shuffle=False, num_workers=num_workers)
    test_loader = DataLoader(test_ds, batch_size=batch_size, shuffle=False, num_workers=num_workers)

    return train_loader, val_loader, test_loader
