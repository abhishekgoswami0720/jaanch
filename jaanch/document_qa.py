"""Conversational Q&A engine for follow-up questions on analyzed offer letters.

Allows students and job seekers to ask questions about an earlier analyzed
document in the same conversation without triggering expensive re-scans.

Understands:
- "Why is this offer suspicious?"
- "Which exact details indicate fraud?"
- "Check the company domain."
- "Is the stipend realistic?"
- "What should I verify before joining?"
- "Summarize the findings."
"""

import json
import logging
import re
from typing import Optional

from .document_analyzer import DocumentAnalysisResult
from .llm import _chat

LOGGER = logging.getLogger("jaanch.document_qa")

DOC_QA_SYSTEM_PROMPT = """You are Jaanch, an AI job and internship scam detection assistant for Indian students.
You are answering a user's follow-up question about an offer letter that was already scanned.
Rely strictly on the verified analysis and evidence provided below.
Do not invent facts, companies, or domain records that are not in the analysis.
Keep your response concise (under 120 words), direct, and empathetic.
Highlight exact evidence, locations (e.g. Page 1), and actionable advice."""


def is_follow_up_question(text: str) -> bool:
    """Detects if an incoming message is a follow-up question about an analyzed document."""
    low = text.lower().strip()
    if len(low) < 5:
        return False

    follow_up_patterns = [
        r"why\s+(?:is\s+)?(?:this|it|the offer|my offer)",
        r"(?:which|what)\s+(?:exact\s+)?details",
        r"(?:indicate|shows?|mean)\s+fraud",
        r"(?:check|verify)\s+(?:the\s+)?(?:company\s+)?domain",
        r"(?:is\s+)?(?:the\s+)?(?:stipend|salary|pay)\s+(?:realistic|genuine|fake|high|normal)",
        r"what\s+should\s+i\s+(?:verify|do|check)",
        r"(?:summarize|summary|overview)\s+(?:the\s+)?findings",
        r"tell\s+me\s+more\s+about\s+(?:the|this)",
        r"can\s+i\s+trust\s+(?:this|them)",
        r"is\s+it\s+safe",
    ]
    return any(re.search(p, low) for p in follow_up_patterns)


