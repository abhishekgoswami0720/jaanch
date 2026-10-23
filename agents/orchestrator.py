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

from uagents import Agent, Context, Protocol
from uagents_core.contrib.protocols.chat import (
    ChatAcknowledgement,
    ChatMessage,
    TextContent,
    chat_protocol_spec,
)

from jaanch import llm
from jaanch.cards import REPORT_STEPS, WELCOME, card_message, verdict_card
from jaanch.domain_intel import check_domains
from jaanch.ml_detector import predict_offer
from jaanch.models import (
    DomainReport,
    OfferFacts,
    PatternReport,
    VerifyOfferRequest,
    VerifyOfferResponse,
)
from jaanch.patterns import check_patterns
from jaanch.pipeline import Result, combine

HERE = Path(__file__).parent
SPECIALIST_TIMEOUT = 20

chat_proto = Protocol(spec=chat_protocol_spec)
verify_proto = Protocol(name="JaanchOfferVerification", version="1.0.0")

# Filled in by build_orchestrator()
SPECIALISTS = {"domain": "", "pattern": ""}


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
    domain, pattern = await asyncio.gather(
        _ask(ctx, SPECIALISTS["domain"], facts, DomainReport),
        _ask(ctx, SPECIALISTS["pattern"], facts, PatternReport),
    )
    # Recovery: do the work locally if a specialist is down.
    if domain is None:
        domain = await check_domains(facts)
        domain.errors.append("domain agent unavailable; checked locally")
    if pattern is None:
        pattern = check_patterns(facts)
    pred = predict_offer(facts.text)
    ml_sig = pred.to_signal()
    return combine(facts, domain, pattern, ml_signal=ml_sig), is_offer


def _looks_like_chitchat(text: str) -> bool:
    t = text.strip().lower()
    return len(t) < 25 and "@" not in t and "." not in t


def _selection(text: str) -> dict:
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else {}
    except (ValueError, TypeError):
        pass
    low = text.lower()
    if "how_to_report" in low or "how do i report" in low:
        return {"action": "how_to_report"}
    if "check_another" in low or "check another" in low:
        return {"action": "check_another"}
    return {}


@chat_proto.on_message(ChatMessage)
async def on_chat(ctx: Context, sender: str, msg: ChatMessage):
    await ctx.send(sender, ChatAcknowledgement(acknowledged_msg_id=msg.msg_id))
    text = "".join(c.text for c in msg.content if isinstance(c, TextContent)).strip()
    if not text:
        return

    action = _selection(text).get("action")
    if action == "how_to_report":
        await ctx.send(sender, ChatMessage(content=[TextContent(text=REPORT_STEPS)]))
        return
    if action == "check_another" or _looks_like_chitchat(text):
        await ctx.send(sender, ChatMessage(content=[TextContent(text=WELCOME)]))
        return

    result, is_offer = await investigate(ctx, text)
    if not is_offer and not result.signals:
        await ctx.send(sender, ChatMessage(content=[TextContent(text=WELCOME)]))
        return

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
                       port: int | None = None) -> Agent:
    SPECIALISTS["domain"] = domain_address
    SPECIALISTS["pattern"] = pattern_address
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
