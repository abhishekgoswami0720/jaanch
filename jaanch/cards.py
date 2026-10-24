"""ASI:One interactive cards and complaint dockets for Jaanch.

Provides:
- verdict_card: for pasted offer messages (1-10 scale)
- document_analysis_card: for uploaded offer letters (0-100 scale, full evidence)
- generate_cybercrime_docket: for pasted messages
- generate_document_cybercrime_docket: for analyzed documents
"""

import json
from typing import Any, Dict, List, Optional

from uagents_core.contrib.protocols.chat import ChatMessage, MetadataContent, TextContent

from .models import OfferFacts, Signal

VARIANT = {
    "high_risk": "warning",
    "suspicious": "warning",
    "low_risk": "success",
    "LIKELY FRAUD": "warning",
    "SUSPICIOUS": "warning",
    "LIKELY GENUINE": "success",
    "INSUFFICIENT EVIDENCE": "neutral",
}


def verdict_card(risk: int, verdict: str, verdict_text: str, signals: list[Signal],
                 checked: list[str]) -> dict:
    rows = []
    for s in signals[:6]:
        mark = "▲" if s.weight > 0 else "✓"
        rows.append({"type": "text", "value": f"{mark} {s.label}", "style": "body"})
        if s.evidence:
            rows.append({"type": "text", "value": f"   {s.evidence[:120]}", "style": "muted"})
    if not rows:
        rows.append({"type": "text", "value": "No scam signals found in the text or the domains.", "style": "body"})

    children = [
        {"type": "group", "direction": "row", "gap": 8, "children": [
            {"type": "badge", "label": f"Risk {risk}/10", "variant": VARIANT.get(verdict, "warning")},
            {"type": "badge", "label": verdict.replace("_", " ").title(), "variant": VARIANT.get(verdict, "warning")},
        ]},
        {"type": "heading", "value": verdict_text, "level": 2},
        {"type": "divider"},
        {"type": "section", "title": "Evidence", "children": rows},
    ]
    if checked:
        children.append({"type": "text", "value": "Domains checked live: " + ", ".join(checked), "style": "muted"})
    button_group = [
        {"type": "button", "label": "How do I report this?", "primary": risk >= 7,
         "action": {"selection": {"action": "how_to_report"}}},
        {"type": "button", "label": "Copy Cybercrime Docket", "primary": False,
         "action": {"selection": {"action": "get_docket"}}},
        {"type": "button", "label": "Check another offer", "primary": False,
         "action": {"selection": {"action": "check_another"}}},
    ]
    children.append({"type": "group", "direction": "row", "gap": 8, "children": button_group})
    return {"root": {"type": "section", "title": "Jaanch offer check", "children": children}}


