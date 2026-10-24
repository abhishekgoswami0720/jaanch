"""The full check without agents: used by the CLI, the tests, and as the
orchestrator's fallback when a specialist agent doesn't answer in time."""

from dataclasses import dataclass, field
from typing import Optional

from . import llm, memory
from .domain_intel import check_domains
from .ml_detector import predict_offer
from .models import DomainReport, OfferFacts, PatternReport, ReputationReport, Signal
from .patterns import check_patterns
from .reputation import check_reputation
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


def combine(
    facts: OfferFacts,
    domain: DomainReport,
    pattern: PatternReport,
    ml_signal: Optional[Signal] = None,
    reputation: Optional[ReputationReport] = None,
    extra: Optional[list[Signal]] = None,
) -> Result:
    all_signals = list(domain.signals + pattern.signals)
    if ml_signal is not None:
        all_signals.append(ml_signal)
    if reputation is not None:
        all_signals.extend(reputation.signals)
    all_signals.extend(extra or [])
    signals = ranked(all_signals)
    risk = score(signals)
    v = verdict(risk)

    checked = list(domain.checked)
    if reputation and reputation.checked:
        checked.extend(f"community:{q}" for q in reputation.checked)

    errors = list(domain.errors)
    if reputation and reputation.errors:
        errors.extend(reputation.errors)

    return Result(
        facts=facts,
        risk=risk,
        verdict=v,
        verdict_text=VERDICT_TEXT[v],
        signals=signals,
        checked=checked,
        errors=errors,
    )


async def run_local(
    text: str,
    fetch=None,
    rep_fetch=None,
    now=None,
    logger=None,
    use_ml: bool = True,
    check_rep: bool = True,
    store=None,
) -> Result:
    """`store` (optional) turns on the shared scam memory, as in the agent."""
    facts, _ = await llm.extract(text, logger=logger)
    kwargs = {}
    if fetch:
        kwargs["fetch"] = fetch
    if now:
        kwargs["now"] = now
    domain = await check_domains(facts, **kwargs)
    pattern = check_patterns(facts)
    reputation = None
    if check_rep:
        reputation = await check_reputation(facts, fetch=rep_fetch)
    ml_sig = None
    if use_ml:
        pred = predict_offer(facts.text)
        ml_sig = pred.to_signal()
    seen = memory.lookup(store, facts) if store is not None else []
    result = combine(facts, domain, pattern, ml_signal=ml_sig, reputation=reputation, extra=seen)
    if store is not None:
        memory.learn_from(store, facts, result.verdict)
    return result
