"""Jaanch: the agent users talk to in ASI:One.

Flow for every pasted offer or uploaded offer letter:
  1. If a document (PDF, DOCX, Image, TXT) is uploaded, Jaanch parses it,
     extracts structured offer attributes, examines fraud indicators (fees,
     UPI IDs, freemail, lookalikes), validates corporate registrations (CIN),
     runs ML pattern matching, checks scam memory, and returns an interactive
     Offer Letter Analysis card.
  2. If a text message is pasted, ASI1 + rules pull out company, pay, fee,
     emails, domains, and links.
  3. Facts go to domain, pattern, and reputation agents in parallel.
  4. Evidence is combined into an explainable risk score.
  5. The reply carries an interactive card and one-click cybercrime docket.
  6. Users can ask follow-up questions about the document in the same chat.
"""

import asyncio
import base64
import json
import logging
import os
from pathlib import Path
import re
from typing import Optional, Tuple

from uagents import Agent, Context, Protocol
from uagents_core.contrib.protocols.chat import (
    ChatAcknowledgement,
    ChatMessage,
    ResourceContent,
    TextContent,
    chat_protocol_spec,
)

from jaanch import llm, memory
from jaanch.cards import (
    REPORT_STEPS,
    WELCOME,
    card_message,
    document_analysis_card,
    generate_cybercrime_docket,
    generate_document_cybercrime_docket,
    verdict_card,
)
from jaanch.document_analyzer import DocumentAnalysisResult, analyze_offer_document
from jaanch.document_parser import (
    DocumentParsingError,
    InsufficientTextError,
    parse_document,
)
from jaanch.document_qa import answer_document_question, is_follow_up_question
from jaanch.document_security import (
    DocumentSecurityError,
    EncryptedDocumentError,
    FileTooLargeError,
    store_uploaded_file,
)
from jaanch.document_store import DOCUMENT_STORE
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

# State per user / conversation
_LAST_RESULT: dict[str, Result] = {}
_LAST_DOCUMENT_ANALYSIS: dict[str, DocumentAnalysisResult] = {}


async def _ask(ctx: Context, address: str, facts: OfferFacts, reply_type):
    if not address:
        return None
    try:
        reply, status = await ctx.send_and_receive(
            address, facts, response_type=reply_type, timeout=SPECIALIST_TIMEOUT
        )
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
    # Shared scam memory
    try:
        seen = memory.lookup(ctx.storage, facts)
    except Exception as err:
        ctx.logger.warning(f"scam memory lookup failed: {err}")
        seen = []
    result = combine(facts, domain, pattern, ml_signal=ml_sig, reputation=reputation, extra=seen)
    try:
        saved = memory.learn_from(ctx.storage, facts, result.verdict)
        if saved:
            ctx.logger.info(f"scam memory: remembered {saved} contact(s) from this scam")
    except Exception as err:
        ctx.logger.warning(f"scam memory save failed: {err}")
    return result, is_offer


def _strip_mention(text: str) -> str:
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
    if "check_another" in low or "check another" in low or "scan_another" in low:
        return {"action": "check_another"}
    return {}


def _extract_document_attachment(msg: ChatMessage, raw_text: str) -> Optional[Tuple[bytes, str]]:
    """Inspects ChatMessage for uploaded offer letters (ResourceContent, base64 data URIs, or local file paths)."""
    # 1. Check ResourceContent
    for c in msg.content:
        if isinstance(c, ResourceContent):
            res_items = c.resource if isinstance(c.resource, list) else [c.resource]
            for r in res_items:
                uri = getattr(r, "uri", "")
                if uri.startswith("data:"):
                    match = re.match(r"^data:[^;]+;base64,(.+)$", uri, re.DOTALL)
                    if match:
                        name = (getattr(r, "metadata", {}) or {}).get("filename", "offer_letter.pdf")
                        try:
                            return base64.b64decode(match.group(1)), name
                        except Exception:
                            pass
                elif uri and Path(uri).exists() and Path(uri).is_file():
                    p = Path(uri)
                    return p.read_bytes(), p.name

    # 2. Check base64 data URI in text
    if "data:application/" in raw_text or "data:image/" in raw_text:
        match = re.search(r"data:([^;]+);base64,([A-Za-z0-9+/=]+)", raw_text)
        if match:
            mime = match.group(1)
            b64_str = match.group(2)
            ext = ".pdf" if "pdf" in mime else (".docx" if "word" in mime else ".jpg")
            try:
                return base64.b64decode(b64_str), f"offer_letter{ext}"
            except Exception:
                pass

    # 3. Check for local file path in text (e.g. path pasted by test client or CLI)
    cleaned_path = raw_text.strip().strip("'\"")
    if Path(cleaned_path).suffix.lower() in (".pdf", ".docx", ".jpg", ".jpeg", ".png", ".webp", ".txt"):
        p = Path(cleaned_path)
        if p.exists() and p.is_file():
            try:
                return p.read_bytes(), p.name
            except Exception:
                pass

    return None


