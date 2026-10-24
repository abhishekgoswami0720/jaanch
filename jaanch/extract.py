"""Rule-based extraction of contacts and money mentions from an offer message.

ASI1 does the richer extraction (company, role) when a key is set; these rules
always run so the agent still works if the LLM call fails.
"""

import re

from .brands import BRANDS, FREE_MAIL, PAYMENT_GATEWAY_DOMAINS, PLATFORM_DOMAINS, SHORT_BRANDS
from .models import OfferFacts

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+)")
URL_RE = re.compile(
    r"\b((?:https?://)?(?:www\.)?([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,})(?![\w@-])(/[^\s)\]]*)?)",
    re.IGNORECASE,
)
PHONE_RE = re.compile(r"(?:\+?91[\s-]?)?\b[6-9]\d{4}[\s-]?\d{5}\b")
UPI_RE = re.compile(r"\b[A-Za-z0-9._%+-]{2,256}@(okaxis|okhdfcbank|okicici|oksbi|ybl|ibl|paytm|apl|barodampay|upi)\b", re.IGNORECASE)
CIN_RE = re.compile(r"\b[LU][0-9]{5}[A-Z]{2}[0-9]{4}[A-Z]{3}[0-9]{6}\b", re.IGNORECASE)
MONEY = r"(?:rs\.?|inr|₹)\s?\d[\d,]*(?:\.\d+)?(?:\s?(?:k|lakh|lpa))?"
FEE_RE = re.compile(
    r"((?:registration|security|training|joining|processing|kit|onboarding|verification|"
    r"refundable|application|certificate|document|id card|laptop)?\s*(?:fee|fees|charge|charges|"
    r"deposit)[^.\n]{0,40}?" + MONEY + r"|" + MONEY + r"[^.\n]{0,25}?(?:fee|fees|deposit|charges)"
    r"|(?:https?://)?(?:rzp\.io|pages\.razorpay\.com|imjo\.in|instamojo\.com|cashfree\.com)/[^\s)]+)",
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
    if ":" in host:
        host = host.split(":")[-1]
    host = re.sub(r"^[^a-z0-9]+|[^a-z0-9.-]+", "", host)
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
        # Strip any stray prefixes before hostname
        if ":" in host:
            host = host.split(":")[-1]
        host = re.sub(r"^[^a-z0-9]+|[^a-z0-9.-]+", "", host)
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
    if "whatsapp" in low or "wa.me/" in low or "chat.whatsapp.com" in low:
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

    # If no textual fee was found, check if a payment gateway link was provided
    pg_links = []
    for u in urls:
        for pg in PAYMENT_GATEWAY_DOMAINS:
            if pg in u.lower():
                pg_links.append(u)
    for h in hosts:
        if h in PAYMENT_GATEWAY_DOMAINS and h not in pg_links:
            pg_links.append(h)

    fee_str = fee.group(0).strip() if fee else None
    if not fee_str and pg_links:
        fee_str = f"Payment Gateway Link ({pg_links[0]})"

    pay = PAY_RE.search(text)
    brands = find_brands(text)
    upis = sorted({m.group(0).lower() for m in UPI_RE.finditer(text)})
    cins = sorted({m.group(0).upper() for m in CIN_RE.finditer(text)})

    return OfferFacts(
        text=text,
        company=display_brand(brands[0]) if brands else None,
        fee=fee_str,
        pay=pay.group(0).strip() if pay else None,
        emails=emails,
        domains=sorted(domains),
        urls=urls,
        phones=sorted({re.sub(r"[\s-]", "", p) for p in PHONE_RE.findall(text)}),
        upis=upis,
        cins=cins,
        channels=channels,
        extracted_by="rules",
    )


def free_mail_used(facts: OfferFacts) -> list[str]:
    return [e for e in facts.emails if e.split("@", 1)[1] in FREE_MAIL]
