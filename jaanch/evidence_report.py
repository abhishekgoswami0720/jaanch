"""Signed evidence reports: the paid product behind the Payment Protocol.

The scam check itself is always free. A placement cell forwarding an offer to
its students, or a student filing a police complaint, can buy a report that
Jaanch signs with its agent key. Anyone can later prove the report came from
Jaanch and was not edited, using only Jaanch's public agent address.

The report holds a fingerprint of the message, never the message itself.
"""

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Optional

from uagents_core.identity import Identity

from .models import Signal


def message_sha256(text: str) -> str:
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()


def build_report(text: str, risk: int, verdict: str, verdict_text: str, signals: list[Signal],
                 checked: list[str], payment_tx: Optional[str] = None,
                 now: Optional[datetime] = None) -> dict:
    now = now or datetime.now(timezone.utc)
    return {
        "report": "Jaanch signed evidence report",
        "report_id": str(uuid.uuid4()),
        "checked_at_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "message_sha256": message_sha256(text),
        "risk_score": risk,
        "verdict": verdict,
        "verdict_text": verdict_text,
        "evidence": [
            {"finding": s.label, "evidence": (s.evidence or "")[:160], "points": s.weight, "source": s.source}
            for s in signals
        ],
        "checked_live": list(checked),
        "payment_tx": payment_tx,
    }


def canonical(report: dict) -> str:
    return json.dumps(report, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def report_digest(report: dict) -> bytes:
    return hashlib.sha256(canonical(report).encode("utf-8")).digest()


def sign_report(report: dict, identity: Identity) -> str:
    return identity.sign_digest(report_digest(report))


def verify_report(report: dict, signer_address: str, signature: str) -> bool:
    try:
        return Identity.verify_digest(signer_address, report_digest(report), signature)
    except Exception:
        return False


def render_report(report: dict, signer_address: str, signature: str) -> str:
    lines = [
        "🔏 **Jaanch signed evidence report**",
        "",
        f"**Verdict:** {report['verdict_text']} ({report['risk_score']}/10)",
        f"**Checked at:** {report['checked_at_utc']}",
        "",
        "**Evidence**",
    ]
    for i, e in enumerate(report["evidence"], 1):
        detail = f" ({e['evidence']})" if e["evidence"] else ""
        lines.append(f"{i}. {e['finding']}{detail}")
    if not report["evidence"]:
        lines.append("No scam signals found.")
    lines += [
        "",
        f"**Signed by Jaanch:** `{signer_address}`",
        f"**Signature:** `{signature}`",
        "",
        "Keep the block below unchanged. Anyone can prove this report came from Jaanch and was not edited "
        "by running `python scripts/verify_report.py` from the Jaanch repository.",
        "```json",
        canonical(report),
        "```",
    ]
    return "\n".join(lines)
