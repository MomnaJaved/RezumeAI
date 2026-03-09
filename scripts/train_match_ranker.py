"""
Train match ranker: cross-encoder (resume + JD) -> regression score.
Uses outputs/transformer_data (from build_pairs_and_splits, no leakage).
Config: config/train_match.yaml. Saves to artifacts/match_ranker.
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

CONFIG_PATH = ROOT / "config" / "train_match.yaml"
DATA_DIR = ROOT / "outputs" / "transformer_data"
OUT_DIR = ROOT / "artifacts" / "match_ranker"


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
    train_csv = Path(train_csv or cfg.get("data", {}).get("train", str(DATA_DIR / "train.csv")))
    val_csv = Path(val_csv or cfg.get("data", {}).get("val", str(DATA_DIR / "val.csv")))
    output_dir = Path(output_dir or cfg.get("output_dir", str(OUT_DIR)))
    seed = seed if seed is not None else cfg.get("seed", 42)
    model_name = model_name or cfg.get("model_name", "distilroberta-base")
    num_epochs = num_epochs if num_epochs is not None else cfg.get("num_epochs", 2)
    batch_size = batch_size if batch_size is not None else cfg.get("batch_size", 8)
    learning_rate = learning_rate or cfg.get("learning_rate", 2e-5)
    max_length = cfg.get("max_length", 256)
    weight_decay = cfg.get("weight_decay", 0.01)
    warmup_ratio = cfg.get("warmup_ratio", 0.1)

    if not train_csv.exists():
        raise SystemExit(f"Missing: {train_csv} (run build_pairs_and_splits.py first)")

    train_df = pd.read_csv(train_csv).fillna("")
    val_df = pd.read_csv(val_csv).fillna("") if val_csv.exists() else pd.DataFrame()

    for col in ("job_text", "cand_text", "weak_score"):
        if col not in train_df.columns:
            raise ValueError(f"Expected column '{col}' in {train_csv}")
    train_df["label"] = train_df["weak_score"].astype(float)
    if len(val_df) > 0:
        val_df["label"] = val_df["weak_score"].astype(float)

    tokenizer = AutoTokenizer.from_pretrained(model_name)

    def tokenize(batch):
        return tokenizer(
            batch["job_text"],
            batch["cand_text"],
            truncation=True,
            padding="max_length",
            max_length=max_length,
        )

    train_ds = Dataset.from_pandas(train_df[["job_text", "cand_text", "label"]])
    train_ds = train_ds.map(tokenize, batched=True)
    train_ds.set_format(type="torch", columns=["input_ids", "attention_mask", "label"])

    eval_ds = None
    if len(val_df) > 0:
        eval_ds = Dataset.from_pandas(val_df[["job_text", "cand_text", "label"]])
        eval_ds = eval_ds.map(tokenize, batched=True)
        eval_ds.set_format(type="torch", columns=["input_ids", "attention_mask", "label"])

    model = AutoModelForSequenceClassification.from_pretrained(
        model_name,
        num_labels=1,
        problem_type="regression",
    )

    def compute_metrics(eval_pred):
        preds, labels = eval_pred
        preds = preds.reshape(-1)
        labels = labels.reshape(-1)
        mse = float(np.mean((preds - labels) ** 2))
        mae = float(np.mean(np.abs(preds - labels)))
        # Spearman
        from scipy.stats import spearmanr
        r, _ = spearmanr(preds, labels)
        return {"mse": mse, "mae": mae, "spearmanr": float(r) if not np.isnan(r) else 0.0}

    args = TrainingArguments(
        output_dir=str(output_dir),
        num_train_epochs=num_epochs,
        per_device_train_batch_size=batch_size,
        per_device_eval_batch_size=batch_size,
        learning_rate=learning_rate,
        weight_decay=weight_decay,
        warmup_ratio=warmup_ratio,
        eval_strategy=cfg.get("eval_strategy", "epoch"),
        save_strategy="epoch",
        logging_steps=50,
        load_best_model_at_end=bool(eval_ds),
        metric_for_best_model="mae",
        greater_is_better=False,
        report_to="none",
        seed=seed,
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
    # Ensure a weight file exists alongside config/tokenizer for easy loading
    try:
        import torch
        torch.save(model.state_dict(), output_dir / "pytorch_model.bin")
    except Exception as e:
        print("Warning: could not save explicit pytorch_model.bin:", e)
    print("Saved model to:", output_dir)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(CONFIG_PATH))
    ap.add_argument("--train", default=None)
    ap.add_argument("--val", default=None)
    ap.add_argument("--output-dir", default=None)
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--model", default=None)
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
