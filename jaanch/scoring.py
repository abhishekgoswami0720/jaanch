"""Turns evidence into a 1-10 risk score.

The score is a fixed formula over the signals, never an LLM opinion, so the
same message always gets the same score and every point can be traced to a
piece of evidence.
"""

from .models import Signal

BASELINE = 2.0  # an offer with no evidence either way


def score(signals: list[Signal]) -> int:
    total = BASELINE + sum(s.weight for s in _dedupe(signals))
    return int(max(1, min(10, round(total))))


def verdict(risk: int) -> str:
    if risk >= 7:
        return "high_risk"
    if risk >= 4:
        return "suspicious"
    return "low_risk"


VERDICT_TEXT = {
    "high_risk": "High risk: this looks like a scam",
    "suspicious": "Suspicious: verify before you share anything or pay",
    "low_risk": "Low risk: no strong scam signals found",
}


def _dedupe(signals: list[Signal]) -> list[Signal]:
    """Count each kind of signal once, keeping its strongest instance."""
    best: dict[str, Signal] = {}
    for s in signals:
        if s.id not in best or abs(s.weight) > abs(best[s.id].weight):
            best[s.id] = s
    return list(best.values())


def ranked(signals: list[Signal]) -> list[Signal]:
    return sorted(_dedupe(signals), key=lambda s: -s.weight)
