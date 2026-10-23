"""Evaluate the trained job scam classifier on the isolated held-out test set.

Usage:
    python scripts/evaluate_model.py
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import (
    average_precision_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)


def evaluate(
    test_path: Path,
    train_path: Path,
    model_path: Path,
    metadata_path: Path,
    report_output_path: Path,
):
    if not test_path.exists():
        raise FileNotFoundError(f"Held-out test set not found at: {test_path}")
    if not model_path.exists():
        raise FileNotFoundError(f"Trained model not found at: {model_path}")

    # Load data
    test_df = pd.read_csv(test_path, encoding="utf-8").dropna(subset=["text", "fraudulent"]).copy()
    y_test = test_df["fraudulent"].astype(int).values
    total_test = len(y_test)

    # Check for leakage against train set if available
    train_overlap_count = 0
    if train_path.exists():
        train_df = pd.read_csv(train_path, encoding="utf-8").dropna(subset=["text", "fraudulent"])
        overlap = set(test_df["text"]) & set(train_df["text"])
        train_overlap_count = len(overlap)
        if train_overlap_count > 0:
            print(f"[WARNING] Detected {train_overlap_count} text overlaps between train and test sets!")
        else:
            print("Verified: 0 text overlaps between train and test sets.")

    # Load model and metadata
    pipeline = joblib.load(model_path)
    metadata = {}
    if metadata_path.exists():
        with open(metadata_path, "r", encoding="utf-8") as f:
            metadata = json.load(f)

    chosen_threshold = metadata.get("decision_thresholds", {}).get("val_tuned_optimal_f1", 0.5)

    # Compute predictions
    probs = pipeline.predict_proba(test_df["text"])[:, 1]
    preds_default = (probs >= 0.50).astype(int)
    preds_chosen = (probs >= chosen_threshold).astype(int)

    # 1. Majority-class baseline (predict 0 for everything)
    majority_preds = np.zeros(total_test, dtype=int)
    baseline_acc = float(np.mean(majority_preds == y_test))
    baseline_scam_rec = float(recall_score(y_test, majority_preds, zero_division=0))
    baseline_scam_prec = float(precision_score(y_test, majority_preds, zero_division=0))
    baseline_scam_f1 = float(f1_score(y_test, majority_preds, zero_division=0))

    # Metrics computation function
    def compute_metrics(y_true, y_pred, threshold_val):
        cm = confusion_matrix(y_true, y_pred)
        tn, fp, fn, tp = int(cm[0, 0]), int(cm[0, 1]), int(cm[1, 0]), int(cm[1, 1])
        scam_prec = float(precision_score(y_true, y_pred, pos_label=1, zero_division=0))
        scam_rec = float(recall_score(y_true, y_pred, pos_label=1, zero_division=0))
        scam_f1 = float(f1_score(y_true, y_pred, pos_label=1, zero_division=0))
        legit_prec = float(precision_score(y_true, y_pred, pos_label=0, zero_division=0))
        legit_rec = float(recall_score(y_true, y_pred, pos_label=0, zero_division=0))
        legit_f1 = float(f1_score(y_true, y_pred, pos_label=0, zero_division=0))
        macro_f1 = float(f1_score(y_true, y_pred, average="macro", zero_division=0))
        return {
            "threshold": threshold_val,
            "confusion_matrix": {"TN": tn, "FP": fp, "FN": fn, "TP": tp},
            "scam": {"precision": round(scam_prec, 4), "recall": round(scam_rec, 4), "f1": round(scam_f1, 4)},
            "legitimate": {"precision": round(legit_prec, 4), "recall": round(legit_rec, 4), "f1": round(legit_f1, 4)},
            "macro_f1": round(macro_f1, 4),
        }

    metrics_default = compute_metrics(y_test, preds_default, 0.50)
    metrics_chosen = compute_metrics(y_test, preds_chosen, chosen_threshold)

    pr_auc = float(average_precision_score(y_test, probs))
    roc_auc = float(roc_auc_score(y_test, probs))

    # Print summary
    scam_count = int(np.sum(y_test == 1))
    legit_count = int(np.sum(y_test == 0))

    print("\n================== HELD-OUT TEST EVALUATION REPORT ==================")
    print(f"Test Samples: {total_test:,} (Legitimate: {legit_count:,}, Scam: {scam_count:,})")
    print(f"Scam Prevalence: {scam_count / total_test:.2%}")
    print(f"PR-AUC: {pr_auc:.4f} | ROC-AUC: {roc_auc:.4f}")
    print("\n--- Baseline: Majority-Class Classifier (Always Legitimate) ---")
    print(f"Accuracy: {baseline_acc:.4f} | Scam Precision: {baseline_scam_prec:.4f} | Scam Recall: {baseline_scam_rec:.4f} | Scam F1: {baseline_scam_f1:.4f}")

    print("\n--- Model: Logistic Regression @ Default Threshold (0.50) ---")
    cm_d = metrics_default["confusion_matrix"]
    print(f"Confusion Matrix: [TN={cm_d['TN']}, FP={cm_d['FP']}, FN={cm_d['FN']}, TP={cm_d['TP']}]")
    print(f"Scam Class:       Precision={metrics_default['scam']['precision']:.4f}, Recall={metrics_default['scam']['recall']:.4f}, F1={metrics_default['scam']['f1']:.4f}")
    print(f"Legitimate Class: Precision={metrics_default['legitimate']['precision']:.4f}, Recall={metrics_default['legitimate']['recall']:.4f}, F1={metrics_default['legitimate']['f1']:.4f}")
    print(f"Macro F1:         {metrics_default['macro_f1']:.4f}")

    print(f"\n--- Model: Logistic Regression @ Validation-Selected Threshold ({chosen_threshold:.4f}) ---")
    cm_c = metrics_chosen["confusion_matrix"]
    print(f"Confusion Matrix: [TN={cm_c['TN']}, FP={cm_c['FP']}, FN={cm_c['FN']}, TP={cm_c['TP']}]")
    print(f"Scam Class:       Precision={metrics_chosen['scam']['precision']:.4f}, Recall={metrics_chosen['scam']['recall']:.4f}, F1={metrics_chosen['scam']['f1']:.4f}")
    print(f"Legitimate Class: Precision={metrics_chosen['legitimate']['precision']:.4f}, Recall={metrics_chosen['legitimate']['recall']:.4f}, F1={metrics_chosen['legitimate']['f1']:.4f}")
    print(f"Macro F1:         {metrics_chosen['macro_f1']:.4f}")
    print("====================================================================\n")

    report_payload = {
        "evaluation_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "model_file": model_path.name,
        "test_dataset": str(test_path),
        "total_test_samples": total_test,
        "class_distribution": {"legitimate": legit_count, "scam": scam_count},
        "train_test_overlap_count": train_overlap_count,
        "pr_auc": round(pr_auc, 4),
        "roc_auc": round(roc_auc, 4),
        "majority_class_baseline": {
            "accuracy": round(baseline_acc, 4),
            "scam_precision": round(baseline_scam_prec, 4),
            "scam_recall": round(baseline_scam_rec, 4),
            "scam_f1": round(baseline_scam_f1, 4),
        },
        "default_threshold_metrics": metrics_default,
        "validation_selected_threshold_metrics": metrics_chosen,
        "limitations": [
            "Evaluated strictly on held-out split of EMSCAD historical job board postings.",
            "Test set does not measure performance on WhatsApp/Telegram Indian student internship scams.",
            "Evaluation reflects text-only postings without external domain lookups.",
        ],
    }

    report_output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_output_path, "w", encoding="utf-8") as f:
        json.dump(report_payload, f, indent=2)
    print(f"Full evaluation report saved to: {report_output_path}")

    return report_payload


def main():
    parser = argparse.ArgumentParser(description="Evaluate job scam classifier on held-out test data.")
    parser.add_argument("--test-path", type=str, default="data/processed/test.csv")
    parser.add_argument("--train-path", type=str, default="data/processed/train.csv")
    parser.add_argument("--model-path", type=str, default="models/job_scam_model.joblib")
    parser.add_argument("--metadata-path", type=str, default="models/job_scam_model_metadata.json")
    parser.add_argument("--report-path", type=str, default="data/reports/evaluation_report.json")
    args = parser.parse_args()

    evaluate(
        test_path=Path(args.test_path),
        train_path=Path(args.train_path),
        model_path=Path(args.model_path),
        metadata_path=Path(args.metadata_path),
        report_output_path=Path(args.report_path),
    )


if __name__ == "__main__":
    main()
