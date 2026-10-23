"""Train and evaluate baseline text classifiers for job scam detection.

Usage:
    python scripts/train_model.py
    python scripts/train_model.py --compare-svm
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
import sklearn
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_recall_curve,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.pipeline import Pipeline
from sklearn.svm import LinearSVC

MODEL_VERSION = "1.0.0"
RANDOM_SEED = 42


def load_splits(data_dir: Path):
    train_path = data_dir / "train.csv"
    val_path = data_dir / "val.csv"

    if not train_path.exists() or not val_path.exists():
        raise FileNotFoundError(
            f"Processed data files not found in {data_dir}.\n"
            "Please run 'python scripts/prepare_dataset.py' first."
        )

    train_df = pd.read_csv(train_path, encoding="utf-8")
    val_df = pd.read_csv(val_path, encoding="utf-8")

    # Drop any null text rows if present
    train_df = train_df.dropna(subset=["text", "fraudulent"]).copy()
    val_df = val_df.dropna(subset=["text", "fraudulent"]).copy()

    return train_df, val_df


def find_optimal_threshold(y_true, y_probs) -> tuple[float, dict]:
    """Find the threshold on the validation set that optimizes scam F1 score."""
    precisions, recalls, thresholds = precision_recall_curve(y_true, y_probs)
    # Calculate F1 for all threshold points (avoiding division by zero)
    f1_scores = []
    for p, r in zip(precisions[:-1], recalls[:-1]):
        if (p + r) > 0:
            f1_scores.append(2 * (p * r) / (p + r))
        else:
            f1_scores.append(0.0)

    best_idx = int(np.argmax(f1_scores))
    best_threshold = float(thresholds[best_idx])
    best_f1 = float(f1_scores[best_idx])

    y_pred_opt = (y_probs >= best_threshold).astype(int)
    metrics_at_opt = {
        "threshold": round(best_threshold, 4),
        "f1": round(best_f1, 4),
        "precision": round(float(precision_score(y_true, y_pred_opt, zero_division=0)), 4),
        "recall": round(float(recall_score(y_true, y_pred_opt, zero_division=0)), 4),
    }
    return best_threshold, metrics_at_opt


def train_and_select_model(
    train_df: pd.DataFrame,
    val_df: pd.DataFrame,
    models_dir: Path,
    reports_dir: Path,
    compare_svm: bool = True,
):
    print("Vectorizing text using TF-IDF (word n-grams 1-2, sublinear scaling)...")
    tfidf_config = {
        "ngram_range": (1, 2),
        "max_features": 30000,
        "min_df": 2,
        "sublinear_tf": True,
        "token_pattern": r"(?u)\b[\w\$\€\£\₹]{2,}\b",
    }

    # 1. Primary Model: Logistic Regression with balanced class weighting
    print("Training Logistic Regression pipeline...")
    lr_pipeline = Pipeline([
        ("tfidf", TfidfVectorizer(**tfidf_config)),
        ("clf", LogisticRegression(class_weight="balanced", max_iter=1000, random_state=RANDOM_SEED, C=1.0)),
    ])
    lr_pipeline.fit(train_df["text"], train_df["fraudulent"])

    # Predict probabilities on validation set
    val_lr_probs = lr_pipeline.predict_proba(val_df["text"])[:, 1]
    val_lr_preds_default = (val_lr_probs >= 0.5).astype(int)

    lr_pr_auc = float(average_precision_score(val_df["fraudulent"], val_lr_probs))
    lr_roc_auc = float(roc_auc_score(val_df["fraudulent"], val_lr_probs))
    best_thresh, opt_metrics = find_optimal_threshold(val_df["fraudulent"].values, val_lr_probs)

    print("\n--- Logistic Regression Validation Results (Default threshold 0.5) ---")
    print(f"Scam Precision: {precision_score(val_df['fraudulent'], val_lr_preds_default, zero_division=0):.4f}")
    print(f"Scam Recall:    {recall_score(val_df['fraudulent'], val_lr_preds_default, zero_division=0):.4f}")
    print(f"Scam F1-score:  {f1_score(val_df['fraudulent'], val_lr_preds_default, zero_division=0):.4f}")
    print(f"PR-AUC:         {lr_pr_auc:.4f}")
    print(f"ROC-AUC:        {lr_roc_auc:.4f}")
    print(f"Validation-tuned threshold: {best_thresh:.4f} (Validation F1: {opt_metrics['f1']:.4f})")

    svm_metrics = None
    if compare_svm:
        print("\nTraining Linear SVM pipeline for benchmark comparison...")
        svm_pipeline = Pipeline([
            ("tfidf", TfidfVectorizer(**tfidf_config)),
            ("clf", LinearSVC(class_weight="balanced", random_state=RANDOM_SEED, max_iter=2000, C=1.0)),
        ])
        svm_pipeline.fit(train_df["text"], train_df["fraudulent"])
        val_svm_preds = svm_pipeline.predict(val_df["text"])
        val_svm_decision = svm_pipeline.decision_function(val_df["text"])
        svm_pr_auc = float(average_precision_score(val_df["fraudulent"], val_svm_decision))

        print("\n--- Linear SVM Validation Results ---")
        print(f"Scam Precision: {precision_score(val_df['fraudulent'], val_svm_preds, zero_division=0):.4f}")
        print(f"Scam Recall:    {recall_score(val_df['fraudulent'], val_svm_preds, zero_division=0):.4f}")
        print(f"Scam F1-score:  {f1_score(val_df['fraudulent'], val_svm_preds, zero_division=0):.4f}")
        print(f"PR-AUC:         {svm_pr_auc:.4f}")

        svm_metrics = {
            "model_type": "LinearSVC",
            "val_precision": round(float(precision_score(val_df["fraudulent"], val_svm_preds, zero_division=0)), 4),
            "val_recall": round(float(recall_score(val_df["fraudulent"], val_svm_preds, zero_division=0)), 4),
            "val_f1": round(float(f1_score(val_df["fraudulent"], val_svm_preds, zero_division=0)), 4),
            "val_pr_auc": round(svm_pr_auc, 4),
        }

    # Save fitted Logistic Regression pipeline
    models_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    model_path = models_dir / "job_scam_model.joblib"
    joblib.dump(lr_pipeline, model_path)
    print(f"\nSaved inference pipeline to: {model_path}")

    # Build and save metadata
    metadata = {
        "model_name": "jaanch_job_scam_detector",
        "model_version": MODEL_VERSION,
        "algorithm": "LogisticRegression_balanced",
        "saved_pipeline_file": model_path.name,
        "dataset": {
            "name": "EMSCAD (Employment Scam Aegean Dataset)",
            "source": "https://www.kaggle.com/datasets/shivamb/real-or-fake-fake-jobposting-prediction",
            "split_strategy": "stratified_70_15_15",
            "random_seed": RANDOM_SEED,
            "train_samples": len(train_df),
            "val_samples": len(val_df),
        },
        "target_mapping": {
            "0": "legitimate",
            "1": "scam",
        },
        "feature_configuration": {
            "vectorizer": "TfidfVectorizer",
            "ngram_range": [1, 2],
            "max_features": 30000,
            "min_df": 2,
            "sublinear_tf": True,
            "token_pattern": r"(?u)\b[\w\$\€\£\₹]{2,}\b",
        },
        "decision_thresholds": {
            "default": 0.50,
            "val_tuned_optimal_f1": round(best_thresh, 4),
            "conservative_scam_alert": 0.65,
        },
        "validation_metrics": {
            "logistic_regression": {
                "default_threshold_0_5": {
                    "precision": round(float(precision_score(val_df["fraudulent"], val_lr_preds_default, zero_division=0)), 4),
                    "recall": round(float(recall_score(val_df["fraudulent"], val_lr_preds_default, zero_division=0)), 4),
                    "f1": round(float(f1_score(val_df["fraudulent"], val_lr_preds_default, zero_division=0)), 4),
                },
                "val_optimal_threshold": opt_metrics,
                "pr_auc": round(lr_pr_auc, 4),
                "roc_auc": round(lr_roc_auc, 4),
            },
            "linear_svm_comparison": svm_metrics,
        },
        "environment": {
            "python_version": sys.version,
            "scikit_learn_version": sklearn.__version__,
            "trained_at_utc": datetime.now(timezone.utc).isoformat(),
        },
        "limitations": [
            "Dataset represents historical international job postings, not recent WhatsApp/Telegram internship messages.",
            "Model probabilities should be treated as text-pattern similarity, not guaranteed factual truth.",
            "Does not replace live domain verification or payment demand detection rules.",
        ],
    }

    metadata_path = models_dir / "job_scam_model_metadata.json"
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)
    print(f"Saved model metadata to: {metadata_path}")

    return metadata


def main():
    parser = argparse.ArgumentParser(description="Train baseline job scam classifier.")
    parser.add_argument("--data-dir", type=str, default="data/processed", help="Path to processed data directory")
    parser.add_argument("--models-dir", type=str, default="models", help="Path to models directory")
    parser.add_argument("--reports-dir", type=str, default="data/reports", help="Path to reports directory")
    parser.add_argument("--compare-svm", action="store_true", default=True, help="Train Linear SVM for comparison")
    args = parser.parse_args()

    train_df, val_df = load_splits(Path(args.data_dir))
    train_and_select_model(
        train_df=train_df,
        val_df=val_df,
        models_dir=Path(args.models_dir),
        reports_dir=Path(args.reports_dir),
        compare_svm=args.compare_svm,
    )


if __name__ == "__main__":
    main()
