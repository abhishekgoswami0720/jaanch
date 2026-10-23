"""Tests for the ML dataset preparation, training, evaluation, and inference pipeline.

Ensures zero regressions, strict privacy/safety, graceful fallbacks,
and proper integration with existing Jaanch scoring and schemas.
"""

import json
from pathlib import Path
import tempfile

import numpy as np
import pandas as pd
import pytest
from sklearn.pipeline import Pipeline

from jaanch.cards import card_message, verdict_card
from jaanch.ml_detector import (
    DEFAULT_MODEL_PATH,
    MLPredictionResult,
    load_model,
    predict_offer,
    reset_cached_model,
)
from jaanch.models import DomainReport, OfferFacts, PatternReport, Signal, VerifyOfferResponse
from jaanch.pipeline import combine, run_local
from scripts.prepare_dataset import (
    RANDOM_SEED,
    build_text_representation,
    clean_text_field,
    find_raw_dataset,
    prepare_data,
)


ROOT = Path(__file__).resolve().parent.parent


# 1. Target mapping & schema tests
def test_target_mapping():
    candidates = [ROOT / d / "labels" / "target_mapping.json" for d in ("data", "Data")]
    mapping_path = next((c for c in candidates if c.exists()), candidates[0])
    assert mapping_path.exists(), "target_mapping.json must exist"
    with open(mapping_path, "r", encoding="utf-8") as f:
        mapping = json.load(f)
    assert mapping.get("0") == "legitimate"
    assert mapping.get("1") == "scam"


# 2. Missing & malformed dataset tests
def test_dataset_missing_validation():
    with pytest.raises(FileNotFoundError) as exc_info:
        find_raw_dataset("/path/that/does/not/exist/fake.csv")
    assert "not found" in str(exc_info.value).lower()


def test_malformed_dataset_missing_target(tmp_path):
    bad_csv = tmp_path / "bad.csv"
    bad_csv.write_text("job_id,title,description\n1,Developer,Coding", encoding="utf-8")
    with pytest.raises(ValueError) as exc:
        prepare_data(bad_csv, tmp_path / "proc", tmp_path / "rep", tmp_path / "lab")
    assert "fraudulent" in str(exc.value)


def test_malformed_dataset_invalid_target_values(tmp_path):
    bad_csv = tmp_path / "bad_target.csv"
    bad_csv.write_text("job_id,title,description,fraudulent\n1,Dev,Code,maybe", encoding="utf-8")
    with pytest.raises(Exception):
        prepare_data(bad_csv, tmp_path / "proc", tmp_path / "rep", tmp_path / "lab")


# 3. Text cleaning & empty fields
@pytest.mark.parametrize("val,expected", [
    (None, ""),
    ("nan", ""),
    ("NAN", ""),
    ("null", ""),
    ("", ""),
    ("   ", ""),
    ("  Software   Engineer  ", "Software Engineer"),
])
def test_clean_text_field(val, expected):
    assert clean_text_field(val) == expected


def test_build_text_representation_no_nan_leakage():
    row = pd.Series({
        "job_id": 99999,
        "title": "Software Intern",
        "company_profile": None,
        "description": "Develop Python web services.",
        "requirements": "nan",
        "benefits": "",
        "employment_type": None,
        "salary_range": "$50,000 - $60,000",
    })
    text = build_text_representation(row)
    assert "99999" not in text, "job_id must not leak into text features"
    assert "nan" not in text.lower(), "Literal 'nan' must not leak into text features"
    assert "Title: Software Intern" in text
    assert "Description: Develop Python web services." in text
    assert "Salary: $50,000 - $60,000" in text


@pytest.mark.parametrize("empty_input", [None, "", "   ", "\n\t"])
def test_empty_text_inference_handling(empty_input):
    res = predict_offer(empty_input)
    assert res.scam_score is None
    assert res.predicted_class is None
    assert "empty or invalid" in (res.warning or "").lower()


