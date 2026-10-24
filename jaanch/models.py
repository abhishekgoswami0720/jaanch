"""Message models shared by the Jaanch agents.

uAgents models are pydantic v1 models, so keep field types simple
(str, int, float, bool, lists and optional values).
"""

from typing import List, Optional

from uagents import Model


class Signal(Model):
    """One piece of evidence that moves the risk score up (risk) or down (trust)."""

    id: str
    label: str
    weight: float  # > 0 raises risk, < 0 lowers it
    evidence: str = ""
    source: str = ""  # which agent produced it


class OfferFacts(Model):
    """Structured facts pulled out of a pasted offer message."""

    text: str
    company: Optional[str] = None
    role: Optional[str] = None
    pay: Optional[str] = None
    fee: Optional[str] = None
    emails: List[str] = []
    domains: List[str] = []
    urls: List[str] = []
    phones: List[str] = []
    channels: List[str] = []  # e.g. telegram, whatsapp, email
    extracted_by: str = "rules"  # "asi1" or "rules"


class DomainReport(Model):
    signals: List[Signal] = []
    checked: List[str] = []
    errors: List[str] = []


class PatternReport(Model):
    signals: List[Signal] = []


class ReputationReport(Model):
    signals: List[Signal] = []
    checked: List[str] = []
    errors: List[str] = []


# ---- Public protocol other agents can call before they recommend a listing ----


class VerifyOfferRequest(Model):
    offer_text: str
    source_url: Optional[str] = None


class VerifyOfferResponse(Model):
    risk_score: int  # 1 (looks genuine) .. 10 (almost certainly a scam)
    verdict: str  # "low_risk" | "suspicious" | "high_risk"
    reasons: List[str]
    checked_domains: List[str] = []
