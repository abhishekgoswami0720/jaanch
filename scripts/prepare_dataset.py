"""Prepare and split the EMSCAD job scam dataset.

Usage:
    python scripts/prepare_dataset.py
    python scripts/prepare_dataset.py --raw-path data/raw/fake_job_postings.csv
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd
from sklearn.model_selection import train_test_split

RANDOM_SEED = 42
TEXT_COLUMNS = [
    "title",
    "company_profile",
    "description",
    "requirements",
    "benefits",
    "employment_type",
    "required_experience",
    "required_education",
    "industry",
    "function",
    "location",
    "salary_range",
]


def find_raw_dataset(specified_path: Optional[str] = None) -> Path:
    """Find the raw dataset CSV file or raise a descriptive error."""
    root = Path(__file__).resolve().parent.parent

    if specified_path:
        path = Path(specified_path)
        if path.exists() and path.is_file() and path.stat().st_size > 0:
            return path
        raise FileNotFoundError(
            f"Specified raw dataset not found at: {specified_path}\n"
            "Please ensure the file exists or omit --raw-path to search standard locations."
        )

    candidates = [
        root / "data" / "raw" / "fake_job_postings.csv",
        root / "Data" / "fake_job_postings.csv",
    ]
    raw_dir = root / "data" / "raw"
    if raw_dir.exists():
        candidates.extend(list(raw_dir.glob("*.csv")))

    for path in candidates:
        if path.exists() and path.is_file() and path.stat().st_size > 0:
            return path

    expected_path = root / "data" / "raw" / "fake_job_postings.csv"
    raise FileNotFoundError(
        f"Raw dataset not found at expected path: {expected_path}\n"
        "Please download the EMSCAD dataset ('fake_job_postings.csv') from Kaggle:\n"
        "https://www.kaggle.com/datasets/shivamb/real-or-fake-fake-jobposting-prediction\n"
        f"and place the CSV at: {expected_path}"
    )


def clean_text_field(val) -> str:
    """Safely format and clean an individual text field."""
    if val is None or pd.isna(val):
        return ""
    s = str(val).strip()
    if s.lower() == "nan" or s.lower() == "null" or s == "":
        return ""
    # Normalize excessive internal whitespace and tabs while preserving newlines & punctuation
    s = re.sub(r"[ \t]+", " ", s)
    return s.strip()


def build_text_representation(row: pd.Series) -> str:
    """Assemble relevant fields into a single rich text representation.
    
    Excludes job_id and system identifiers to prevent data leakage.
    Preserves numbers, currency amounts, negation, and domain references.
    """
    sections = []

    title = clean_text_field(row.get("title"))
    if title:
        sections.append(f"Title: {title}")

    company = clean_text_field(row.get("company_profile"))
    if company:
        sections.append(f"Company: {company}")

    desc = clean_text_field(row.get("description"))
    if desc:
        sections.append(f"Description: {desc}")

    reqs = clean_text_field(row.get("requirements"))
    if reqs:
        sections.append(f"Requirements: {reqs}")

    benefits = clean_text_field(row.get("benefits"))
    if benefits:
        sections.append(f"Benefits: {benefits}")

    # Metadata attributes
    meta_parts = []
    for col in ["employment_type", "required_experience", "required_education", "industry", "function"]:
        val = clean_text_field(row.get(col))
        if val:
            meta_parts.append(val)
    if meta_parts:
        sections.append(f"Details: {' | '.join(meta_parts)}")

    loc = clean_text_field(row.get("location"))
    if loc:
        sections.append(f"Location: {loc}")

    salary = clean_text_field(row.get("salary_range"))
    if salary:
        sections.append(f"Salary: {salary}")

    full_text = "\n\n".join(sections)
    return full_text.strip()


def prepare_data(raw_path: Path, output_dir: Path, reports_dir: Path, labels_dir: Path) -> dict:
    """Load, inspect, clean, deduplicate, and split the raw job postings dataset."""
    print(f"Loading raw dataset from: {raw_path}")
    df = pd.read_csv(raw_path, encoding="utf-8", low_memory=False)

    initial_rows, initial_cols = df.shape
    print(f"Discovered {initial_rows:,} rows across {initial_cols} columns.")

    # Target column validation
    if "fraudulent" not in df.columns:
        raise ValueError(f"Required target column 'fraudulent' not found in columns: {list(df.columns)}")

    # Check for non-null target values
    df = df.dropna(subset=["fraudulent"]).copy()
    try:
        df["fraudulent"] = df["fraudulent"].astype(int)
    except Exception as err:
        raise ValueError(f"Could not convert target column 'fraudulent' to integer: {err}")

    # Validate target values are strictly 0 and 1
    unique_targets = sorted(df["fraudulent"].unique())
    if unique_targets != [0, 1] and unique_targets != [0] and unique_targets != [1]:
        raise ValueError(f"Target column 'fraudulent' contains unexpected classes: {unique_targets} (expected [0, 1])")

    target_counts = df["fraudulent"].value_counts().to_dict()
    print(f"Target distribution: 0 (legitimate)={target_counts.get(0, 0):,}, 1 (scam)={target_counts.get(1, 0):,}")

    # Inspect missing values
    missingness = {}
    for col in df.columns:
        null_count = int(df[col].isna().sum())
        null_pct = float(null_count / initial_rows * 100) if initial_rows > 0 else 0.0
        missingness[col] = {"null_count": null_count, "null_pct": round(null_pct, 2), "dtype": str(df[col].dtype)}

    # Build consolidated text
    print("Building composite text representations...")
    df["text"] = df.apply(build_text_representation, axis=1)

    # Discard records with completely empty text
    empty_text_mask = df["text"].str.strip().eq("")
    empty_text_count = int(empty_text_mask.sum())
    if empty_text_count > 0:
        print(f"Dropping {empty_text_count} records with empty combined text.")
        df = df[~empty_text_mask].copy()

    # Deduplication analysis
    exact_duplicates = int(df.duplicated(subset=["text"]).sum())
    print(f"Found {exact_duplicates:,} exact duplicate text postings.")

    # Drop exact text duplicates to prevent train/test leakage
    # If the same text has conflicting labels, keep none to avoid ambiguity
    grouped = df.groupby("text")["fraudulent"].nunique()
    conflicting_texts = grouped[grouped > 1].index
    if len(conflicting_texts) > 0:
        print(f"Dropping {len(conflicting_texts)} text entries with conflicting fraudulent labels.")
        df = df[~df["text"].isin(conflicting_texts)].copy()

    df = df.drop_duplicates(subset=["text"], keep="first").copy()
    cleaned_rows = len(df)
    print(f"Retained {cleaned_rows:,} unique, well-formed records after deduplication.")

    clean_target_counts = df["fraudulent"].value_counts().to_dict()

    # Stratified Split: 70% Train, 15% Validation, 15% Test
    print("Splitting dataset into Train (70%), Validation (15%), and Test (15%) sets...")
    min_class_count = min(clean_target_counts.values()) if clean_target_counts else 0
    can_stratify = min_class_count >= 4 and len(clean_target_counts) > 1

    train_df, temp_df = train_test_split(
        df[["text", "fraudulent"]],
        test_size=0.30,
        random_state=RANDOM_SEED,
        stratify=df["fraudulent"] if can_stratify else None,
    )

    can_stratify_temp = False
    if can_stratify:
        temp_counts = temp_df["fraudulent"].value_counts()
        can_stratify_temp = min(temp_counts) >= 2 and len(temp_counts) > 1

    val_df, test_df = train_test_split(
        temp_df,
        test_size=0.50,
        random_state=RANDOM_SEED,
        stratify=temp_df["fraudulent"] if can_stratify_temp else None,
    )

    # Verify zero leakage across splits
    train_texts = set(train_df["text"])
    val_texts = set(val_df["text"])
    test_texts = set(test_df["text"])
    assert len(train_texts & test_texts) == 0, "Data leakage detected: train and test sets overlap!"
    assert len(train_texts & val_texts) == 0, "Data leakage detected: train and val sets overlap!"
    assert len(val_texts & test_texts) == 0, "Data leakage detected: val and test sets overlap!"

    # Save processed splits
    output_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)
    labels_dir.mkdir(parents=True, exist_ok=True)

    train_path = output_dir / "train.csv"
    val_path = output_dir / "val.csv"
    test_path = output_dir / "test.csv"

    train_df.to_csv(train_path, index=False, encoding="utf-8")
    val_df.to_csv(val_path, index=False, encoding="utf-8")
    test_df.to_csv(test_path, index=False, encoding="utf-8")
    print(f"Saved processed splits to:\n  {train_path}\n  {val_path}\n  {test_path}")

    # Save target mapping
    target_mapping = {
        0: "legitimate",
        1: "scam",
    }
    with open(labels_dir / "target_mapping.json", "w", encoding="utf-8") as f:
        json.dump(target_mapping, f, indent=2)

    # Prepare machine-readable report
    report = {
        "dataset_name": "EMSCAD_fake_job_postings",
        "processed_at_utc": datetime.now(timezone.utc).isoformat(),
        "random_seed": RANDOM_SEED,
        "raw_file": str(raw_path.name),
        "initial_rows": initial_rows,
        "initial_columns": initial_cols,
        "initial_target_distribution": target_counts,
        "exact_duplicates_removed": exact_duplicates,
        "cleaned_unique_rows": cleaned_rows,
        "cleaned_target_distribution": clean_target_counts,
        "splits": {
            "train": {
                "total": len(train_df),
                "scam": int((train_df["fraudulent"] == 1).sum()),
                "legitimate": int((train_df["fraudulent"] == 0).sum()),
            },
            "val": {
                "total": len(val_df),
                "scam": int((val_df["fraudulent"] == 1).sum()),
                "legitimate": int((val_df["fraudulent"] == 0).sum()),
            },
            "test": {
                "total": len(test_df),
                "scam": int((test_df["fraudulent"] == 1).sum()),
                "legitimate": int((test_df["fraudulent"] == 0).sum()),
            },
        },
        "column_missingness": missingness,
    }

    report_path = reports_dir / "dataset_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(f"Wrote dataset report to {report_path}")

    return report


def main():
    parser = argparse.ArgumentParser(description="Prepare and split EMSCAD job scam dataset.")
    parser.add_argument("--raw-path", type=str, default=None, help="Path to raw fake_job_postings.csv")
    parser.add_argument("--output-dir", type=str, default="data/processed", help="Output directory for processed CSVs")
    parser.add_argument("--reports-dir", type=str, default="data/reports", help="Directory for dataset reports")
    parser.add_argument("--labels-dir", type=str, default="data/labels", help="Directory for label mappings")
    args = parser.parse_args()

    raw_path = find_raw_dataset(args.raw_path)
    output_dir = Path(args.output_dir)
    reports_dir = Path(args.reports_dir)
    labels_dir = Path(args.labels_dir)

    prepare_data(raw_path, output_dir, reports_dir, labels_dir)


if __name__ == "__main__":
    main()
