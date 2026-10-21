"""Live checks on the domains and email addresses in an offer.

- Domain age from RDAP (the public successor to WHOIS), via the rdap.org bootstrap.
- Whether the email domain can receive mail at all (MX records over DNS-over-HTTPS).
- Lookalikes of well-known employers (infosys-careers.in, tcs-hr.co, wipr0.com).

Network calls are injectable so tests can run offline.
"""

import asyncio
from datetime import datetime, timezone
from typing import Awaitable, Callable, Optional

import aiohttp

from .brands import ALL_OFFICIAL, BRANDS, PLATFORM_DOMAINS, RELATED_OFFICIAL, URL_SHORTENERS
from .extract import display_brand, find_brands
from .models import DomainReport, OfferFacts, Signal

SOURCE = "domain-agent"
RDAP_URL = "https://rdap.org/domain/{domain}"
DOH_URL = "https://dns.google/resolve?name={domain}&type=MX"

Fetcher = Callable[[str], Awaitable[tuple[int, Optional[dict]]]]


async def http_json(url: str) -> tuple[int, Optional[dict]]:
    timeout = aiohttp.ClientTimeout(total=8)
    headers = {"Accept": "application/rdap+json, application/json"}
    async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
        async with session.get(url, allow_redirects=True) as resp:
            if resp.status != 200:
                return resp.status, None
            return resp.status, await resp.json(content_type=None)


def registration_date(rdap: dict) -> Optional[datetime]:
    for event in rdap.get("events", []):
        if event.get("eventAction") == "registration" and event.get("eventDate"):
            raw = event["eventDate"].replace("Z", "+00:00")
            try:
                dt = datetime.fromisoformat(raw)
            except ValueError:
                return None
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    return None


# Short brand labels distinctive enough to match inside another domain name.
_SHORT_OK = {"tcs", "hcl", "ibm", "sbi", "jio", "pwc", "kpmg", "zoho", "hdfc"}

_HOMOGLYPHS = str.maketrans({"0": "o", "1": "l", "3": "e", "5": "s", "4": "a", "7": "t"})


def _edit_distance_le1(a: str, b: str) -> bool:
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b)) <= 1
    short, long_ = (a, b) if len(a) < len(b) else (b, a)
    return any(long_[:i] + long_[i + 1:] == short for i in range(len(long_)))


def lookalike_of(domain: str) -> Optional[tuple[str, str]]:
    """Return (brand, official_domain) if `domain` imitates a known employer."""
    if domain in ALL_OFFICIAL or domain in RELATED_OFFICIAL:
        return None
    raw = domain.split(".")[0]
    label = raw.replace("-", "").translate(_HOMOGLYPHS).replace("rn", "m")
    for brand, officials in BRANDS.items():
        key = brand.replace(" ", "").replace("&", "")
        for official in officials:
            off_label = official.split(".")[0]
            if raw == off_label:
                return brand, official  # right name, wrong ending: infosys.co, tcs.in.net
            # Brand name embedded in another domain: infosys-careers.in, tcshiring.com
            if (len(off_label) >= 5 or off_label in _SHORT_OK) and off_label in label:
                return brand, official
            if len(key) >= 5 and key in label:
                return brand, official
            # One-letter typo or digit swap: infosyss.com, amazom.in, wipr0.com
            if len(off_label) >= 5 and _edit_distance_le1(label, off_label):
                return brand, official
    return None


async def check_domain(domain: str, fetch: Fetcher, now: datetime) -> tuple[list[Signal], list[str]]:
    signals: list[Signal] = []
    errors: list[str] = []

    look = lookalike_of(domain)
    if look:
        brand, official = look
        signals.append(Signal(
            id="lookalike", label=f"{domain} imitates {display_brand(brand)} (official site: {official})",
            weight=3.0, evidence=domain, source=SOURCE))

    rdap_task = fetch(RDAP_URL.format(domain=domain))
    mx_task = fetch(DOH_URL.format(domain=domain))
    rdap_res, mx_res = await asyncio.gather(rdap_task, mx_task, return_exceptions=True)

    # Domain age
    if isinstance(rdap_res, Exception):
        errors.append(f"RDAP lookup failed for {domain}: {type(rdap_res).__name__}")
    else:
        status, data = rdap_res
        if status == 404:
            # Some ccTLD registries have no RDAP service; only DNS decides "doesn't exist".
            errors.append(f"No RDAP record for {domain}; age unknown")
        elif data:
            reg = registration_date(data)
            if reg:
                days = (now - reg).days
                when = reg.date().isoformat()
                if days < 30:
                    signals.append(Signal(id="domain_new", label=f"{domain} was registered only {days} days ago",
                                          weight=3.0, evidence=f"registered {when}", source=SOURCE))
                elif days < 180:
                    signals.append(Signal(id="domain_young", label=f"{domain} is less than 6 months old",
                                          weight=1.5, evidence=f"registered {when}", source=SOURCE))
                elif days > 5 * 365 and not look:
                    signals.append(Signal(id="domain_old", label=f"{domain} has existed since {reg.year}",
                                          weight=-1.0, evidence=f"registered {when}", source=SOURCE))
        else:
            errors.append(f"RDAP returned HTTP {status} for {domain}")

    # Can the domain receive email?
    if isinstance(mx_res, Exception):
        errors.append(f"MX lookup failed for {domain}: {type(mx_res).__name__}")
    else:
        status, data = mx_res
        if data is not None:
            answers = [a for a in data.get("Answer", []) if a.get("type") == 15]
            if data.get("Status") == 3:  # NXDOMAIN
                signals.append(Signal(id="not_registered", label=f"{domain} does not exist",
                                      weight=2.0, evidence="DNS: NXDOMAIN", source=SOURCE))
            elif not answers:
                signals.append(Signal(id="no_mx", label=f"{domain} cannot receive email (no mail server)",
                                      weight=1.5, evidence="DNS: no MX records", source=SOURCE))
        else:
            errors.append(f"DNS returned HTTP {status} for {domain}")

    return signals, errors


async def check_domains(facts: OfferFacts, fetch: Fetcher = http_json,
                        now: Optional[datetime] = None) -> DomainReport:
    now = now or datetime.now(timezone.utc)
    targets = [d for d in facts.domains if d not in PLATFORM_DOMAINS and d not in URL_SHORTENERS][:4]

    signals: list[Signal] = []
    errors: list[str] = []

    results = await asyncio.gather(*(check_domain(d, fetch, now) for d in targets))
    for sigs, errs in results:
        signals.extend(sigs)
        errors.extend(errs)

    # Email domain belongs to the company the message names: a good sign.
    brands = find_brands(facts.text)
    email_domains = {e.split("@", 1)[1] for e in facts.emails}
    for brand in brands:
        officials = set(BRANDS[brand])
        if any(d in officials or any(d.endswith("." + o) for o in officials) for d in email_domains):
            signals.append(Signal(id="official_email", label=f"Email comes from {display_brand(brand)}'s official domain",
                                  weight=-2.0, evidence=", ".join(sorted(email_domains)), source=SOURCE))
            break

    return DomainReport(signals=signals, checked=targets, errors=errors)
