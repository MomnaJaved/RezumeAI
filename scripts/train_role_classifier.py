"""
Train role classifier: RoBERTa on resume text -> role_label.
Labels come from src/parsing/role_labels.py (multi-department by default:
frontend, backend, fullstack, devops, qa, data, design, product, marketing, hr, operations, other).
Uses config/train_role.yaml or CLI args. Saves to artifacts/role_classifier.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from datasets import Dataset
from transformers import (
    AutoModelForSequenceClassification,
    AutoTokenizer,
    Trainer,
    TrainingArguments,
)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.parsing.role_labels import ROLE_LABELS

DATA_DIR = ROOT / "outputs" / "role_data"
CONFIG_PATH = ROOT / "config" / "train_role.yaml"
OUT_DIR = ROOT / "artifacts" / "role_classifier"

# Use role_labels schema (multi-department or engineering-only per role_labels.USE_MULTI_DEPARTMENT)
LABELS = tuple(ROLE_LABELS)
LABEL2ID = {k: i for i, k in enumerate(LABELS)}
ID2LABEL = {i: k for k, i in LABEL2ID.items()}


def load_config(path: Path) -> dict:
    if path.exists():
        with open(path) as f:
            return yaml.safe_load(f)
    return {}


def main(
    config_path: Path = CONFIG_PATH,
    train_csv: Path | None = None,
    val_csv: Path | None = None,
    output_dir: Path | None = None,
    seed: int | None = None,
    model_name: str | None = None,
    num_epochs: int | None = None,
    batch_size: int | None = None,
    learning_rate: float | None = None,
):
    cfg = load_config(config_path)
    train_csv = train_csv or Path(cfg.get("data", {}).get("train", str(DATA_DIR / "train.csv")))
    val_csv = val_csv or Path(cfg.get("data", {}).get("val", str(DATA_DIR / "val.csv")))
    output_dir = Path(output_dir or cfg.get("output_dir", str(OUT_DIR)))
    seed = seed if seed is not None else cfg.get("seed", 42)
    model_name = model_name or cfg.get("model_name", "distilroberta-base")
    num_epochs = num_epochs if num_epochs is not None else cfg.get("num_epochs", 3)
    batch_size = batch_size if batch_size is not None else cfg.get("batch_size", 8)
    learning_rate = learning_rate or cfg.get("learning_rate", 2e-5)
    max_length = cfg.get("max_length", 256)
    weight_decay = cfg.get("weight_decay", 0.01)
    warmup_ratio = cfg.get("warmup_ratio", 0.1)

    if not train_csv.exists():
        raise SystemExit(f"Missing: {train_csv} (run prepare_role_data.py first)")

    train_df = pd.read_csv(train_csv).fillna("")
    val_df = pd.read_csv(val_csv).fillna("") if val_csv.exists() else None

    for col in ("text", "role_label"):
        if col not in train_df.columns:
            raise ValueError(f"Expected column '{col}' in {train_csv}")
    train_df["label"] = train_df["role_label"].map(LABEL2ID)
    if val_df is not None:
        val_df["label"] = val_df["role_label"].map(LABEL2ID)

    tokenizer = AutoTokenizer.from_pretrained(model_name)

    def tokenize(batch):
        return tokenizer(
            batch["text"],
            truncation=True,
            padding="max_length",
            max_length=max_length,
        )

    train_ds = Dataset.from_pandas(train_df[["text", "label"]])
    train_ds = train_ds.map(tokenize, batched=True)
    train_ds.set_format(type="torch", columns=["input_ids", "attention_mask", "label"])

    eval_ds = None
    if val_df is not None and len(val_df) > 0:
        eval_ds = Dataset.from_pandas(val_df[["text", "label"]])
        eval_ds = eval_ds.map(tokenize, batched=True)
        eval_ds.set_format(type="torch", columns=["input_ids", "attention_mask", "label"])

    model = AutoModelForSequenceClassification.from_pretrained(
        model_name,
        num_labels=len(LABELS),
        id2label=ID2LABEL,
        label2id=LABEL2ID,
    )

    def compute_metrics(eval_pred):
        logits, labels = eval_pred
        preds = np.argmax(logits, axis=-1)
        acc = (preds == labels).mean()
        # Macro F1
        from sklearn.metrics import f1_score
        f1 = f1_score(labels, preds, average="macro", zero_division=0)
        return {"accuracy": float(acc), "macro_f1": float(f1)}

    args = TrainingArguments(
        output_dir=str(output_dir),
        num_train_epochs=num_epochs,
        per_device_train_batch_size=batch_size,
        per_device_eval_batch_size=batch_size,
        learning_rate=learning_rate,
        weight_decay=weight_decay,
        warmup_ratio=warmup_ratio,
        eval_strategy="epoch" if eval_ds else "no",
        save_strategy="epoch",
        logging_steps=50,
        load_best_model_at_end=bool(eval_ds),
        metric_for_best_model="macro_f1",
        greater_is_better=True,
        report_to="none",
        seed=seed,
        use_cpu=True,  # avoid MPS OOM on macOS; train on CPU
    )

    trainer = Trainer(
        model=model,
        args=args,
        train_dataset=train_ds,
        eval_dataset=eval_ds,
        tokenizer=tokenizer,
        compute_metrics=compute_metrics,
    )
    trainer.train()
    output_dir.mkdir(parents=True, exist_ok=True)
    trainer.save_model(str(output_dir))
    tokenizer.save_pretrained(str(output_dir))
    # Save label mapping + explicit weight file for easy loading
    import json
    with open(output_dir / "label2id.json", "w") as f:
        json.dump(LABEL2ID, f, indent=2)
    try:
        import torch
        torch.save(model.state_dict(), output_dir / "pytorch_model.bin")
    except Exception as e:
        print("Warning: could not save explicit pytorch_model.bin:", e)
    print("Saved model to:", output_dir)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(CONFIG_PATH), help="YAML config path")
    ap.add_argument("--train", default=None, help="Train CSV")
    ap.add_argument("--val", default=None, help="Val CSV")
    ap.add_argument("--output-dir", default=None, help="Output dir")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--model", default=None, help="HuggingFace model name")
    ap.add_argument("--epochs", type=int, default=None)
    ap.add_argument("--batch-size", type=int, default=None)
    ap.add_argument("--lr", type=float, default=None)
    args = ap.parse_args()
    main(
        config_path=Path(args.config),
        train_csv=Path(args.train) if args.train else None,
        val_csv=Path(args.val) if args.val else None,
        output_dir=Path(args.output_dir) if args.output_dir else None,
        seed=args.seed,
        model_name=args.model,
        num_epochs=args.epochs,
        batch_size=args.batch_size,
        learning_rate=args.lr,
    )
