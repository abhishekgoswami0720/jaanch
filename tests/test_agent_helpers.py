import json

from agents.orchestrator import _looks_like_chitchat, _selection
from jaanch.cards import card_message, verdict_card
from jaanch.models import Signal


def depth(node, d=1):
    kids = node.get("children", []) if isinstance(node, dict) else []
    return max([d] + [depth(k, d + 1) for k in kids])


def test_card_fits_asi_one_limits():
    sigs = [Signal(id=f"s{i}", label="x" * 80, weight=2, evidence="y" * 300) for i in range(10)]
    payload = verdict_card(10, "high_risk", "High risk", sigs, ["a.com", "b.in"])
    assert depth(payload["root"]) <= 8
    assert len(json.dumps(payload)) < 64_000
    msg = card_message("narration", payload)
    meta = msg.content[1].metadata
    assert meta["card_protocol_version"] == "1" and meta["card_kind"] == "custom"
    assert all(isinstance(v, str) for v in meta.values())


def test_card_selection_parsing():
    assert _selection('{"action": "how_to_report"}')["action"] == "how_to_report"
    assert _selection("The user chose: How do I report this?")["action"] == "how_to_report"
    assert _selection("check_another")["action"] == "check_another"
    assert _selection("Dear candidate, pay ₹999") == {}


def test_chitchat_detection():
    assert _looks_like_chitchat("hi")
    assert _looks_like_chitchat("what can you do")
    assert not _looks_like_chitchat("Is infosys-careers.in real?")
    assert not _looks_like_chitchat("Pay registration fee of ₹1,499 to confirm your internship seat today")
