"""Jaanch: the agent users talk to in ASI:One.

Flow for every pasted offer:
  1. ASI1 + rules pull out company, pay, fee, emails, domains, links.
  2. The facts go to the domain agent and the pattern agent at the same time.
  3. Their evidence is combined into a fixed-formula 1-10 risk score.
  4. ASI1 explains the result; the reply carries an interactive card.
If a specialist doesn't answer in time, the orchestrator runs that check itself,
so the user always gets an answer.
"""

import asyncio
import json
import os
from pathlib import Path
import re

from uagents import Agent, Context, Protocol
from uagents_core.contrib.protocols.chat import (
    ChatAcknowledgement,
    ChatMessage,
    TextContent,
    chat_protocol_spec,
)

from jaanch import llm
from jaanch.cards import (
    REPORT_STEPS,
    WELCOME,
    card_message,
    generate_cybercrime_docket,
    verdict_card,
)
from jaanch.domain_intel import check_domains
from jaanch.ml_detector import predict_offer
from jaanch.models import (
    DomainReport,
    OfferFacts,
    PatternReport,
    ReputationReport,
    VerifyOfferRequest,
    VerifyOfferResponse,
)
from jaanch.patterns import check_patterns
from jaanch.pipeline import Result, combine
from jaanch.reputation import check_reputation

HERE = Path(__file__).parent
SPECIALIST_TIMEOUT = 20

chat_proto = Protocol(spec=chat_protocol_spec)
verify_proto = Protocol(name="JaanchOfferVerification", version="1.0.0")

# Filled in by build_orchestrator()
SPECIALISTS = {"domain": "", "pattern": "", "reputation": ""}


async def _ask(ctx: Context, address: str, facts: OfferFacts, reply_type):
    if not address:
        return None
    try:
        reply, status = await ctx.send_and_receive(address, facts, response_type=reply_type,
                                                   timeout=SPECIALIST_TIMEOUT)
        if reply is None:
            ctx.logger.warning(f"{reply_type.__name__} not received: {status.detail}")
        return reply
    except Exception as err:
        ctx.logger.warning(f"{reply_type.__name__} request failed: {err}")
        return None


async def investigate(ctx: Context, text: str) -> tuple[Result, bool]:
    facts, is_offer = await llm.extract(text, logger=ctx.logger)
    domain, pattern, reputation = await asyncio.gather(
        _ask(ctx, SPECIALISTS["domain"], facts, DomainReport),
        _ask(ctx, SPECIALISTS["pattern"], facts, PatternReport),
        _ask(ctx, SPECIALISTS["reputation"], facts, ReputationReport),
    )
    # Recovery: do the work locally if a specialist is down.
    if domain is None:
        domain = await check_domains(facts)
        domain.errors.append("domain agent unavailable; checked locally")
    if pattern is None:
        pattern = check_patterns(facts)
    if reputation is None:
        reputation = await check_reputation(facts)
    pred = predict_offer(facts.text)
    ml_sig = pred.to_signal()
    return combine(facts, domain, pattern, ml_signal=ml_sig, reputation=reputation), is_offer


def _strip_mention(text: str) -> str:
    # Strips leading @handle if user mentions the agent (e.g. @jaanch-scam-check)
    return re.sub(r"^\s*@[\w.-]+\s*", "", text).strip()


def _looks_like_chitchat(text: str) -> bool:
    cleaned = _strip_mention(text).lower()
    return len(cleaned) < 25 and "@" not in cleaned and "." not in cleaned


def _selection(text: str) -> dict:
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else {}
    except (ValueError, TypeError):
        pass
    low = text.lower()
    if "how_to_report" in low or "how do i report" in low:
        return {"action": "how_to_report"}
    if "get_docket" in low or "cybercrime docket" in low or "copy docket" in low:
        return {"action": "get_docket"}
    if "check_another" in low or "check another" in low:
        return {"action": "check_another"}
    return {}


# In-memory shared collective threat ledger across scans
_COMMUNITY_FLAGGED_SCAMS: dict[str, int] = {}


