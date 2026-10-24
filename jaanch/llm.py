"""ASI1 calls: pull structured facts out of messy text, and explain the verdict.

ASI1 never decides the score. If no key is set or a call fails, the agent
falls back to rule-based extraction and a template explanation.
"""

import json
import os
import re
from typing import Optional

import aiohttp

from .extract import extract_rules
from .models import OfferFacts, Signal

ASI1_URL = "https://api.asi1.ai/v1/chat/completions"
MODEL = os.getenv("ASI1_MODEL", "asi1")

EXTRACT_PROMPT = """You extract facts from a job or internship offer message that an Indian student received.
Return ONLY a JSON object with these keys (use null when absent, never guess):
{"company": string|null, "role": string|null, "pay": string|null, "fee": string|null,
 "is_offer": boolean}
- company: the employer the message claims to hire for.
- pay: the salary/stipend/earning claim, quoted from the text.
- fee: any money the candidate is asked to pay (registration, training, deposit, kit...), quoted.
- is_offer: false if the text is not a job/internship/recruitment message at all."""

EXPLAIN_PROMPT = """You are Jaanch, an agent that checks job and internship offers for scams.
Write a short reply (max 90 words) to the student explaining the result below.
Rules: use only the evidence given, do not invent facts, do not change the score.
Start with the verdict line. Then the 2-3 most important reasons in plain words.
End with one concrete next step. If the user's message was in Hinglish, reply in simple Hinglish."""

ADVISE_PROMPT = """You are Jaanch (जाँच), an expert AI scam-check assistant for Indian students and job seekers.
The user asked a general question, greeting, or requested advice (NOT an offer to evaluate).
Give a concise, helpful, and empathetic answer (under 120 words).
If they ask what scams look like or how to spot them:
- Highlight common red flags: paying registration/security/training/laptop fees, tasks like YouTube liking, moving to personal Telegram/WhatsApp, lookalike emails (@gmail instead of official company domain).
- Give a brief example if appropriate.
Always invite them to paste any suspicious job offer or message so you can run a full live scan with evidence."""


def _key() -> Optional[str]:
    return os.getenv("ASI1_API_KEY") or os.getenv("ASI_ONE_API_KEY")


async def _chat(messages: list[dict], max_tokens: int = 400) -> Optional[str]:
    key = _key()
    if not key:
        return None
    body = {"model": MODEL, "messages": messages, "max_tokens": max_tokens, "temperature": 0}
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    timeout = aiohttp.ClientTimeout(total=25)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(ASI1_URL, json=body, headers=headers) as resp:
            if resp.status != 200:
                raise RuntimeError(f"ASI1 HTTP {resp.status}: {(await resp.text())[:200]}")
            data = await resp.json()
    return data["choices"][0]["message"]["content"]


def _parse_json(raw: str) -> dict:
    raw = raw.strip()
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    return json.loads(m.group(0) if m else raw)


async def extract(text: str, logger=None) -> tuple[OfferFacts, bool]:
    """Returns (facts, is_offer). Contacts always come from the rules, which don't hallucinate."""
    facts = extract_rules(text)
    is_offer = True
    try:
        raw = await _chat([
            {"role": "system", "content": EXTRACT_PROMPT},
            {"role": "user", "content": text[:6000]},
        ])
        if raw:
            data = _parse_json(raw)
            facts.company = data.get("company") or facts.company
            facts.role = data.get("role") or facts.role
            facts.pay = data.get("pay") or facts.pay
            # Only trust an LLM-reported fee if the quoted text really is in the message.
            fee = data.get("fee")
            if fee and fee.lower() in text.lower():
                facts.fee = fee
            is_offer = bool(data.get("is_offer", True))
            facts.extracted_by = "asi1"
    except Exception as err:  # network, quota, bad JSON: fall back to rules
        if logger:
            logger.warning(f"ASI1 extraction failed, using rules only: {err}")

    # Heuristic fallback: if no key was set or extraction didn't run,
    # questions or short texts without offer indicators shouldn't be tagged as an offer
    if not facts.company and not facts.fee and not facts.pay and not facts.emails and not facts.urls and not facts.phones:
        # Check if text is a question or lacks typical offer keywords
        q_markers = ("what", "how", "tell me", "why", "who", "when", "can you", "explain", "?")
        low = text.lower().strip()
        if any(low.startswith(m) or low.endswith("?") for m in q_markers):
            is_offer = False

    return facts, is_offer


def template_explanation(risk: int, verdict_text: str, signals: list[Signal]) -> str:
    risky = [s for s in signals if s.weight > 0][:3]
    good = [s for s in signals if s.weight < 0][:2]
    lines = [f"**{verdict_text} ({risk}/10)**"]
    for s in risky:
        lines.append(f"- {s.label}")
    for s in good:
        lines.append(f"- ✓ {s.label}")
    if risk >= 7:
        lines.append("Do not pay anything or share OTPs. Report it at cybercrime.gov.in or call 1930.")
    elif risk >= 4:
        lines.append("Check the company's official careers page and email them from there before you reply.")
    else:
        lines.append("Still never pay to get a job; genuine employers don't charge candidates.")
    return "\n".join(lines)


async def explain(user_text: str, risk: int, verdict_text: str, signals: list[Signal], logger=None) -> str:
    fallback = template_explanation(risk, verdict_text, signals)
    evidence = "\n".join(f"- {s.label} ({'+' if s.weight > 0 else ''}{s.weight}) [{s.evidence}]" for s in signals)
    try:
        out = await _chat([
            {"role": "system", "content": EXPLAIN_PROMPT},
            {"role": "user", "content": (
                f"User message (first 600 chars):\n{user_text[:600]}\n\n"
                f"Verdict: {verdict_text}\nRisk score: {risk}/10\nEvidence:\n{evidence or '- none'}"
            )},
        ], max_tokens=300)
        if out and f"{risk}/10" in out:
            return out.strip()
        if out:
            return f"**{verdict_text} ({risk}/10)**\n{out.strip()}"
    except Exception as err:
        if logger:
            logger.warning(f"ASI1 explanation failed, using template: {err}")
    return fallback


async def advise(user_text: str, logger=None) -> Optional[str]:
    """Answers general questions, guidelines, or advice about job scams without scoring."""
    try:
        out = await _chat([
            {"role": "system", "content": ADVISE_PROMPT},
            {"role": "user", "content": user_text[:1000]},
        ], max_tokens=250)
        if out and out.strip():
            return out.strip()
    except Exception as err:
        if logger:
            logger.warning(f"ASI1 advice failed: {err}")
    return None
