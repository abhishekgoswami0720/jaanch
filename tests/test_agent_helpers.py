import json

from agents.orchestrator import _looks_like_chitchat, _selection, _strip_mention
from jaanch.cards import card_message, generate_cybercrime_docket, verdict_card
from jaanch.models import OfferFacts, Signal


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
    assert _selection("Copy Cybercrime Docket")["action"] == "get_docket"
    assert _selection("check_another")["action"] == "check_another"
    assert _selection("Dear candidate, pay ₹999") == {}


def test_generate_cybercrime_docket():
    facts = OfferFacts(
        text="Pay ₹1,500 to recruiter@okaxis for Infosys placement",
        company="Infosys",
        fee="₹1,500",
        phones=["9876543210"],
        upis=["recruiter@okaxis"],
        domains=["fake-infosys.in"],
    )
    sigs = [Signal(id="fee_demand", label="Asks fee", weight=4, evidence="₹1,500", source="pattern-agent")]
    docket = generate_cybercrime_docket(facts, 9, sigs)
    assert "OFFICIAL CYBERCRIME COMPLAINT DOCKET" in docket
    assert "1930" in docket
    assert "recruiter@okaxis" in docket
    assert "fake-infosys.in" in docket
    assert "9876543210" in docket


def test_chitchat_detection():
    assert _looks_like_chitchat("hi")
    assert _looks_like_chitchat("what can you do")
    assert _looks_like_chitchat("@jaanch-scam-check hi")
    assert not _looks_like_chitchat("Is infosys-careers.in real?")
    assert not _looks_like_chitchat("Pay registration fee of ₹1,499 to confirm your internship seat today")


def test_strip_mention():
    assert _strip_mention("@jaanch-scam-check tell me what a fake internship looks like") == "tell me what a fake internship looks like"
    assert _strip_mention("@jaanch hello") == "hello"
    assert _strip_mention("Just a normal text") == "Just a normal text"


def test_file_paths_in_chat_are_never_read(tmp_path):
    """Anyone on ASI:One can message the agent; a path must not make it read local files."""
    from uagents_core.contrib.protocols.chat import ChatMessage, TextContent

    from agents.orchestrator import _extract_document_attachment

    secret = tmp_path / "private_notes.txt"
    secret.write_text("not for strangers", encoding="utf-8")
    msg = ChatMessage(content=[TextContent(text=str(secret))])
    assert _extract_document_attachment(msg, str(secret)) is None


def test_specialist_seeds_never_fall_back_to_public_dev_seeds(monkeypatch):
    """With only JAANCH_SEED set, each specialist gets a private seed, and run.py
    computes the same address the agent itself will use."""
    import run
    from agents.specialists import REPUTATION_DEV_SEED, build_reputation_agent
    from uagents_core.identity import Identity

    monkeypatch.setenv("JAANCH_SEED", "a private test seed phrase for jaanch")
    monkeypatch.delenv("JAANCH_REPUTATION_SEED", raising=False)
    agent = build_reputation_agent(False, port=8199)
    assert agent.address != Identity.from_seed(REPUTATION_DEV_SEED, 0).address
    assert run._address("JAANCH_REPUTATION_SEED", REPUTATION_DEV_SEED) == agent.address