@chat_proto.on_message(ChatMessage)
async def on_chat(ctx: Context, sender: str, msg: ChatMessage):
    await ctx.send(sender, ChatAcknowledgement(acknowledged_msg_id=msg.msg_id))
    raw_text = "".join(c.text for c in msg.content if isinstance(c, TextContent)).strip()
    if not raw_text:
        return

    text = _strip_mention(raw_text)

    action = _selection(raw_text).get("action")
    if action == "how_to_report":
        await ctx.send(sender, ChatMessage(content=[TextContent(text=REPORT_STEPS)]))
        return
    if action == "get_docket":
        last_investigation = getattr(ctx, "_last_investigation", None)
        if last_investigation:
            res = last_investigation
            docket_text = generate_cybercrime_docket(res.facts, res.risk, res.signals)
            await ctx.send(sender, ChatMessage(content=[TextContent(text=docket_text)]))
        else:
            await ctx.send(sender, ChatMessage(content=[TextContent(text="Please paste an offer to scan first to generate a customized cybercrime evidence docket.")]))
        return
    if action == "check_another" or _looks_like_chitchat(text):
        await ctx.send(sender, ChatMessage(content=[TextContent(text=WELCOME)]))
        return

    result, is_offer = await investigate(ctx, text)
    if not is_offer and not result.signals:
        # User asked a question, requested advice, or sent non-offer text
        advice_text = await llm.advise(text, logger=ctx.logger)
        if not advice_text:
            advice_text = (
                "I am **Jaanch**, an AI assistant that checks job and internship offers for scam signals.\n\n"
                "**Typical signs of fake internship/job offers:**\n"
                "• Demands for payment (registration, training fee, laptop deposit, ID card charge)\n"
                "• Recruiter contacts from free emails (@gmail, @yahoo) while claiming to be from a large company\n"
                "• Requests to shift conversation to Telegram or personal WhatsApp\n"
                "• Earning promises for simple tasks (liking YouTube videos, reviewing hotels)\n"
                "• Immediate offer letters without any interview or verification\n\n"
                "👉 Paste the exact offer or message you received, and I'll run a full scan with live domain and pattern checks."
            )
        await ctx.send(sender, ChatMessage(content=[TextContent(text=advice_text)]))
        return

    # Collective memory check: Record and alert if repeated scam target
    for target in (result.facts.phones + result.facts.upis + [d for d in result.facts.domains if "whatsapp" in d or "telegram" in d]):
        count = _COMMUNITY_FLAGGED_SCAMS.get(target, 0) + 1
        _COMMUNITY_FLAGGED_SCAMS[target] = count
        if count > 1 and result.risk >= 5:
            result.signals.insert(
                0,
                Signal(
                    id="collective_threat_alert",
                    label=f"Repeat Scam Alert: Scanned by {count} job-seekers recently",
                    weight=1.5,
                    evidence=f"Target {target} repeatedly queried and flagged",
                    source="collective-memory",
                ),
            )

    # Save to context for one-click docket generation
    setattr(ctx, "_last_investigation", result)

    narration = await llm.explain(text, result.risk, result.verdict_text, result.signals, logger=ctx.logger)
    payload = verdict_card(result.risk, result.verdict, result.verdict_text, result.signals, result.checked)
    ctx.logger.info(f"risk={result.risk} verdict={result.verdict} signals={[s.id for s in result.signals]}")
    await ctx.send(sender, card_message(narration, payload))


@chat_proto.on_message(ChatAcknowledgement)
async def on_ack(ctx: Context, sender: str, msg: ChatAcknowledgement):
    pass


@verify_proto.on_message(VerifyOfferRequest, replies=VerifyOfferResponse)
async def on_verify(ctx: Context, sender: str, req: VerifyOfferRequest):
    """Agent-to-agent trust check: job-search agents call this before recommending a listing."""
    text = req.offer_text + (f"\n{req.source_url}" if req.source_url else "")
    result, _ = await investigate(ctx, text)
    await ctx.send(sender, VerifyOfferResponse(
        risk_score=result.risk,
        verdict=result.verdict,
        reasons=[s.label for s in result.signals if s.weight > 0][:5],
        checked_domains=result.checked,
    ))


def build_orchestrator(mailbox: bool, domain_address: str, pattern_address: str,
                       reputation_address: str = "", port: int | None = None) -> Agent:
    SPECIALISTS["domain"] = domain_address
    SPECIALISTS["pattern"] = pattern_address
    SPECIALISTS["reputation"] = reputation_address
    seed = os.getenv("JAANCH_SEED")
    if not seed:
        print("[warn] JAANCH_SEED not set; using a public dev seed. Set your own before deploying.")
        seed = "jaanch dev seed orchestrator do not use in prod"
    agent = Agent(
        name="jaanch",
        seed=seed,
        port=port,
        mailbox=mailbox,
        publish_agent_details=mailbox,
        readme_path=str(HERE / "README_jaanch.md"),
        description="Paste a job or internship offer; Jaanch checks it for scam signs with live evidence and gives a 1-10 risk score.",
        handle_messages_concurrently=True,
    )
    agent.include(chat_proto, publish_manifest=True)
    agent.include(verify_proto, publish_manifest=True)
    return agent
