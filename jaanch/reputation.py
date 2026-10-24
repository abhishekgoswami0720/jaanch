"""Reputation intelligence: Checks Reddit and review sentiment for companies and recruitment domains.

Queries public discussion and community sentiment (e.g. on Reddit) for reports
of scam, fraud, fake internship, upfront fee demands, or complaints.
Injectable fetcher allows full offline unit testing.
"""

import asyncio
import re
import urllib.parse
from typing import Awaitable, Callable, List, Optional

import aiohttp

from .brands import PLATFORM_DOMAINS
from .models import OfferFacts, ReputationReport, Signal

SOURCE = "reputation-agent"
USER_AGENT = "Jaanch/1.0 (recruitment scam checker; github.com/abhishekgoswami0720/jaanch)"

# Search endpoints
REDDIT_SEARCH_URL = "https://www.reddit.com/search.json?q={query}&sort=relevance&limit=5"

Fetcher = Callable[[str], Awaitable[tuple[int, Optional[dict]]]]


async def default_http_json(url: str) -> tuple[int, Optional[dict]]:
    timeout = aiohttp.ClientTimeout(total=8)
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    try:
        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
            async with session.get(url, allow_redirects=True) as resp:
                if resp.status != 200:
                    return resp.status, None
                return resp.status, await resp.json(content_type=None)
    except Exception:
        return 0, None


SCAM_KEYWORDS = re.compile(
    r"\b(scam|fake|fraud|cheat|money|fee|deposit|con|beware|police|fir|complaint|worst|illegal)\b",
    re.IGNORECASE,
)


def analyze_reddit_posts(query: str, posts: list[dict]) -> tuple[int, List[str]]:
    """Analyzes Reddit search results for scam-related discussions."""
    scam_hits = []
    for item in posts:
        data = item.get("data", {})
        title = data.get("title", "")
        selftext = data.get("selftext", "")
        combined = f"{title} {selftext}"
        
        matches = SCAM_KEYWORDS.findall(combined)
        if len(matches) >= 2 or re.search(r"\b(fake|scam|fraud)\b", title, re.IGNORECASE):
            subreddit = data.get("subreddit_name_prefixed", "r/reddit")
            snippet = title[:80]
            scam_hits.append(f"[{subreddit}] {snippet}")

    return len(scam_hits), scam_hits


async def check_reputation(
    facts: OfferFacts,
    fetch: Optional[Fetcher] = None,
) -> ReputationReport:
    """Checks Reddit and online discussions for scam complaints regarding the company or domains."""
    fetcher = fetch or default_http_json
    signals: list[Signal] = []
    checked_queries: list[str] = []
    errors: list[str] = []

    # Targets to search: company name and custom domains
    targets = []
    if facts.company and len(facts.company) >= 3 and facts.company.lower() not in {"tcs", "ibm", "hcl", "wipro", "infosys"}:
        targets.append(facts.company)
    for d in facts.domains:
        if d not in PLATFORM_DOMAINS and "." in d and d not in targets:
            targets.append(d)

    for target in targets[:2]:  # check top 2 targets to stay fast
        query = f'"{target}" (scam OR fake OR fraud OR internship)'
        checked_queries.append(target)
        url = REDDIT_SEARCH_URL.format(query=urllib.parse.quote(query))

        try:
            status, data = await fetcher(url)
            if status == 200 and data and isinstance(data, dict):
                children = data.get("data", {}).get("children", [])
                hit_count, samples = analyze_reddit_posts(target, children)
                
                if hit_count >= 2:
                    signals.append(
                        Signal(
                            id="community_scam_reports",
                            label=f"Community & Reddit discussions flag '{target}' for scam/fraud complaints",
                            weight=2.5,
                            evidence="; ".join(samples[:2]),
                            source=SOURCE,
                        )
                    )
                elif hit_count == 1:
                    signals.append(
                        Signal(
                            id="community_warning",
                            label=f"Reddit discussion mentions suspicious activity regarding '{target}'",
                            weight=1.0,
                            evidence=samples[0],
                            source=SOURCE,
                        )
                    )
            elif status not in (200, 404):
                errors.append(f"Reddit lookup returned HTTP {status} for {target}")
        except Exception as err:
            errors.append(f"Reputation lookup failed for {target}: {err}")

    return ReputationReport(signals=signals, checked=checked_queries, errors=errors)
