"""The two specialist agents. Each does one job and answers the orchestrator
over its own small protocol, so other agents on Agentverse can reuse them too."""

import os
from pathlib import Path

from uagents import Agent, Context, Protocol

from jaanch.domain_intel import check_domains
from jaanch.seeds import resolve_seed
from jaanch.models import DomainReport, OfferFacts, PatternReport, ReputationReport
from jaanch.patterns import check_patterns
from jaanch.reputation import check_reputation

HERE = Path(__file__).parent

domain_protocol = Protocol(name="JaanchDomainIntel", version="0.1.0")
pattern_protocol = Protocol(name="JaanchPatternCheck", version="0.1.0")
reputation_protocol = Protocol(name="JaanchReputationIntel", version="0.1.0")


@domain_protocol.on_message(OfferFacts, replies=DomainReport)
async def on_domain_request(ctx: Context, sender: str, facts: OfferFacts):
    report = await check_domains(facts)
    ctx.logger.info(f"checked {report.checked}: {len(report.signals)} signals, {len(report.errors)} errors")
    await ctx.send(sender, report)


@pattern_protocol.on_message(OfferFacts, replies=PatternReport)
async def on_pattern_request(ctx: Context, sender: str, facts: OfferFacts):
    report = check_patterns(facts)
    ctx.logger.info(f"{len(report.signals)} red flags")
    await ctx.send(sender, report)


@reputation_protocol.on_message(OfferFacts, replies=ReputationReport)
async def on_reputation_request(ctx: Context, sender: str, facts: OfferFacts):
    report = await check_reputation(facts)
    ctx.logger.info(f"reputation checked {report.checked}: {len(report.signals)} signals")
    await ctx.send(sender, report)


DOMAIN_DEV_SEED = "jaanch dev seed domain intel do not use in prod"
PATTERN_DEV_SEED = "jaanch dev seed pattern check do not use in prod"
REPUTATION_DEV_SEED = "jaanch dev seed reputation intel do not use in prod"


def _seed(var: str, dev_default: str) -> str:
    return resolve_seed(var, dev_default)


def build_domain_agent(mailbox: bool, port: int | None = None) -> Agent:
    agent = Agent(
        name="jaanch-domain-intel",
        seed=_seed("JAANCH_DOMAIN_SEED", DOMAIN_DEV_SEED),
        port=port,
        mailbox=mailbox,
        publish_agent_details=mailbox,
        readme_path=str(HERE / "README_domain.md"),
        description="Checks a recruiter's domains and emails: domain age (RDAP), mail server (MX) and brand lookalikes.",
    )
    agent.include(domain_protocol, publish_manifest=mailbox)
    return agent


def build_pattern_agent(mailbox: bool, port: int | None = None) -> Agent:
    agent = Agent(
        name="jaanch-pattern-check",
        seed=_seed("JAANCH_PATTERN_SEED", PATTERN_DEV_SEED),
        port=port,
        mailbox=mailbox,
        publish_agent_details=mailbox,
        readme_path=str(HERE / "README_pattern.md"),
        description="Finds scam red flags in job/internship messages: fee demands, OTP requests, task scams, pressure tactics.",
    )
    agent.include(pattern_protocol, publish_manifest=mailbox)
    return agent


def build_reputation_agent(mailbox: bool, port: int | None = None) -> Agent:
    agent = Agent(
        name="jaanch-reputation-intel",
        seed=_seed("JAANCH_REPUTATION_SEED", REPUTATION_DEV_SEED),
        port=port,
        mailbox=mailbox,
        publish_agent_details=mailbox,
        readme_path=str(HERE / "README_reputation.md"),
        description="Searches Reddit and community discussions for scam reports, fake internship complaints, and fraudulent reviews.",
    )
    agent.include(reputation_protocol, publish_manifest=mailbox)
    return agent
