"""Machine learning classifier for recruitment scam text patterns.

Loads a scikit-learn TF-IDF + Logistic Regression pipeline trained on
the EMSCAD job postings dataset. Provides lazy-loaded, thread-safe inference
and graceful fallback if the model artifact is absent or corrupted.
"""

from dataclasses import dataclass
import json
import logging
import os
from pathlib import Path
import threading
from typing import Any, Optional

from .models import Signal

LOGGER = logging.getLogger("jaanch.ml_detector")

DEFAULT_MODEL_PATH = Path(__file__).resolve().parent.parent / "models" / "job_scam_model.joblib"
DEFAULT_METADATA_PATH = Path(__file__).resolve().parent.parent / "models" / "job_scam_model_metadata.json"
SOURCE = "ml-detector"

_LOCK = threading.Lock()
_CACHED_PIPELINE: Any = None
_CACHED_METADATA: Optional[dict] = None
_LOAD_ATTEMPTED: bool = False
_LOAD_FAILED: bool = False


@dataclass
class MLPredictionResult:
    """Structured result of an ML offer classification."""

    model_available: bool
    predicted_class: Optional[str]  # "scam" | "legitimate" | None
    scam_score: Optional[float]  # Estimated probability (0.0 to 1.0)
    score_type: str  # "calibrated_probability" | "unavailable"
    threshold: float
    model_version: Optional[str] = None
    warning: Optional[str] = None

    def to_signal(self) -> Optional[Signal]:
        """Convert a confident prediction into a Jaanch evidence Signal.

        A score above the decision threshold produces a moderate risk signal (+1.5 to +2.0).
        Because EMSCAD is historical international data, model output represents
        text pattern similarity, never a guaranteed fraud verdict.
        """
        if not self.model_available or self.scam_score is None:
            return None

        # Confident scam pattern (above validation-tuned threshold)
        if self.scam_score >= self.threshold:
            # Scale weight between 1.5 and 2.0 based on confidence
            weight = 2.0 if self.scam_score >= 0.75 else 1.5
            return Signal(
                id="ml_scam_pattern",
                label="Text patterns match known recruitment scam listings (ML classifier)",
                weight=weight,
                evidence=f"Model text-match score: {self.scam_score:.0%} (threshold: {self.threshold:.2f})",
                source=SOURCE,
            )

        return None


def _get_configured_model_path() -> Path:
    env_path = os.getenv("JAANCH_ML_MODEL_PATH")
    if env_path:
        return Path(env_path)
    return DEFAULT_MODEL_PATH


def _is_ml_enabled() -> bool:
    val = os.getenv("JAANCH_ENABLE_ML", "1").strip().lower()
    return val not in ("0", "false", "no", "off")


def load_model(model_path: Optional[Path] = None, force_reload: bool = False) -> tuple[Any, Optional[dict]]:
    """Lazily and safely load the trained inference pipeline and metadata."""
    global _CACHED_PIPELINE, _CACHED_METADATA, _LOAD_ATTEMPTED, _LOAD_FAILED

    if not _is_ml_enabled():
        return None, None

    with _LOCK:
        if _CACHED_PIPELINE is not None and not force_reload:
            return _CACHED_PIPELINE, _CACHED_METADATA

        if _LOAD_ATTEMPTED and _LOAD_FAILED and not force_reload:
            return None, None

        target_path = model_path or _get_configured_model_path()
        _LOAD_ATTEMPTED = True

        if not target_path.exists():
            LOGGER.warning("ML model artifact not found; operating in rule-only mode.")
            _LOAD_FAILED = True
            return None, None

        try:
            import joblib

            pipeline = joblib.load(target_path)
            meta_path = target_path.parent / f"{target_path.stem}_metadata.json"
            metadata = None
            if meta_path.exists():
                try:
                    with open(meta_path, "r", encoding="utf-8") as f:
                        metadata = json.load(f)
                except Exception:
                    LOGGER.warning("Could not parse model metadata JSON.")

            _CACHED_PIPELINE = pipeline
            _CACHED_METADATA = metadata
            _LOAD_FAILED = False
            return _CACHED_PIPELINE, _CACHED_METADATA
        except Exception as err:
            LOGGER.warning(f"Failed to load ML model artifact: {type(err).__name__}")
            _LOAD_FAILED = True
            return None, None


def reset_cached_model() -> None:
    """Reset cached model for testing purposes."""
    global _CACHED_PIPELINE, _CACHED_METADATA, _LOAD_ATTEMPTED, _LOAD_FAILED
    with _LOCK:
        _CACHED_PIPELINE = None
        _CACHED_METADATA = None
        _LOAD_ATTEMPTED = False
        _LOAD_FAILED = False


def predict_offer(
    text: Optional[str],
    model_path: Optional[Path] = None,
    threshold_override: Optional[float] = None,
) -> MLPredictionResult:
    """Predict whether a job/internship offer matches historical scam patterns.

    Parameters:
        text: The pasted offer text to classify.
        model_path: Optional custom path to model artifact.
        threshold_override: Optional custom decision threshold.

    Returns:
        Structured MLPredictionResult indicating availability, score, and predicted class.
    """
    pipeline, metadata = load_model(model_path)

    default_threshold = 0.65
    model_version = None
    if metadata:
        model_version = metadata.get("model_version", "1.0.0")
        val_thresh = metadata.get("decision_thresholds", {}).get("val_tuned_optimal_f1")
        if val_thresh:
            default_threshold = float(val_thresh)

    threshold = threshold_override if threshold_override is not None else default_threshold

    # Validate input text
    if not text or not isinstance(text, str) or not text.strip():
        return MLPredictionResult(
            model_available=pipeline is not None,
            predicted_class=None,
            scam_score=None,
            score_type="unavailable",
            threshold=threshold,
            model_version=model_version,
            warning="Input text is empty or invalid.",
        )

    if pipeline is None:
        return MLPredictionResult(
            model_available=False,
            predicted_class=None,
            scam_score=None,
            score_type="unavailable",
            threshold=threshold,
            model_version=model_version,
            warning="ML model artifact not loaded or disabled.",
        )

    try:
        clean_text = text.strip()
        # predict_proba returns [prob_legit, prob_scam]
        probs = pipeline.predict_proba([clean_text])[0]
        scam_prob = float(probs[1])
        predicted_class = "scam" if scam_prob >= threshold else "legitimate"

        return MLPredictionResult(
            model_available=True,
            predicted_class=predicted_class,
            scam_score=round(scam_prob, 4),
            score_type="calibrated_probability",
            threshold=round(threshold, 4),
            model_version=model_version,
            warning=None,
        )
    except Exception as err:
        LOGGER.warning(f"Inference exception encountered: {type(err).__name__}")
        return MLPredictionResult(
            model_available=True,
            predicted_class=None,
            scam_score=None,
            score_type="unavailable",
            threshold=threshold,
            model_version=model_version,
            warning=f"Inference failed safely ({type(err).__name__}).",
        )