# 4. Duplicate handling and zero leakage across splits
def test_data_splits_zero_leakage():
    train_path = ROOT / "data" / "processed" / "train.csv"
    val_path = ROOT / "data" / "processed" / "val.csv"
    test_path = ROOT / "data" / "processed" / "test.csv"

    if not (train_path.exists() and test_path.exists()):
        pytest.skip("Processed splits not generated yet.")

    train_df = pd.read_csv(train_path, encoding="utf-8")
    val_df = pd.read_csv(val_path, encoding="utf-8")
    test_df = pd.read_csv(test_path, encoding="utf-8")

    train_texts = set(train_df["text"].dropna())
    val_texts = set(val_df["text"].dropna())
    test_texts = set(test_df["text"].dropna())

    assert len(train_texts & test_texts) == 0, "Train and test texts must have 0 overlap"
    assert len(train_texts & val_texts) == 0, "Train and val texts must have 0 overlap"
    assert len(val_texts & test_texts) == 0, "Val and test texts must have 0 overlap"


# 5. Deterministic preparation and splits
def test_deterministic_split(tmp_path):
    dummy_csv = tmp_path / "dummy.csv"
    records = []
    for i in range(60):
        records.append({
            "job_id": i,
            "title": f"Job Title {i}",
            "description": f"Detailed job description {i} with some unique content.",
            "fraudulent": 1 if i % 6 == 0 else 0,
        })
    pd.DataFrame(records).to_csv(dummy_csv, index=False)

    p1 = tmp_path / "p1"
    p2 = tmp_path / "p2"
    rep = tmp_path / "rep"
    lab = tmp_path / "lab"

    prepare_data(dummy_csv, p1, rep, lab)
    prepare_data(dummy_csv, p2, rep, lab)

    t1 = pd.read_csv(p1 / "train.csv")["text"].tolist()
    t2 = pd.read_csv(p2 / "train.csv")["text"].tolist()
    assert t1 == t2, "Preparation must be strictly deterministic with fixed seed"


# 6. Model serialization and reload
def test_model_pipeline_structure():
    pipeline, metadata = load_model()
    if pipeline is None:
        pytest.skip("Model artifact not found; skipping model structure test.")

    assert isinstance(pipeline, Pipeline)
    assert "tfidf" in pipeline.named_steps
    assert "clf" in pipeline.named_steps
    assert hasattr(pipeline, "predict_proba")
    assert metadata is not None
    assert metadata.get("model_version") == "1.0.0"


# 7. Inference for both classes
def test_inference_both_classes():
    scam_text = (
        "Title: Urgent Work From Home Data Entry Assistant\n"
        "Earn $500 per day! No experience needed. Immediate start.\n"
        "Send your wire transfer deposit and bank details to confirm slot."
    )
    legit_text = (
        "Title: Senior Backend Software Engineer\n"
        "Company: Established Enterprise Solutions Inc.\n"
        "Requirements: 5+ years experience in Python, distributed systems, PostgreSQL.\n"
        "Competitive salary, full medical insurance, 401(k) matching."
    )

    scam_pred = predict_offer(scam_text)
    legit_pred = predict_offer(legit_text)

    if not scam_pred.model_available:
        pytest.skip("Model artifact not available for inference test.")

    assert scam_pred.scam_score is not None
    assert legit_pred.scam_score is not None
    # The scam text should score higher than the standard legitimate enterprise posting
    assert scam_pred.scam_score > legit_pred.scam_score
    assert legit_pred.predicted_class == "legitimate"


# 8. Missing model artifact graceful handling
def test_missing_model_artifact_graceful(monkeypatch):
    reset_cached_model()
    res = predict_offer("Any offer text", model_path=Path("/no/such/model.joblib"))
    assert res.model_available is False
    assert res.predicted_class is None
    assert res.scam_score is None
    assert res.to_signal() is None
    assert "not loaded or disabled" in res.warning.lower()
    reset_cached_model()


# 9. Corrupt model artifact graceful handling
def test_corrupt_model_artifact(tmp_path):
    reset_cached_model()
    corrupt_file = tmp_path / "corrupt_model.joblib"
    corrupt_file.write_bytes(b"NOT_A_VALID_JOBLIB_FILE_CORRUPTED_BYTES")

    res = predict_offer("Any offer text", model_path=corrupt_file)
    assert res.model_available is False
    assert res.scam_score is None
    assert res.to_signal() is None
    reset_cached_model()