@chat_proto.on_message(ChatMessage)
async def on_chat(ctx: Context, sender: str, msg: ChatMessage):
    await ctx.send(sender, ChatAcknowledgement(acknowledged_msg_id=msg.msg_id))
    raw_text = "".join(c.text for c in msg.content if isinstance(c, TextContent)).strip()
    
    # 1. Check for Document Attachment (Offer Letter PDF, DOCX, Image, TXT)
    attached_doc = _extract_document_attachment(msg, raw_text)
    if attached_doc:
        file_bytes, filename = attached_doc
        ctx.logger.info(f"Received offer letter attachment: {filename} ({len(file_bytes)} bytes)")
        
        # Immediate receipt acknowledgement
        await ctx.send(
            sender,
            ChatMessage(content=[
                TextContent(text="I've received your offer letter. I'll extract its contents, examine potential fraud indicators, and verify the employer using available evidence.")
            ]),
        )

        try:
            doc_id, stored_path, safe_name, size, sha256 = store_uploaded_file(
                file_bytes=file_bytes,
                original_filename=filename,
            )
            DOCUMENT_STORE.save_document(
                doc_id=doc_id,
                filename=safe_name,
                file_type=Path(safe_name).suffix.lower().replace(".", ""),
                file_size=size,
                sha256=sha256,
                stored_path=str(stored_path),
                conversation_id=sender,
                status="processing",
            )
            doc = parse_document(file_bytes, safe_name, doc_id)
            analysis = await analyze_offer_document(doc, shared_store=ctx.storage, logger=ctx.logger)
            DOCUMENT_STORE.save_analysis(analysis, conversation_id=sender)
            _LAST_DOCUMENT_ANALYSIS[sender] = analysis

            payload = document_analysis_card(analysis)
            narration = (
                f"**{analysis.classification} ({analysis.risk_score}/100)**\n\n"
                f"{analysis.summary}\n\n"
                f"• **Confidence:** {analysis.confidence}\n"
                f"• **Key Details:** Role: {analysis.extracted_fields.get('role') or 'Unspecified'} · "
                f"Joining: {analysis.extracted_fields.get('joining_date') or 'Unspecified'} · "
                f"Fee Demanded: {analysis.extracted_fields.get('requested_payment') or 'None detected'}\n"
                f"• **Next step:** {analysis.recommended_actions[0] if analysis.recommended_actions else 'Verify with placement cell.'}"
            )
            await ctx.send(sender, card_message(narration, payload))
            return
        except FileTooLargeError as err:
            await ctx.send(sender, ChatMessage(content=[TextContent(text=f"⚠️ Upload Error: {err}")]))
            return
        except (EncryptedDocumentError, InsufficientTextError, DocumentSecurityError, DocumentParsingError) as err:
            await ctx.send(sender, ChatMessage(content=[TextContent(text=f"⚠️ Document Error: {err}")]))
            return
        except Exception as err:
            ctx.logger.exception(f"Document analysis failed: {err}")
            await ctx.send(sender, ChatMessage(content=[TextContent(text="⚠️ An internal error occurred while analyzing the offer letter. Please verify the file format and try again.")]))
            return

    if not raw_text:
        return

    text = _strip_mention(raw_text)

    # 2. Check for Button Actions
    action = _selection(raw_text).get("action")
    if action == "how_to_report":
        await ctx.send(sender, ChatMessage(content=[TextContent(text=REPORT_STEPS)]))
        return
    if action == "get_docket":
        # Check if user had an analyzed document first
        latest_doc = _LAST_DOCUMENT_ANALYSIS.get(sender) or DOCUMENT_STORE.get_latest_analysis(sender)
        if latest_doc:
            docket_text = generate_document_cybercrime_docket(latest_doc)
            await ctx.send(sender, ChatMessage(content=[TextContent(text=docket_text)]))
            return
        last_investigation = _LAST_RESULT.get(sender)
        if last_investigation:
            docket_text = generate_cybercrime_docket(last_investigation.facts, last_investigation.risk, last_investigation.signals)
            await ctx.send(sender, ChatMessage(content=[TextContent(text=docket_text)]))
            return
        await ctx.send(sender, ChatMessage(content=[TextContent(text="Please scan an offer letter or paste a message first to generate a customized cybercrime evidence docket.")]))
        return
    if action == "check_another" or _looks_like_chitchat(text):
        await ctx.send(sender, ChatMessage(content=[TextContent(text=WELCOME)]))
        return

    # 3. Check for Follow-Up Questions on Previously Analyzed Document
    latest_doc = _LAST_DOCUMENT_ANALYSIS.get(sender) or DOCUMENT_STORE.get_latest_analysis(sender)
    if latest_doc and is_follow_up_question(text):
        answer = await answer_document_question(text, latest_doc, logger=ctx.logger)
        await ctx.send(sender, ChatMessage(content=[TextContent(text=answer)]))
        return

    # 4. Standard Text Offer Investigation
    result, is_offer = await investigate(ctx, text)
    if not is_offer and not result.signals:
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
                "👉 Paste the offer message or **upload an offer letter** (PDF, DOCX, Image) and I'll run a forensic scan with live evidence."
            )
        await ctx.send(sender, ChatMessage(content=[TextContent(text=advice_text)]))
        return

<<<<<<< HEAD
=======
    # Repeat scammers are caught by the shared scam memory inside investigate().
    # Keep this user's latest result for the one-click cybercrime docket
    # (ctx is rebuilt for every message, so it can't hold state).
    if len(_LAST_RESULT) > 500:
        _LAST_RESULT.clear()
>>>>>>> 0af5ad58c0415d3f45fb8a6097c4b433ba917c5f
    _LAST_RESULT[sender] = result

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
        description="Paste an offer message or upload an offer letter (PDF, Word, Image); Jaanch checks it for scam signs and provides evidence-backed risk analysis.",
        handle_messages_concurrently=True,
    )
    agent.include(chat_proto, publish_manifest=True)
    agent.include(verify_proto, publish_manifest=True)
    return agent
