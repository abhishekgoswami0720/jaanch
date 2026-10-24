import asyncio
import logging
import subprocess
import sys
from types import SimpleNamespace

from conftest import ROOT
from uagents_core.contrib.protocols.chat import ChatMessage, TextContent
from uagents_core.contrib.protocols.payment import (
    CancelPayment,
    CommitPayment,
    CompletePayment,
    Funds,
    RejectPayment,
    RequestPayment,
)
from uagents_core.identity import Identity

from agents import payments
from jaanch import fet_payments
from jaanch.evidence_report import build_report, render_report, sign_report, verify_report
from jaanch.models import Signal

AGENT_WALLET = "fetch1jaanchwallet"
BUYER = "fetch1buyerwallet"
TX = "A" * 64


def tx(recipient=AGENT_WALLET, sender=BUYER, amount="100000000000000000atestfet", code=0):
    return SimpleNamespace(code=code, logs=[], events={"transfer": {
        "recipient": recipient, "sender": sender, "amount": amount}})


# ---- ledger check ----------------------------------------------------------------

def test_transfer_to_jaanch_of_the_right_amount_is_accepted():
    assert fet_payments.check_transfer(tx(), AGENT_WALLET, "0.1", buyer=BUYER, coin_denom="atestfet")[0]


def test_wrong_recipient_low_amount_failed_tx_and_wrong_buyer_are_refused():
    assert not fet_payments.check_transfer(tx(recipient="fetch1someoneelse"), AGENT_WALLET, "0.1", coin_denom="atestfet")[0]
    assert not fet_payments.check_transfer(tx(amount="1000atestfet"), AGENT_WALLET, "0.1", coin_denom="atestfet")[0]
    assert not fet_payments.check_transfer(tx(code=5), AGENT_WALLET, "0.1", coin_denom="atestfet")[0]
    assert not fet_payments.check_transfer(tx(), AGENT_WALLET, "0.1", buyer="fetch1other", coin_denom="atestfet")[0]
    assert not fet_payments.check_transfer(tx(amount="100000000000000000afet"), AGENT_WALLET, "0.1", coin_denom="atestfet")[0]


def test_malformed_hash_is_refused_without_touching_the_network():
    ok, why = fet_payments.verify_payment("not-a-hash", AGENT_WALLET, "0.1")
    assert not ok and "hash" in why


def test_testnet_is_the_default(monkeypatch):
    monkeypatch.delenv("JAANCH_FET_TESTNET", raising=False)
    assert fet_payments.use_testnet() and fet_payments.denom() == "atestfet"


# ---- signed report ---------------------------------------------------------------

def _report():
    sigs = [Signal(id="fee_demand", label="Asks you to pay a fee", weight=4.0, evidence="fee ₹1,499", source="pattern-agent")]
    return build_report("pay ₹1,499 now", 10, "high_risk", "High risk: this looks like a scam", sigs, ["t.me"], payment_tx=TX)


def test_signed_report_verifies_and_detects_tampering():
    identity = Identity.from_seed("jaanch test seed for reports", 0)
    report = _report()
    signature = sign_report(report, identity)
    assert verify_report(report, identity.address, signature)
    edited = dict(report, risk_score=1)
    assert not verify_report(edited, identity.address, signature)
    assert "pay ₹1,499 now" not in render_report(report, identity.address, signature)  # only a fingerprint


def test_verify_script_accepts_a_copied_report(tmp_path):
    identity = Identity.from_seed("jaanch test seed for reports", 0)
    report = _report()
    text = render_report(report, identity.address, sign_report(report, identity))
    path = tmp_path / "report.txt"
    path.write_text(text, encoding="utf-8")
    ok = subprocess.run([sys.executable, str(ROOT / "scripts" / "verify_report.py"), str(path)], capture_output=True, text=True)
    assert ok.returncode == 0 and "VALID" in ok.stdout
    path.write_text(text.replace('"risk_score":10', '"risk_score":1'), encoding="utf-8")
    bad = subprocess.run([sys.executable, str(ROOT / "scripts" / "verify_report.py"), str(path)], capture_output=True, text=True)
    assert bad.returncode == 1


