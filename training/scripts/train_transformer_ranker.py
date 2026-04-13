from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from datasets import Dataset
from transformers import (
    AutoModelForSequenceClassification,
    AutoTokenizer,
    Trainer,
    TrainingArguments,
)

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "outputs" / "transformer_data"
MODEL_DIR = ROOT / "models" / "transformer" / "ranker_roberta"
MODEL_DIR.mkdir(parents=True, exist_ok=True)

TRAIN_CSV = DATA_DIR / "train.csv"
VAL_CSV = DATA_DIR / "val.csv"

# Use distilroberta for faster CPU training on macOS; change to "roberta-base" if you want.
MODEL_NAME = "distilroberta-base"


def load_df(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path).fillna("")
    # ensure required columns exist
    required = {"job_text", "cand_text", "weak_score"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"{path} is missing columns: {missing}")

    df["label"] = df["weak_score"].astype(float)
    return df[["job_text", "cand_text", "label"]]


def main() -> None:
    train_df = load_df(TRAIN_CSV)
    val_df = load_df(VAL_CSV)

    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)

    def tokenize(batch):
        return tokenizer(
            batch["job_text"],
            batch["cand_text"],
            truncation=True,
            padding="max_length",
            max_length=256,
        )

    train_ds = Dataset.from_pandas(train_df).map(tokenize, batched=True)
    val_ds = Dataset.from_pandas(val_df).map(tokenize, batched=True)

    train_ds.set_format(type="torch", columns=["input_ids", "attention_mask", "label"])
    val_ds.set_format(type="torch", columns=["input_ids", "attention_mask", "label"])

    model = AutoModelForSequenceClassification.from_pretrained(
        MODEL_NAME,
        num_labels=1,
        problem_type="regression",
    )

    def compute_metrics(eval_pred):
        preds, labels = eval_pred
        preds = preds.reshape(-1)
        labels = labels.reshape(-1)
        mse = float(np.mean((preds - labels) ** 2))
        mae = float(np.mean(np.abs(preds - labels)))
        return {"mse": mse, "mae": mae}

    args = TrainingArguments(
        output_dir=str(MODEL_DIR),
        num_train_epochs=2,
        per_device_train_batch_size=8,
        per_device_eval_batch_size=8,
        learning_rate=2e-5,
        weight_decay=0.01,
        eval_strategy="epoch",   # NOTE: new API name
        save_strategy="epoch",
        logging_steps=50,
        load_best_model_at_end=True,
        metric_for_best_model="mae",
        greater_is_better=False,
        report_to="none",
    )

    trainer = Trainer(
        model=model,
        args=args,
        train_dataset=train_ds,
        eval_dataset=val_ds,
        tokenizer=tokenizer,
        compute_metrics=compute_metrics,
    )

    trainer.train()
    trainer.save_model(str(MODEL_DIR))
    tokenizer.save_pretrained(str(MODEL_DIR))

    print("✅ Saved model to:", MODEL_DIR)

if __name__ == "__main__":
    main()
