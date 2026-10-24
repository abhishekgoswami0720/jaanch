"""Shared scam memory: what Jaanch learns from every student's check.

When an offer comes out high risk, Jaanch remembers the scammer's contacts:
phone numbers, email addresses, websites, UPI IDs, Telegram links and
short/form links. When anyone later checks a different message that reuses one
of them, Jaanch says so and adds risk points.

A single ChatGPT conversation can't do this: it never sees what other people
pasted. Jaanch is one agent that every student talks to, so it can.

Privacy:
- Only a keyed fingerprint (HMAC-SHA256) of each contact is stored, never the
  contact itself and never the message.
- Official company and college domains, free-mail providers and messaging
  platforms are never stored, so nobody can get a real company "flagged".
- Redacted placeholders such as 98XXXXXXXX are ignored.
- Checking the same message twice doesn't count twice.

`store` is anything with get(key) and set(key, value): the agent's
ctx.storage in production, a dict wrapper in tests.
"""

import hashlib
import hmac
import os
import re
from datetime import date
from typing import Any, Optional, Protocol as TypingProtocol

from .brands import ALL_OFFICIAL, FREE_MAIL, PLATFORM_DOMAINS, RELATED_OFFICIAL, URL_SHORTENERS
from .extract import registrable_domain
from .models import OfferFacts, Signal

SOURCE = "scam-memory"
WEIGHT = 3.0
MAX_MESSAGES = 50  # message fingerprints kept per contact

KIND_LABEL = {
    "phone": "phone number",
    "email": "email address",
    "domain": "website",
    "upi": "UPI ID",
    "telegram": "Telegram account",
    "link": "link",
}

_UPI_HANDLES = (
    "ybl|ibl|axl|okaxis|okhdfcbank|okicici|oksbi|paytm|pthdfc|ptsbi|ptyes|ptaxis|upi|apl|yapl|ikwik|"
    "fbl|axisbank|icici|sbi|hdfcbank|kotak|pnb|boi|barodampay|freecharge|jio|airtel|waicici|"
    "wahdfcbank|waaxis|wasbi|naviaxis|superyes|yesbank|idfcbank|indus|federal|rbl|unionbank|cnrb"
)
UPI_RE = re.compile(r"\b[a-z0-9._-]{2,64}@(?:" + _UPI_HANDLES + r")\b", re.IGNORECASE)
TELEGRAM_RE = re.compile(r"(?:t\.me|telegram\.me)/(?:joinchat/)?([A-Za-z0-9_+-]{3,})", re.IGNORECASE)
_ACADEMIC = (".ac.in", ".edu", ".edu.in", ".gov.in", ".nic.in")
_LINK_HOSTS = URL_SHORTENERS | {"forms.gle", "docs.google.com", "linktr.ee", "chat.whatsapp.com"}


class Store(TypingProtocol):
    def get(self, key: str) -> Any: ...
    def set(self, key: str, value: Any) -> None: ...


def _secret() -> bytes:
    # Keyed with the agent's own secret seed, so the fingerprints can't be reversed by guessing numbers.
    return (os.getenv("JAANCH_SEED") or "jaanch dev memory key").encode()


def _fingerprint(kind: str, value: str) -> str:
    return hmac.new(_secret(), f"{kind}:{value}".encode(), hashlib.sha256).hexdigest()[:32]


def message_fingerprint(text: str) -> str:
    normalized = re.sub(r"\s+", " ", text).strip().lower()
    return hashlib.sha256(normalized.encode()).hexdigest()[:16]


def _redacted(value: str) -> bool:
    return "xxx" in value.lower()


def _official(domain: str) -> bool:
    domain = domain.lower()
    return (
        domain in ALL_OFFICIAL or registrable_domain(domain) in ALL_OFFICIAL
        or domain in RELATED_OFFICIAL or registrable_domain(domain) in RELATED_OFFICIAL
        or domain.endswith(_ACADEMIC)
    )


def identifiers(facts: OfferFacts) -> list[tuple[str, str]]:
    """The scammer-controlled contacts in a message, as (kind, normalized value)."""
    found: list[tuple[str, str]] = []

    for phone in facts.phones:
        digits = re.sub(r"\D", "", phone)[-10:]
        if len(digits) == 10:
            found.append(("phone", digits))

    for email in facts.emails:
        domain = email.split("@", 1)[1]
        if not _official(domain):
            found.append(("email", email.lower()))

    for domain in facts.domains:
        if domain in FREE_MAIL or domain in PLATFORM_DOMAINS or domain in URL_SHORTENERS or _official(domain):
            continue
        found.append(("domain", domain))

    for m in UPI_RE.finditer(facts.text):
        found.append(("upi", m.group(0).lower()))

    for m in TELEGRAM_RE.finditer(facts.text):
        found.append(("telegram", m.group(1).lower()))

    for url in facts.urls:
        bare = re.sub(r"^(?:https?://)?(?:www\.)?", "", url).rstrip("/")
        host = bare.split("/", 1)[0].lower()
        if host in _LINK_HOSTS and "/" in bare and not bare.lower().startswith(("t.me/", "telegram.me/")):
            found.append(("link", host + "/" + bare.split("/", 1)[1]))

    unique, seen = [], set()
    for kind, value in found:
        if (kind, value) not in seen and not _redacted(value):
            seen.add((kind, value))
            unique.append((kind, value))
    return unique


def lookup(store: Store, facts: OfferFacts) -> list[Signal]:
    """A 'seen before' signal if any contact appeared in an earlier high-risk check."""
    this_msg = message_fingerprint(facts.text)
    hits = []
    for kind, value in identifiers(facts):
        record = store.get("seen:" + _fingerprint(kind, value))
        if not record:
            continue
        earlier = [m for m in record.get("msgs", []) if m != this_msg]
        if earlier:
            hits.append((len(earlier), kind, value, record.get("first", "")))
    if not hits:
        return []

    hits.sort(reverse=True)
    count, kind, value, first = hits[0]
    label = f"This {KIND_LABEL[kind]} was already flagged in {count} earlier scam check{'s' if count != 1 else ''}"
    evidence = f"{value} · first flagged {first}"
    if len(hits) > 1:
        evidence += f" · {len(hits) - 1} more contact(s) also seen before"
    return [Signal(id="seen_before", label=label, weight=WEIGHT, evidence=evidence, source=SOURCE)]


def remember(store: Store, facts: OfferFacts, today: Optional[str] = None) -> int:
    """Record the contacts from a high-risk offer. Returns how many were new for this message."""
    this_msg = message_fingerprint(facts.text)
    today = today or date.today().isoformat()
    saved = 0
    for kind, value in identifiers(facts):
        key = "seen:" + _fingerprint(kind, value)
        record = store.get(key) or {"kind": kind, "first": today, "msgs": []}
        if this_msg in record["msgs"]:
            continue
        record["msgs"] = (record["msgs"] + [this_msg])[-MAX_MESSAGES:]
        record["last"] = today
        store.set(key, record)
        saved += 1
    return saved


def learn_from(store: Store, facts: OfferFacts, verdict: str) -> int:
    """Only high-risk results teach the memory, so ordinary offers never get recorded."""
    if verdict != "high_risk":
        return 0
    return remember(store, facts)