# ---- the protocol flow -----------------------------------------------------------

class Store(dict):
    def set(self, k, v):
        self[k] = v


class FakeCtx:
    def __init__(self, store):
        identity = Identity.from_seed("jaanch test seed for reports", 0)
        self.storage = store
        self.logger = logging.getLogger("test")
        self.agent = SimpleNamespace(identity=identity, address=identity.address)
        self.sent = []

    async def send(self, to, msg):
        self.sent.append(msg)


def _result():
    return SimpleNamespace(risk=10, verdict="high_risk", verdict_text="High risk: this looks like a scam",
                           signals=[Signal(id="fee_demand", label="Asks you to pay a fee", weight=4.0)],
                           checked=[])


def _commit(tx_id=TX):
    return CommitPayment(funds=Funds(amount="0.1", currency="FET", payment_method="fet_direct"),
                         recipient=AGENT_WALLET, transaction_id=tx_id, metadata={"buyer_fet_wallet": BUYER})


def test_full_payment_flow_and_replay_protection(monkeypatch):
    monkeypatch.setitem(payments.WALLET, "address", AGENT_WALLET)
    monkeypatch.setattr(fet_payments, "verify_payment", lambda tx_id, rcpt, amt, buyer=None: (True, "ok"))
    store = Store()

    ctx = FakeCtx(store)
    asyncio.run(payments.request_report_payment(ctx, "user1", "pay ₹1,499 now", _result()))
    request = ctx.sent[-1]
    assert isinstance(request, RequestPayment) and request.recipient == AGENT_WALLET
    assert request.accepted_funds[0].currency == "FET" and request.metadata["fet_network"]

    ctx = FakeCtx(store)
    asyncio.run(payments.on_commit(ctx, "user1", _commit()))
    assert isinstance(ctx.sent[0], CompletePayment)
    report_text = ctx.sent[1].content[0].text
    assert "signed evidence report" in report_text and TX in report_text

    # The same transaction can't buy a second report.
    asyncio.run(payments.request_report_payment(FakeCtx(store), "user1", "pay ₹1,499 now", _result()))
    ctx = FakeCtx(store)
    asyncio.run(payments.on_commit(ctx, "user1", _commit()))
    assert isinstance(ctx.sent[0], CancelPayment) and "already used" in ctx.sent[0].reason


def test_failed_ledger_check_cancels_and_delivers_nothing(monkeypatch):
    monkeypatch.setitem(payments.WALLET, "address", AGENT_WALLET)
    monkeypatch.setattr(fet_payments, "verify_payment", lambda tx_id, rcpt, amt, buyer=None: (False, "no transfer"))
    store = Store()
    asyncio.run(payments.request_report_payment(FakeCtx(store), "user2", "text", _result()))
    ctx = FakeCtx(store)
    asyncio.run(payments.on_commit(ctx, "user2", _commit("B" * 64)))
    assert isinstance(ctx.sent[0], CancelPayment)
    assert not any("signed evidence report" in getattr(m.content[0], "text", "") for m in ctx.sent[1:]
                   if isinstance(m, ChatMessage))
    assert store == {}


def test_commit_without_a_request_is_cancelled(monkeypatch):
    monkeypatch.setitem(payments.WALLET, "address", AGENT_WALLET)
    payments.PENDING.pop("stranger", None)
    ctx = FakeCtx(Store())
    asyncio.run(payments.on_commit(ctx, "stranger", _commit("C" * 64)))
    assert isinstance(ctx.sent[0], CancelPayment)


def test_reject_keeps_everything_free():
    ctx = FakeCtx(Store())
    asyncio.run(payments.on_reject(ctx, "user3", RejectPayment(reason="no thanks")))
    assert isinstance(ctx.sent[0], ChatMessage) and "free" in ctx.sent[0].content[0].text
