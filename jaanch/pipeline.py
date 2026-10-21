"""The full check without agents: used by the CLI, the tests, and as the
orchestrator's fallback when a specialist agent doesn't answer in time."""

from dataclasses import dataclass, field

from . import llm
from .domain_intel import check_domains
from .models import DomainReport, OfferFacts, PatternReport, Signal
from .patterns import check_patterns
from .scoring import VERDICT_TEXT, ranked, score, verdict


@dataclass
class Result:
    facts: OfferFacts
    risk: int
    verdict: str
    verdict_text: str
    signals: list[Signal]
    checked: list[str]
    errors: list[str] = field(default_factory=list)


def combine(facts: OfferFacts, domain: DomainReport, pattern: PatternReport) -> Result:
    signals = ranked(domain.signals + pattern.signals)
    risk = score(signals)
    v = verdict(risk)
    return Result(facts=facts, risk=risk, verdict=v, verdict_text=VERDICT_TEXT[v],
                  signals=signals, checked=domain.checked, errors=domain.errors)


async def run_local(text: str, fetch=None, now=None, logger=None) -> Result:
    facts, _ = await llm.extract(text, logger=logger)
    kwargs = {}
    if fetch:
        kwargs["fetch"] = fetch
    if now:
        kwargs["now"] = now
    domain = await check_domains(facts, **kwargs)
    pattern = check_patterns(facts)
    return combine(facts, domain, pattern)