def document_analysis_card(analysis: Any) -> dict:
    """Renders a rich interactive ASI:One card for an analyzed offer letter document."""
    data = analysis if isinstance(analysis, dict) else analysis.to_dict()

    risk_score = data.get("risk_score", 0)
    classification = data.get("classification", "SUSPICIOUS")
    confidence = data.get("confidence", "Moderate")
    summary = data.get("summary", "")
    fields = data.get("extracted_fields", {})
    indicators = data.get("risk_indicators", [])
    positives = data.get("positive_signals", [])
    verif = data.get("company_verification", {})

    # Top badges
    badges = [
        {"type": "badge", "label": f"Risk {risk_score}/100", "variant": VARIANT.get(classification, "warning")},
        {"type": "badge", "label": classification, "variant": VARIANT.get(classification, "warning")},
        {"type": "badge", "label": f"Confidence: {confidence}", "variant": "neutral"},
    ]

    # Extracted fields rows
    extracted_rows = [
        {"type": "text", "value": f"🏢 Employer: {fields.get('company_name') or 'Not specified'}", "style": "body"},
        {"type": "text", "value": f"💼 Role: {fields.get('role') or 'Not specified'}", "style": "body"},
        {"type": "text", "value": f"💰 Stipend / Salary: {fields.get('stipend') or 'Not specified'}", "style": "body"},
        {"type": "text", "value": f"📅 Joining Date: {fields.get('joining_date') or 'Not specified'}", "style": "body"},
    ]
    if fields.get("requested_payment"):
        extracted_rows.append({
            "type": "text",
            "value": f"⚠️ Demanded Fee / Deposit: {fields.get('requested_payment')}",
            "style": "body",
        })

    # Evidence rows
    evidence_rows = []
    for ind in indicators[:5]:
        loc = f"[{ind.get('location', 'Page 1')}] " if ind.get("location") else ""
        sev = f"({ind.get('severity', 'Medium')}) "
        evidence_rows.append({"type": "text", "value": f"▲ {loc}{sev}{ind.get('indicator')}", "style": "body"})
        if ind.get("evidence"):
            evidence_rows.append({"type": "text", "value": f"   Quote: {ind.get('evidence')[:120]}", "style": "muted"})

    for pos in positives[:3]:
        evidence_rows.append({"type": "text", "value": f"✓ {pos.get('signal')}", "style": "body"})
        if pos.get("explanation"):
            evidence_rows.append({"type": "text", "value": f"   {pos.get('explanation')[:120]}", "style": "muted"})

    if not evidence_rows:
        evidence_rows.append({"type": "text", "value": "No suspicious indicators identified.", "style": "body"})

    children = [
        {"type": "group", "direction": "row", "gap": 8, "children": badges},
        {"type": "heading", "value": summary, "level": 2},
        {"type": "divider"},
        {"type": "section", "title": "Extracted Offer Details", "children": extracted_rows},
        {"type": "section", "title": "Evidence & Warning Signs", "children": evidence_rows},
    ]

    # Verification footnote
    v_status = verif.get("verification_status")
    if v_status:
        children.append({"type": "text", "value": f"Verification status: {v_status}", "style": "muted"})

    # Buttons
    button_group = [
        {"type": "button", "label": "Copy Cybercrime Docket", "primary": risk_score >= 70,
         "action": {"selection": {"action": "get_docket"}}},
        {"type": "button", "label": "How do I report this?", "primary": False,
         "action": {"selection": {"action": "how_to_report"}}},
        {"type": "button", "label": "Scan another document", "primary": False,
         "action": {"selection": {"action": "check_another"}}},
    ]
    children.append({"type": "group", "direction": "row", "gap": 8, "children": button_group})

    return {"root": {"type": "section", "title": "Jaanch Offer Letter Analysis", "children": children}}


def generate_document_cybercrime_docket(analysis: Any) -> str:
    """Generates an official pre-formatted cybercrime complaint docket for an offer letter."""
    data = analysis if isinstance(analysis, dict) else analysis.to_dict()
    fields = data.get("extracted_fields", {})
    indicators = data.get("risk_indicators", [])
    risk = data.get("risk_score", 0)

    phones = fields.get("contact_numbers") or []
    upis = fields.get("payment_methods") or []
    emails = [fields.get("recruiter_email")] if fields.get("recruiter_email") else []
    dom = fields.get("company_domain") or fields.get("company_website") or "None"

    lines = [
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "📋 OFFICIAL CYBERCRIME COMPLAINT DOCKET",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "Category: Job / Internship Offer Letter Fraud & Impersonation",
        "Target Portal: https://cybercrime.gov.in (Report Other Cyber Crime) & Chakshu",
        "National Helpline: 1930",
        "",
        "▶ SUSPECT PARTICULARS (FROM OFFER LETTER):",
        f"• Document Name: {data.get('filename', 'Offer_Letter.pdf')}",
        f"• Impersonated Company: {fields.get('company_name') or 'Not specified'}",
        f"• Purported Role: {fields.get('role') or 'Not specified'}",
        f"• Suspect Phone Number(s): {', '.join(phones) if phones else 'Not provided'}",
        f"• Suspect UPI Handle(s): {', '.join(upis) if upis else 'None detected'}",
        f"• Suspect Recruiter Email(s): {', '.join(emails) if emails else 'None provided'}",
        f"• Suspect Website / Domain: {dom}",
        f"• Demanded Upfront Payment: {fields.get('requested_payment') or 'None detected'}",
        "",
        "▶ FORENSIC EVIDENCE LOG (JAANCH AI):",
        f"• Risk Score: {risk}/100 ({data.get('classification', 'SUSPICIOUS')})",
        f"• Assessment Confidence: {data.get('confidence', 'Moderate')}",
    ]

    for ind in indicators[:5]:
        loc = f"[{ind.get('location', 'Page 1')}]"
        lines.append(f"  - {loc} {ind.get('indicator')}: {ind.get('evidence', '')[:80]}")

    lines.extend([
        "",
        "▶ INCIDENT SUMMARY FOR COMPLAINT NARRATION:",
        "The complainant received a deceptive offer letter document purportedly from the above organization. "
        "Forensic document analysis identified fraudulent indicators including unverified recruiter credentials, "
        "advance fee demands, or lookalike domain references. The document is submitted as primary evidence.",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
    ])
    return "\n".join(lines)