# 10. Inference exception recovery
def test_inference_exception_recovery(monkeypatch):
    reset_cached_model()
    pipeline, _ = load_model()
    if pipeline is None:
        pytest.skip("Model artifact not available.")

    class ExplodingPipeline:
        def predict_proba(self, texts):
            raise RuntimeError("Simulated internal feature computation failure")

    monkeypatch.setattr("jaanch.ml_detector._CACHED_PIPELINE", ExplodingPipeline())
    monkeypatch.setattr("jaanch.ml_detector._LOAD_ATTEMPTED", True)
    monkeypatch.setattr("jaanch.ml_detector._LOAD_FAILED", False)

    res = predict_offer("Valid text")
    assert res.model_available is True
    assert res.scam_score is None
    assert "failed safely" in (res.warning or "").lower()
    reset_cached_model()


# 11. Interaction with rule-based signals and non-override
def test_ml_signal_does_not_override_rule_evidence():
    facts = OfferFacts(
        text="Infosys hiring with registration fee of ₹999",
        company="Infosys",
        fee="₹999",
        emails=["hr@gmail.com"],
        domains=["infosys-careers.in"],
    )
    # High-risk rule signals
    domain_rep = DomainReport(
        signals=[
            Signal(id="lookalike", label="Imitates Infosys", weight=3.0, evidence="infosys-careers.in"),
            Signal(id="domain_new", label="Domain created recently", weight=3.0),
        ],
        checked=["infosys-careers.in"],
    )
    pattern_rep = PatternReport(
        signals=[
            Signal(id="fee_demand", label="Fee demanded", weight=4.0, evidence="₹999"),
        ]
    )

    # Even if ML signal is absent or low, rule signals correctly result in high_risk
    res_no_ml = combine(facts, domain_rep, pattern_rep, ml_signal=None)
    assert res_no_ml.verdict == "high_risk"
    assert res_no_ml.risk == 10

    # If ML fires, it adds a complementary signal without double-counting rules
    ml_sig = Signal(id="ml_scam_pattern", label="ML scam pattern", weight=1.5, source="ml-detector")
    res_with_ml = combine(facts, domain_rep, pattern_rep, ml_signal=ml_sig)
    assert res_with_ml.verdict == "high_risk"
    assert res_with_ml.risk == 10
    assert any(s.id == "ml_scam_pattern" for s in res_with_ml.signals)


# 12. Network failure behavior with ML
def test_network_failure_pipeline_resilience():
    import asyncio
    from conftest import NOW, make_fetch, sample

    failing_fetch = make_fetch(fail=True)
    res = asyncio.run(run_local(
        sample("scam_lookalike_email.txt"),
        fetch=failing_fetch,
        now=NOW,
        use_ml=True,
    ))
    # Still produces a valid Result with signals and errors noted
    assert res.verdict == "high_risk"
    assert res.risk == 10
    assert len(res.signals) > 0
    assert res.errors


# 13. Preservation of cards and ACP response schemas
def test_cards_and_acp_schemas_with_ml_signals():
    sigs = [
        Signal(id="fee_demand", label="Demands registration fee", weight=4.0, evidence="₹1,000", source="pattern-agent"),
        Signal(id="ml_scam_pattern", label="Text matches recruitment scam dataset", weight=1.5, evidence="Model score 75%", source="ml-detector"),
    ]
    card_dict = verdict_card(
        risk=8,
        verdict="high_risk",
        verdict_text="High risk: this looks like a scam",
        signals=sigs,
        checked=["example.com"],
    )

    # Fits ASI:One card limits
    assert len(json.dumps(card_dict)) < 64_000
    msg = card_message("Narration text", card_dict)
    assert len(msg.content) == 2
    meta = msg.content[1].metadata
    assert meta["card_protocol_version"] == "1"
    assert meta["card_kind"] == "custom"
    assert "preferred_drawer_width_px" in meta

    # VerifyOfferResponse compatibility
    resp = VerifyOfferResponse(
        risk_score=8,
        verdict="high_risk",
        reasons=[s.label for s in sigs if s.weight > 0][:5],
        checked_domains=["example.com"],
    )
    assert resp.risk_score == 8
    assert len(resp.reasons) == 2
    assert "Text matches recruitment scam dataset" in resp.reasons
