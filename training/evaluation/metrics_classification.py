"""Classification metrics helpers (wrap sklearn for JSON export)."""
from __future__ import annotations

from typing import Any, Dict, List

import numpy as np
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)


def classification_summary(
    y_true: List[int],
    y_pred: List[int],
    labels: List[int],
    target_names: List[str],
) -> Dict[str, Any]:
    """Accuracy, macro/micro precision, recall, F1, per-class report, confusion matrix."""
    labels_arr = np.array(labels)
    acc = float(accuracy_score(y_true, y_pred))
    macro_p = float(
        precision_score(y_true, y_pred, labels=labels, average="macro", zero_division=0)
    )
    macro_r = float(
        recall_score(y_true, y_pred, labels=labels, average="macro", zero_division=0)
    )
    macro_f1 = float(
        f1_score(y_true, y_pred, labels=labels, average="macro", zero_division=0)
    )
    micro_f1 = float(
        f1_score(y_true, y_pred, labels=labels, average="micro", zero_division=0)
    )
    report = classification_report(
        y_true,
        y_pred,
        labels=labels,
        target_names=target_names,
        output_dict=True,
        zero_division=0,
    )
    cm = confusion_matrix(y_true, y_pred, labels=labels)
    return {
        "accuracy": acc,
        "precision_macro": macro_p,
        "recall_macro": macro_r,
        "f1_macro": macro_f1,
        "f1_micro": micro_f1,
        "per_class": report,
        "confusion_matrix": cm.tolist(),
        "labels_order": target_names,
    }
