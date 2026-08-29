"""Model loading + single-image inference used by the FastAPI service."""
import io
from pathlib import Path

import torch
import torch.nn.functional as F
from PIL import Image

import sys
sys.path.append(str(Path(__file__).resolve().parents[2]))

from src.data.dataset import build_transforms, IDX_TO_CLASS
from src.models.model import build_model

_DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")


def load_model(model_path: str = "artifacts/model.pt"):
    """Load a trained SimpleCNN checkpoint. Raises FileNotFoundError if missing."""
    path = Path(model_path)
    if not path.exists():
        raise FileNotFoundError(
            f"Model checkpoint not found at {path}. Run src/models/train.py first."
        )
    model = build_model(num_classes=2)
    state_dict = torch.load(path, map_location=_DEVICE)
    model.load_state_dict(state_dict)
    model.to(_DEVICE)
    model.eval()
    return model


def predict_image_bytes(model, image_bytes: bytes, img_size: int = 224) -> dict:
    """Run inference on raw image bytes. Returns {label, probability, probabilities}."""
    transform = build_transforms(img_size=img_size, train=False)
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    tensor = transform(img).unsqueeze(0).to(_DEVICE)

    with torch.no_grad():
        logits = model(tensor)
        probs = F.softmax(logits, dim=1).squeeze(0).cpu().numpy()

    pred_idx = int(probs.argmax())
    return {
        "label": IDX_TO_CLASS[pred_idx],
        "probability": float(probs[pred_idx]),
        "probabilities": {IDX_TO_CLASS[i]: float(p) for i, p in enumerate(probs)},
    }