def generate_cybercrime_docket(facts: OfferFacts, risk: int, signals: list[Signal]) -> str:
    """Generates a pre-formatted incident report ready to paste into cybercrime.gov.in / Chakshu."""
    lines = [
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "📋 OFFICIAL CYBERCRIME COMPLAINT DOCKET",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "Category: Job / Internship Fraud & Financial Deception",
        "Target Portal: https://cybercrime.gov.in (Report Other Cyber Crime) & Chakshu",
        "National Helpline: 1930",
        "",
        "▶ SUSPECT PARTICULARS:",
        f"• Impersonated Entity: {facts.company or 'Not specified / Fake entity'}",
        f"• Suspect Phone Number(s): {', '.join(facts.phones) if facts.phones else 'Not provided'}",
        f"• Suspect UPI / Payment Handle: {', '.join(facts.upis) if facts.upis else 'None detected in text'}",
        f"• Suspect Email Address(es): {', '.join(facts.emails) if facts.emails else 'None provided'}",
        f"• Malicious / Unverified Domains: {', '.join(facts.domains) if facts.domains else 'None'}",
        f"• Demanded Upfront Fee / Deposit: {facts.fee or 'Pending / Conditional bait'}",
        "",
        "▶ FORENSIC EVIDENCE LOG (JAANCH AI):",
        f"• Risk Score: {risk}/10 (Severe Scam Probability)",
    ]
    for s in signals[:5]:
        lines.append(f"  - [{s.source}] {s.label}: {s.evidence[:80]}")
    lines.extend([
        "",
        "▶ INCIDENT SUMMARY FOR COMPLAINT NARRATION:",
        "The complainant received an unsolicited job/internship communication containing deceptive claims. "
        "The sender directed communication to unauthorized platforms/messaging groups and attempted upfront "
        "registration/deposit collection or sensitive data solicitation without authentic corporate verification.",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
    ])
    return "\n".join(lines)


def card_message(narration: str, payload: dict, end_session: bool = False) -> ChatMessage:
    return ChatMessage(content=[
        TextContent(text=narration),
        MetadataContent(metadata={
            "card_protocol_version": "1",
            "requires_card_interaction": "true",
            "card_kind": "custom",
            "card_payload": json.dumps(payload),
            "preferred_drawer_width_px": "520",
        }),
    ])


REPORT_STEPS = """**How to report a job scam in India**
1. Don't pay anything more and stop replying.
2. If you already paid or shared bank details, call the cyber-fraud helpline **1930** right away; fast reports give the best chance of freezing the money.
3. File a complaint at **cybercrime.gov.in** (choose "Report other cyber crime"). Keep screenshots, the sender's number/email and any payment IDs.
4. Report the number on **Sanchar Saathi → Chakshu** (sancharsaathi.gov.in) and report/block the chat in WhatsApp or Telegram.
5. Warn your college placement cell so they can alert other students."""

WELCOME = """Hi, I'm **Jaanch**. Paste a job or internship offer message or **upload an offer letter** (PDF, Word, or image) and I'll analyze it for fraud signs.

I check for fee demands, personal UPI requests, lookalike corporate domains, domain registration age, MX mail servers, and community scam complaints. You get a clear risk assessment with verifiable evidence."""
