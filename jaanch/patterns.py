"""Language and behaviour red flags in the offer text itself.

Each rule is (id, label, weight, regex). Weights are risk points; the scorer
adds them up. Keywords include common Hinglish phrasing used in WhatsApp scams.
"""

import re

from .brands import URL_SHORTENERS
from .extract import display_brand, find_brands, free_mail_used
from .models import OfferFacts, PatternReport, Signal

SOURCE = "pattern-agent"

RULES: list[tuple[str, str, float, str]] = [
    (
        "fee_demand",
        "Asks you to pay a fee or deposit to get the job",
        4.0,
        r"(registration|security|training|joining|processing|kit|onboarding|verification|"
        r"refundable|application|certificate|id card|laptop)\s*(fee|fees|charge|charges|deposit|amount)"
        r"|pay\s+(rs\.?|inr|₹)\s?\d|(fees?|payment)\s+(jama|bhejo|karna|karni|kare)"
        r"|refundable\s+(amount|deposit)",
    ),
    (
        "secret_data",
        "Asks for an OTP, UPI PIN, card details or remote access to your phone",
        3.0,
        r"\botp\b|upi\s*pin|\bcvv\b|debit\s*card|credit\s*card|anydesk|teamviewer|screen\s*share",
    ),
    (
        "id_documents",
        "Asks for Aadhaar, PAN or bank details before any interview",
        1.0,
        r"aadhaar|aadhar|pan\s*card|bank\s*(account|details|statement)",
    ),
    (
        "task_scam",
        "Pays you for online 'tasks' like likes, reviews or ratings",
        3.0,
        r"(like|subscribe)\s+(youtube|videos?|channels?)|google\s+(map\s+)?reviews?|rate\s+(hotels?|products?)"
        r"|prepaid\s+tasks?|merchant\s+tasks?|recharge\s+tasks?|daily\s+tasks?|simple\s+tasks?",
    ),
    (
        "off_platform",
        "Moves the conversation to Telegram or a personal WhatsApp",
        2.0,
        r"t\.me/|telegram|wa\.me/|whatsapp\s+(only|me|karo|kare)|contact\s+(on|via)\s+whatsapp|dm\s+on\s+telegram",
    ),
    (
        "easy_money",
        "Promises unusually high pay for little work",
        2.0,
        r"(earn|kamao|income|salary|payout)[^.\n]{0,30}(rs\.?|inr|₹)\s?\d[\d,]*\s*(/|per|a|daily|every)\s*(day|hour|hr|task)"
        r"|(rs\.?|inr|₹)\s?\d[\d,]*\s*(/|per|a)\s*(day|hour|hr|task)"
        r"|daily\s+(payout|payment|income)|ghar\s+baithe|work\s+from\s+home[^.\n]{0,40}(earn|daily)",
    ),
    (
        "no_interview",
        "Selection without any interview or test",
        1.5,
        r"no\s+interview|without\s+(any\s+)?interview|direct\s+(selection|joining)|interview\s+nahi"
        r"|you\s+(are|have\s+been)\s+(shortlisted|selected)\s+(directly|for\s+direct)",
    ),
    (
        "urgency",
        "Pressures you to act fast",
        1.0,
        r"within\s+\d+\s*(hours?|hrs?|minutes?)|limited\s+(seats|slots|vacanc)|last\s+date\s+(is\s+)?today"
        r"|immediate(ly)?\s+(joining|payment|response)|only\s+(few|\d+)\s+(seats|slots)|jaldi|abhi\s+pay",
    ),
    (
        "generic_greeting",
        "Generic 'Dear candidate' greeting instead of your name",
        0.5,
        r"dear\s+(candidate|applicant|student|user|sir/madam)",
    ),
]

_COMPILED = [(i, l, w, re.compile(p, re.IGNORECASE)) for i, l, w, p in RULES]


def _snippet(text: str, m: re.Match, pad: int = 30) -> str:
    s, e = max(0, m.start() - pad), min(len(text), m.end() + pad)
    return ("…" if s else "") + text[s:e].replace("\n", " ").strip() + ("…" if e < len(text) else "")


_NEGATION = re.compile(r"\b(no|zero|not|never|without|don'?t|do not|nahi|mat)\b[^.!?,;\n]{0,32}$", re.IGNORECASE)


def _first_unnegated(rx: re.Pattern, text: str):
    """First match that isn't negated, so "no registration fee" doesn't count as a fee demand."""
    for m in rx.finditer(text):
        if not _NEGATION.search(text[max(0, m.start() - 40):m.start()]):
            return m
    return None


def check_patterns(facts: OfferFacts) -> PatternReport:
    text = facts.text
    signals: list[Signal] = []

    for rule_id, label, weight, rx in _COMPILED:
        m = _first_unnegated(rx, text)
        if m:
            signals.append(Signal(id=rule_id, label=label, weight=weight, evidence=_snippet(text, m), source=SOURCE))

    # A fee the extractor found but the keyword rule missed (e.g. "send ₹1,999 to confirm").
    if facts.fee and not any(s.id == "fee_demand" for s in signals):
        signals.append(
            Signal(id="fee_demand", label="Asks you to pay a fee or deposit to get the job",
                   weight=4.0, evidence=facts.fee, source=SOURCE)
        )

    shorteners = sorted(set(facts.domains) & URL_SHORTENERS)
    if shorteners:
        signals.append(Signal(id="short_link", label="Hides the real website behind a short link",
                              weight=1.0, evidence=", ".join(shorteners), source=SOURCE))

    free = free_mail_used(facts)
    brands = find_brands(text)
    if free and brands:
        signals.append(
            Signal(
                id="freemail_brand",
                label=f"Claims to hire for {display_brand(brands[0])} but uses a free email address",
                weight=2.5,
                evidence=", ".join(free),
                source=SOURCE,
            )
        )
    elif free:
        signals.append(Signal(id="freemail", label="Recruiter writes from a free email address",
                              weight=1.0, evidence=", ".join(free), source=SOURCE))

    return PatternReport(signals=signals)
