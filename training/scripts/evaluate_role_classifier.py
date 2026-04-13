"""
Evaluate role classifier: accuracy, macro-F1, confusion matrix on test set.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

TEST_CSV = ROOT / "outputs" / "role_data" / "test.csv"
MODEL_DIR = ROOT / "artifacts" / "role_classifier"
MAX_LENGTH = 256
BATCH_SIZE = 16


def main():
    if not TEST_CSV.exists():
        raise SystemExit(f"Missing: {TEST_CSV}")
    if not MODEL_DIR.exists() or not (MODEL_DIR / "config.json").exists():
        raise SystemExit(f"Missing model: {MODEL_DIR} (run train_role_classifier.py first)")

    df = pd.read_csv(TEST_CSV).fillna("")
    with open(MODEL_DIR / "label2id.json") as f:
        label2id = json.load(f)
    # Ensure stable ordering by id
    id2label = {int(v): k for k, v in label2id.items()}
    labels = sorted(id2label.keys())
    labels_names = [id2label[i] for i in labels]
    labels_true = df["role_label"].map(label2id).tolist()

    tokenizer = AutoTokenizer.from_pretrained(str(MODEL_DIR))
    model = AutoModelForSequenceClassification.from_pretrained(str(MODEL_DIR))
    model.eval()

    preds = []
    texts = df["text"].tolist()
    with torch.no_grad():
        for i in range(0, len(texts), BATCH_SIZE):
            batch = texts[i : i + BATCH_SIZE]
            enc = tokenizer(
                batch,
                truncation=True,
                padding=True,
                max_length=MAX_LENGTH,
                return_tensors="pt",
            )
            out = model(**enc)
            preds.extend(np.argmax(out.logits.cpu().numpy(), axis=-1).tolist())

    acc = accuracy_score(labels_true, preds)
    macro_f1 = f1_score(labels_true, preds, labels=labels, average="macro", zero_division=0)
    cm = confusion_matrix(labels_true, preds, labels=labels)
    print("Role classifier evaluation (test set):")
    print("  Accuracy:", acc)
    print("  Macro F1:", macro_f1)
    print("  Classification report:")
    print(classification_report(labels_true, preds, labels=labels, target_names=labels_names, zero_division=0))
    print("  Confusion matrix (rows=true, cols=pred):")
    print("  ", labels_names)
    print(cm)


if __name__ == "__main__":
    main()
