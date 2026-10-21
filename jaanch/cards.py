"""ASI:One interactive card for the verdict.

If ASI:One can't render the card it shows the narration text instead, so the
narration always carries the full answer on its own.
"""

import json

from uagents_core.contrib.protocols.chat import ChatMessage, MetadataContent, TextContent

from .models import Signal

VARIANT = {"high_risk": "warning", "suspicious": "warning", "low_risk": "success"}


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
            {"type": "badge", "label": f"Risk {risk}/10", "variant": VARIANT[verdict]},
            {"type": "badge", "label": verdict.replace("_", " ").title(), "variant": VARIANT[verdict]},
        ]},
        {"type": "heading", "value": verdict_text, "level": 2},
        {"type": "divider"},
        {"type": "section", "title": "Evidence", "children": rows},
    ]
    if checked:
        children.append({"type": "text", "value": "Domains checked live: " + ", ".join(checked), "style": "muted"})
    children.append({"type": "group", "direction": "row", "gap": 8, "children": [
        {"type": "button", "label": "How do I report this?", "primary": risk >= 7,
         "action": {"selection": {"action": "how_to_report"}}},
        {"type": "button", "label": "Check another offer", "primary": False,
         "action": {"selection": {"action": "check_another"}}},
    ]})
    return {"root": {"type": "section", "title": "Jaanch offer check", "children": children}}


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

WELCOME = """Hi, I'm **Jaanch**. Paste a job or internship offer (the WhatsApp/Telegram message, email or offer letter text) and I'll check it for scam signs.

I check the message for fee demands, OTP/bank requests and pressure tactics, look up how old the recruiter's website is, whether its email domain is real, and whether it imitates a big company. You get a 1–10 risk score with the evidence."""