def generate_rule_based_answer(question: str, analysis: DocumentAnalysisResult) -> str:
    """Provides deterministic, structured answers to standard follow-up questions."""
    q_low = question.lower()
    fields = analysis.extracted_fields
    comp = fields.get("company_name") or "the company"

    # 1. Why suspicious / Why fraud?
    if "why" in q_low or "suspicious" in q_low or "fraud" in q_low or "risk" in q_low:
        lines = [
            f"**Why this offer is classified as {analysis.classification} ({analysis.risk_score}/100):**\n"
        ]
        if analysis.risk_indicators:
            for i, ind in enumerate(analysis.risk_indicators[:3], start=1):
                lines.append(f"{i}. **{ind['indicator']}** [{ind.get('location', 'Page 1')}]: {ind['explanation']}")
                if ind.get("evidence"):
                    lines.append(f"   *Evidence quote:* \"{ind['evidence']}\"")
        else:
            lines.append("No major red flags were detected in the text, but authentic employer verification is still recommended.")
        return "\n".join(lines)

    # 2. Which exact details indicate fraud?
    if "detail" in q_low or "exact" in q_low or "evidence" in q_low or "quote" in q_low:
        lines = ["**Exact suspicious evidence detected in your document:**\n"]
        if analysis.risk_indicators:
            for ind in analysis.risk_indicators:
                lines.append(f"• **{ind.get('location', 'Document')}** — {ind['indicator']}")
                lines.append(f"  *Direct Quote:* \"{ind['evidence']}\"")
        else:
            lines.append("• No specific fraudulent phrases were flagged in the document.")
        return "\n".join(lines)

    # 3. Check the company domain
    if "domain" in q_low or "website" in q_low or "email" in q_low:
        verif = analysis.company_verification
        dom = fields.get("company_domain") or fields.get("company_website") or "Not provided"
        recruiter_email = fields.get("recruiter_email") or "Not provided"
        lines = [
            "**Company & Domain Verification Report:**",
            f"• Employer Domain: `{dom}`",
            f"• Recruiter Email: `{recruiter_email}`",
            f"• Verification Status: **{verif.get('verification_status', 'Unverified')}**",
        ]
        if verif.get("sources"):
            lines.append(f"• Sources Checked: {', '.join(verif['sources'])}")
        if verif.get("recruiter_verified"):
            lines.append("✓ Recruiter email matches the verified corporate domain.")
        else:
            lines.append("▲ Recruiter identity could not be verified against official corporate registries.")
        return "\n".join(lines)

    # 4. Is the stipend realistic?
    if "stipend" in q_low or "salary" in q_low or "pay" in q_low or "money" in q_low:
        stipend = fields.get("stipend") or "Not clearly specified"
        role = fields.get("role") or "Intern / Trainee"
        lines = [
            f"**Compensation Analysis for {role}:**",
            f"• Stated Compensation: **{stipend}**",
        ]
        if any(ind["indicator"] == "Unrealistic Compensation Claims" for ind in analysis.risk_indicators):
            lines.append(
                "▲ **High concern:** The offered pay is unusually high for early-career or part-time work without a standard interview. "
                "Scammers commonly promise ₹25,000–₹50,000/month for minimal data-entry tasks to entice students into paying registration fees."
            )
        elif fields.get("requested_payment"):
            lines.append(
                f"▲ **Major contradiction:** The offer promises {stipend} but demands an upfront payment of {fields.get('requested_payment')}. "
                "Genuine employment pays you; you should never pay the employer."
            )
        else:
            lines.append("• The compensation terms appear typical, but confirm payment schedules directly with the company.")
        return "\n".join(lines)

    # 5. What should I verify before joining?
    if "verify" in q_low or "should i do" in q_low or "action" in q_low or "steps" in q_low:
        lines = [f"**Concrete Next Steps Before You Proceed with {comp}:**\n"]
        for i, act in enumerate(analysis.recommended_actions, start=1):
            lines.append(f"{i}. {act}")
        return "\n".join(lines)

    # 6. Default: Summary of findings
    lines = [
        f"**Summary of Analysis for {comp} ({analysis.classification} · {analysis.risk_score}/100):**",
        f"• Role: {fields.get('role') or 'Not specified'}",
        f"• Joining Date: {fields.get('joining_date') or 'Not specified'}",
        f"• Upfront Payment Demanded: {fields.get('requested_payment') or 'None detected'}",
        f"• Summary: {analysis.summary}",
    ]
    if analysis.limitations:
        lines.append(f"• Limitations: {analysis.limitations[0]}")
    return "\n".join(lines)


async def answer_document_question(
    question: str,
    analysis: DocumentAnalysisResult,
    logger=None,
) -> str:
    """Answers a user follow-up question using LLM with deterministic template fallback."""
    # Build compact context for LLM
    context_str = (
        f"Document: {analysis.filename}\n"
        f"Classification: {analysis.classification} (Risk Score: {analysis.risk_score}/100)\n"
        f"Confidence: {analysis.confidence}\n"
        f"Extracted Fields: {json.dumps(analysis.extracted_fields)}\n"
        f"Risk Indicators: {json.dumps(analysis.risk_indicators)}\n"
        f"Positive Signals: {json.dumps(analysis.positive_signals)}\n"
        f"Verification: {json.dumps(analysis.company_verification)}\n"
        f"Summary: {analysis.summary}\n"
        f"Recommended Actions: {json.dumps(analysis.recommended_actions)}\n"
    )

    try:
        out = await _chat([
            {"role": "system", "content": DOC_QA_SYSTEM_PROMPT},
            {"role": "user", "content": f"Verified Document Context:\n{context_str}\n\nUser Question:\n{question}"},
        ], max_tokens=300)
        if out and out.strip():
            return out.strip()
    except Exception as err:
        if logger:
            logger.warning(f"ASI1 follow-up Q&A failed, using deterministic handler: {err}")

    return generate_rule_based_answer(question, analysis)
