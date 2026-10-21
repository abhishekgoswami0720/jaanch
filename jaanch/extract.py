"""Rule-based extraction of contacts and money mentions from an offer message.

ASI1 does the richer extraction (company, role) when a key is set; these rules
always run so the agent still works if the LLM call fails.
"""

import re

from .brands import BRANDS, FREE_MAIL, PLATFORM_DOMAINS, SHORT_BRANDS
from .models import OfferFacts

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+)")
URL_RE = re.compile(
    r"\b((?:https?://)?(?:www\.)?([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,})(?![\w@-])(/[^\s)\]]*)?)",
    re.IGNORECASE,
)
PHONE_RE = re.compile(r"(?:\+?91[\s-]?)?\b[6-9]\d{4}[\s-]?\d{5}\b")
MONEY = r"(?:rs\.?|inr|₹)\s?\d[\d,]*(?:\.\d+)?(?:\s?(?:k|lakh|lpa))?"
FEE_RE = re.compile(
    r"((?:registration|security|training|joining|processing|kit|onboarding|verification|"
    r"refundable|application|certificate|document|id card|laptop)?\s*(?:fee|fees|charge|charges|"
    r"deposit)[^.\n]{0,40}?" + MONEY + r"|" + MONEY + r"[^.\n]{0,25}?(?:fee|fees|deposit|charges))",
    re.IGNORECASE,
)
_NEGATION = re.compile(r"\b(no|zero|not|never|free of|without)\b[^.!?,;\n]{0,15}$", re.IGNORECASE)
PAY_RE = re.compile(
    MONEY + r"\s*(?:/|per|a|each)\s*(?:day|hour|hr|task|week|month|annum)", re.IGNORECASE
)

# Common file extensions and words that look like domains but are not.
_NOT_DOMAINS = {"e.g", "i.e", "u.s"}
_TLD_SKIP = {"pdf", "jpg", "jpeg", "png", "doc", "docx", "txt", "zip"}

_SECOND_LEVEL = {"co", "gov", "ac", "org", "net", "edu", "nic", "res", "gen", "firm", "ind"}


def registrable_domain(host: str) -> str:
    """Rough eTLD+1: careers.infosys.com -> infosys.com, mail.gla.ac.in -> gla.ac.in."""
    host = host.lower().strip(".").removeprefix("www.")
    parts = host.split(".")
    if len(parts) >= 3 and parts[-2] in _SECOND_LEVEL and len(parts[-1]) == 2:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def display_brand(brand: str) -> str:
    return brand.upper() if brand in SHORT_BRANDS else brand.title()


def find_brands(text: str) -> list[str]:
    low = text.lower()
    found = []
    for brand in BRANDS:
        if brand in SHORT_BRANDS:
            if re.search(rf"\b{re.escape(brand)}\b", low):
                found.append(brand)
        elif brand in low:
            found.append(brand)
    return found


def extract_rules(text: str) -> OfferFacts:
    emails = sorted({m.group(0).lower() for m in EMAIL_RE.finditer(text)})
    email_domains = {e.split("@", 1)[1] for e in emails}

    urls, hosts = [], set()
    no_emails = EMAIL_RE.sub(" ", text)
    for m in URL_RE.finditer(no_emails):
        full, host = m.group(1).rstrip(".,;:!?'\""), m.group(2).lower()
        if host in _NOT_DOMAINS or host.rsplit(".", 1)[-1] in _TLD_SKIP:
            continue
        if host.replace(".", "").isdigit():
            continue
        urls.append(full)
        hosts.add(host.removeprefix("www."))

    domains = set()
    for host in hosts | email_domains:
        reg = registrable_domain(host)
        if reg not in FREE_MAIL:
            domains.add(reg if host not in PLATFORM_DOMAINS else host)

    channels = []
    low = text.lower()
    if "telegram" in low or "t.me/" in low:
        channels.append("telegram")
    if "whatsapp" in low or "wa.me/" in low:
        channels.append("whatsapp")
    if emails:
        channels.append("email")

    fee = None
    for m in FEE_RE.finditer(text):
        before = text[max(0, m.start() - 20):m.start()]
        if _NEGATION.search(before) or re.search(r"\bno\s+(fee|fees|charges)", m.group(0), re.I):
            continue
        fee = m
        break
    pay = PAY_RE.search(text)
    brands = find_brands(text)

    return OfferFacts(
        text=text,
        company=display_brand(brands[0]) if brands else None,
        fee=fee.group(0).strip() if fee else None,
        pay=pay.group(0).strip() if pay else None,
        emails=emails,
        domains=sorted(domains),
        urls=urls,
        phones=sorted({re.sub(r"[\s-]", "", p) for p in PHONE_RE.findall(text)}),
        channels=channels,
        extracted_by="rules",
    )


def free_mail_used(facts: OfferFacts) -> list[str]:
    return [e for e in facts.emails if e.split("@", 1)[1] in FREE_MAIL]
