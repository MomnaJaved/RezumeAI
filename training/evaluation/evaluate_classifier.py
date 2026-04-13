#!/usr/bin/env python3
"""
Evaluate role classifier on held-out test.csv or --mock synthetic data.

Writes:
  outputs/evaluation/classifier_metrics.json
  outputs/evaluation/classifier_metrics.csv (single-row summary + flatten key metrics)
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from training.evaluation.metrics_classification import classification_summary  # noqa: E402

TEST_CSV = ROOT / "outputs" / "role_data" / "test.csv"
MOCK_CSV = Path(__file__).resolve().parent / "fixtures" / "mock_role_test.csv"
MODEL_DIR = ROOT / "artifacts" / "role_classifier"
OUT_DIR = ROOT / "outputs" / "evaluation"
MAX_LENGTH = 256
BATCH_SIZE = 16


def ensure_mock_role_data() -> Path:
    MOCK_CSV.parent.mkdir(parents=True, exist_ok=True)
    if MOCK_CSV.exists():
        return MOCK_CSV
    texts = [
        "Senior React frontend developer with TypeScript",
        "Backend engineer Python Django PostgreSQL",
        "Full stack developer Node and React",
        "Java Spring microservices backend",
        "UI designer Figma portfolio",
        "DevOps kubernetes aws terraform",
        "Machine learning engineer pytorch",
        "iOS Swift mobile developer",
    ] * 4
    labels = (
        ["frontend"] * 4 + ["backend"] * 4 + ["fullstack"] * 4 + ["backend"] * 4
    ) * 2
    pd.DataFrame({"text": texts, "role_label": labels}).to_csv(MOCK_CSV, index=False)
    print("Wrote mock role test to:", MOCK_CSV)
    return MOCK_CSV


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mock", action="store_true", help="Use small synthetic role CSV")
    args = parser.parse_args()

    data_path = MOCK_CSV if args.mock or not TEST_CSV.exists() else TEST_CSV
    if not data_path.exists():
        data_path = ensure_mock_role_data()

    if not MODEL_DIR.exists():
        print("ERROR: Missing", MODEL_DIR)
        sys.exit(1)

    df = pd.read_csv(data_path).fillna("")
    if "role_label" not in df.columns or "text" not in df.columns:
        raise SystemExit("CSV needs columns: text, role_label")

    with open(MODEL_DIR / "label2id.json") as f:
        label2id = json.load(f)
    id2label = {int(v): k for k, v in label2id.items()}
    labels_sorted = sorted(id2label.keys())
    target_names = [id2label[i] for i in labels_sorted]

    y_true = []
    for lab in df["role_label"]:
        lab = str(lab).strip()
        if lab not in label2id:
            y_true.append(-1)
        else:
            y_true.append(int(label2id[lab]))

    mask = [i >= 0 for i in y_true]
    df = df.loc[mask].reset_index(drop=True)
    y_true = [y for y, m in zip(y_true, mask) if m]
    texts = df["text"].tolist()

    tokenizer = AutoTokenizer.from_pretrained(str(MODEL_DIR))
    model = AutoModelForSequenceClassification.from_pretrained(str(MODEL_DIR))
    model.eval()
    preds: list[int] = []
    with torch.inference_mode():
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

    summary = classification_summary(y_true, preds, labels_sorted, target_names)
    summary["data_source"] = str(data_path)
    summary["n_samples"] = len(y_true)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUT_DIR / "classifier_metrics.json"
    json_path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")

    csv_path = OUT_DIR / "classifier_metrics.csv"
    flat = {
        "data_source": summary["data_source"],
        "n_samples": summary["n_samples"],
        "accuracy": summary["accuracy"],
        "precision_macro": summary["precision_macro"],
        "recall_macro": summary["recall_macro"],
        "f1_macro": summary["f1_macro"],
        "f1_micro": summary["f1_micro"],
    }
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(flat.keys()))
        w.writeheader()
        w.writerow(flat)

    print("Role classifier evaluation")
    print("  Data:", data_path)
    print("  Accuracy:", summary["accuracy"])
    print("  Precision (macro):", summary["precision_macro"])
    print("  Recall (macro):", summary["recall_macro"])
    print("  F1 (macro):", summary["f1_macro"])
    print("  Wrote:", json_path, csv_path)


if __name__ == "__main__":
    main()
