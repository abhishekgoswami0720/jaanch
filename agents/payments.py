"""Payment Protocol (seller side): signed evidence reports for a small FET fee.

Monetisation model:
- Every scam check, the report steps and the complaint docket are free, always.
- A *signed evidence report* costs JAANCH_REPORT_PRICE_FET (default 0.1 FET).
  Placement cells buy one before forwarding an offer to students; victims attach
  one to a police complaint. Jaanch signs it with its agent key, so anyone can
  prove it is genuine and unedited.

Flow inside ASI:One:
  user clicks "Signed report" -> RequestPayment -> user approves in ASI:One
  -> CommitPayment(tx hash) -> Jaanch checks the transfer on the Fetch.ai ledger
  -> CompletePayment + the signed report. A failed check sends CancelPayment
  with the reason and nothing is charged twice: each transaction hash is
  accepted once.
"""

import asyncio
import time
import uuid
from dataclasses import dataclass

from uagents import Context, Protocol
from uagents_core.contrib.protocols.chat import ChatMessage, TextContent
from uagents_core.contrib.protocols.payment import (
    CancelPayment,
    CommitPayment,
    CompletePayment,
    Funds,
    RejectPayment,
    RequestPayment,
    payment_protocol_spec,
)

from jaanch import fet_payments
from jaanch.evidence_report import build_report, render_report, sign_report

payment_proto = Protocol(spec=payment_protocol_spec, role="seller")

DEADLINE_SECONDS = 300
WALLET = {"address": ""}  # Jaanch's FET wallet, set by build_orchestrator()


@dataclass
class PendingReport:
    reference: str
    text: str
    result: object  # jaanch.pipeline.Result
    created: float


PENDING: dict[str, PendingReport] = {}


def _say(text: str) -> ChatMessage:
    return ChatMessage(content=[TextContent(text=text)])


async def request_report_payment(ctx: Context, sender: str, text: str, result) -> None:
    """Ask the user to pay for a signed report of their latest check."""
    if not WALLET["address"]:
        await ctx.send(sender, _say("Signed reports aren't available on this deployment yet."))
        return
    reference = str(uuid.uuid4())
    PENDING[sender] = PendingReport(reference=reference, text=text, result=result, created=time.time())
    price = fet_payments.price_fet()
    await ctx.send(sender, RequestPayment(
        accepted_funds=[Funds(amount=price, currency="FET", payment_method="fet_direct")],
        recipient=WALLET["address"],
        deadline_seconds=DEADLINE_SECONDS,
        reference=reference,
        description=f"Jaanch signed evidence report for your last check ({price} FET). The check itself stays free.",
        metadata={
            "agent": "jaanch",
            "service": "signed_evidence_report",
            "fet_network": fet_payments.network_name(),
        },
    ))
    ctx.logger.info(f"payment requested: {price} FET, reference {reference}")


@payment_proto.on_message(CommitPayment)
async def on_commit(ctx: Context, sender: str, msg: CommitPayment):
    pending = PENDING.get(sender)
    tx = (msg.transaction_id or "").strip()

    async def cancel(reason: str):
        await ctx.send(sender, CancelPayment(transaction_id=tx or None, reason=reason))
        await ctx.send(sender, _say(f"⚠️ Payment not accepted: {reason}. Your free check result is unchanged."))
        ctx.logger.warning(f"payment cancelled: {reason}")

    if pending is None or time.time() - pending.created > DEADLINE_SECONDS + 60:
        PENDING.pop(sender, None)
        await cancel("there is no open report request; click 'Signed report' again")
        return
    if msg.funds.currency != "FET" or msg.funds.payment_method != "fet_direct":
        await cancel("only FET payments are accepted")
        return
    if ctx.storage.get(f"paid_tx:{tx.upper()}"):
        await cancel("this transaction was already used for a report")
        return

    meta = msg.metadata or {}
    buyer = meta.get("buyer_fet_wallet") or meta.get("buyer_fet_address")
    buyer = buyer if isinstance(buyer, str) else None
    ok, why = await asyncio.to_thread(
        fet_payments.verify_payment, tx, WALLET["address"], fet_payments.price_fet(), buyer)
    if not ok:
        await cancel(why)
        return

    ctx.storage.set(f"paid_tx:{tx.upper()}", {"reference": pending.reference, "at": int(time.time())})
    PENDING.pop(sender, None)
    await ctx.send(sender, CompletePayment(transaction_id=tx))

    r = pending.result
    report = build_report(pending.text, r.risk, r.verdict, r.verdict_text, r.signals, r.checked, payment_tx=tx)
    signature = sign_report(report, ctx.agent.identity)
    await ctx.send(sender, _say(render_report(report, ctx.agent.address, signature)))
    ctx.logger.info(f"payment verified ({tx[:12]}...); signed report {report['report_id']} sent")


@payment_proto.on_message(RejectPayment)
async def on_reject(ctx: Context, sender: str, msg: RejectPayment):
    PENDING.pop(sender, None)
    await ctx.send(sender, _say(
        "No problem. Your check, the report steps and the complaint docket stay free. "
        "Use 'Copy Cybercrime Docket' if you want to file a complaint."))
