"""
Train the baseline CNN on Cats vs Dogs and log everything to MLflow:
params, per-epoch metrics, confusion matrix, loss curve, and the model artifact.

Usage:
    python src/models/train.py --data data/processed --epochs 10 --batch-size 32 --lr 1e-3
    MLFLOW_TRACKING_URI=http://mlflow-server:5000 python src/models/train.py ...
"""
import argparse
import json
import os
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import mlflow
import mlflow.pytorch
import numpy as np
import torch
import torch.nn as nn
from sklearn.metrics import confusion_matrix, accuracy_score

import sys
sys.path.append(str(Path(__file__).resolve().parents[2]))

from src.data.dataset import get_dataloaders, IDX_TO_CLASS
from src.models.model import build_model

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def evaluate(model, loader, device, criterion):
    model.eval()
    total_loss, correct, total = 0.0, 0, 0
    all_preds, all_labels = [], []
    with torch.no_grad():
        for images, labels in loader:
            images, labels = images.to(device), labels.to(device)
            outputs = model(images)
            loss = criterion(outputs, labels)
            total_loss += loss.item() * images.size(0)
            preds = outputs.argmax(dim=1)
            correct += (preds == labels).sum().item()
            total += labels.size(0)
            all_preds.extend(preds.cpu().numpy())
            all_labels.extend(labels.cpu().numpy())
    avg_loss = total_loss / max(total, 1)
    acc = correct / max(total, 1)
    return avg_loss, acc, all_labels, all_preds


def plot_loss_curve(train_losses, val_losses, out_path: Path):
    plt.figure(figsize=(6, 4))
    plt.plot(train_losses, label="train_loss")
    plt.plot(val_losses, label="val_loss")
    plt.xlabel("epoch")
    plt.ylabel("loss")
    plt.title("Loss curve")
    plt.legend()
    plt.tight_layout()
    plt.savefig(out_path)
    plt.close()


def plot_confusion_matrix(y_true, y_pred, out_path: Path):
    cm = confusion_matrix(y_true, y_pred, labels=[0, 1])
    fig, ax = plt.subplots(figsize=(4, 4))
    im = ax.imshow(cm, cmap="Blues")
    classes = [IDX_TO_CLASS[0], IDX_TO_CLASS[1]]
    ax.set_xticks([0, 1]); ax.set_xticklabels(classes)
    ax.set_yticks([0, 1]); ax.set_yticklabels(classes)
    ax.set_xlabel("Predicted"); ax.set_ylabel("True")
    for i in range(2):
        for j in range(2):
            ax.text(j, i, str(cm[i, j]), ha="center", va="center", color="black")
    fig.colorbar(im)
    plt.title("Confusion Matrix")
    plt.tight_layout()
    plt.savefig(out_path)
    plt.close()
    return cm


def configure_mlflow():
    """Configure MLflow tracking URI and S3 artifact store from environment."""
    tracking_uri = os.environ.get("MLFLOW_TRACKING_URI")
    if tracking_uri:
        mlflow.set_tracking_uri(tracking_uri)
        print(f"MLflow tracking URI set to: {tracking_uri}")

    # S3/MinIO artifact store configuration
    s3_endpoint = os.environ.get("MLFLOW_S3_ENDPOINT_URL")
    if s3_endpoint:
        os.environ["MLFLOW_S3_ENDPOINT_URL"] = s3_endpoint
        os.environ["MLFLOW_S3_IGNORE_TLS"] = os.environ.get("MLFLOW_S3_IGNORE_TLS", "true")
        print(f"MLflow S3 endpoint set to: {s3_endpoint}")

    access_key = os.environ.get("AWS_ACCESS_KEY_ID")
    secret_key = os.environ.get("AWS_SECRET_ACCESS_KEY")
    if access_key and secret_key:
        os.environ["AWS_ACCESS_KEY_ID"] = access_key
        os.environ["AWS_SECRET_ACCESS_KEY"] = secret_key
        print("MLflow S3 credentials configured")

    # Local development defaults - if no tracking URI set, use local file store
    if not tracking_uri:
        local_uri = os.environ.get("MLFLOW_LOCAL_URI", "file:./mlruns")
        mlflow.set_tracking_uri(local_uri)
        print(f"MLflow tracking URI (local default): {local_uri}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=str, default="data/processed")
    parser.add_argument("--epochs", type=int, default=10)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--img-size", type=int, default=224)
    parser.add_argument("--out-model", type=str, default="artifacts/model.pt")
    parser.add_argument("--experiment", type=str, default="cats-vs-dogs")
    args = parser.parse_args()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    configure_mlflow()
    mlflow.set_experiment(args.experiment)

    train_loader, val_loader, test_loader = get_dataloaders(
        args.data, img_size=args.img_size, batch_size=args.batch_size
    )

    model = build_model(num_classes=2).to(device)
    criterion = nn.CrossEntropyLoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=args.lr)

    Path("artifacts").mkdir(parents=True, exist_ok=True)

    with mlflow.start_run():
        mlflow.log_params({
            "epochs": args.epochs,
            "batch_size": args.batch_size,
            "lr": args.lr,
            "img_size": args.img_size,
            "model": "SimpleCNN",
        })

        train_losses, val_losses = [], []
        best_val_acc = 0.0

        for epoch in range(args.epochs):
            model.train()
            running_loss, total = 0.0, 0
            for images, labels in train_loader:
                images, labels = images.to(device), labels.to(device)
                optimizer.zero_grad()
                outputs = model(images)
                loss = criterion(outputs, labels)
                loss.backward()
                optimizer.step()
                running_loss += loss.item() * images.size(0)
                total += images.size(0)

            train_loss = running_loss / max(total, 1)
            val_loss, val_acc, _, _ = evaluate(model, val_loader, device, criterion)

            train_losses.append(train_loss)
            val_losses.append(val_loss)

            mlflow.log_metrics({
                "train_loss": train_loss,
                "val_loss": val_loss,
                "val_accuracy": val_acc,
            }, step=epoch)

            print(f"Epoch {epoch+1}/{args.epochs} - train_loss={train_loss:.4f} "
                  f"val_loss={val_loss:.4f} val_acc={val_acc:.4f}")

            if val_acc > best_val_acc:
                best_val_acc = val_acc
                torch.save(model.state_dict(), args.out_model)

        # Final test-set evaluation + confusion matrix
        model.load_state_dict(torch.load(args.out_model, map_location=device))
        test_loss, test_acc, y_true, y_pred = evaluate(model, test_loader, device, criterion)
        mlflow.log_metrics({"test_loss": test_loss, "test_accuracy": test_acc})

        loss_curve_path = Path("artifacts/loss_curve.png")
        cm_path = Path("artifacts/confusion_matrix.png")
        plot_loss_curve(train_losses, val_losses, loss_curve_path)
        cm = plot_confusion_matrix(y_true, y_pred, cm_path)

        mlflow.log_artifact(str(loss_curve_path))
        mlflow.log_artifact(str(cm_path))
        mlflow.log_artifact(args.out_model)
        mlflow.pytorch.log_model(model, artifact_path="model")

        print(f"Test accuracy: {test_acc:.4f}")
        print(f"Confusion matrix:\n{cm}")
        print(f"Model saved to {args.out_model} (also logged to MLflow)")
        metrics_path = Path("artifacts/metrics.json")
        with open(metrics_path, "w") as f:
            json.dump({
                "best_val_accuracy": best_val_acc,
                "test_loss": test_loss,
                "test_accuracy": test_acc,
            }, f, indent=2)
        print(f"Metrics saved to {metrics_path}")


if __name__ == "__main__":
    main()
