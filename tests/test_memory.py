import asyncio
import json

from conftest import NOW, make_fetch, sample

from jaanch import memory
from jaanch.extract import extract_rules
from jaanch.pipeline import run_local


class DictStore(dict):
    """Same get/set interface as the agent's ctx.storage."""

    def set(self, key, value):
        self[key] = value


def run(text, store):
    return asyncio.run(run_local(text, fetch=make_fetch(), now=NOW, store=store, check_rep=False))


def test_same_scammer_in_a_different_message_is_caught():
    store = DictStore()
    before = run(sample("demo_same_scammer.txt"), DictStore())
    run(sample("scam_fee_whatsapp.txt"), store)  # a student reports the first scam
    after = run(sample("demo_same_scammer.txt"), store)  # another student gets a new message
    assert "seen_before" in {s.id for s in after.signals}
    assert after.risk > before.risk and after.verdict == "high_risk"


def test_checking_the_same_message_twice_is_not_seen_before():
    store = DictStore()
    run(sample("scam_fee_whatsapp.txt"), store)
    again = run(sample("scam_fee_whatsapp.txt"), store)
    assert "seen_before" not in {s.id for s in again.signals}


def test_only_high_risk_offers_are_remembered():
    store = DictStore()
    run(sample("genuine_campus_offer.txt"), store)
    run(sample("suspicious_new_startup.txt"), store)
    assert store == {}


def test_official_domains_and_platforms_are_never_stored():
    facts = extract_rules(
        "Pay fee now. Mail hr@infosys.com or placement@gla.ac.in, see https://careers.infosys.com, "
        "join t.me/jobs_now, form https://forms.gle/XXXXXXXX, call 98XXXXXXXX"
    )
    kinds = memory.identifiers(facts)
    assert ("telegram", "jobs_now") in kinds
    values = " ".join(v for _, v in kinds)
    assert "infosys" not in values and "gla.ac.in" not in values and "xxxx" not in values.lower()


def test_contacts_are_stored_only_as_fingerprints():
    store = DictStore()
    facts = extract_rules("Pay ₹999 to priya.hr@ybl, call +91 98765 43210, mail jobs.hr@gmail.com")
    assert memory.remember(store, facts) == 3
    dump = json.dumps(store)
    for secret in ("priya.hr", "9876543210", "jobs.hr"):
        assert secret not in dump


def test_upi_and_short_links_are_identifiers():
    facts = extract_rules("Pay to hrdesk123@okaxis and register at https://bit.ly/Ab3dE")
    kinds = dict(memory.identifiers(facts))
    assert kinds["upi"] == "hrdesk123@okaxis"
    assert kinds["link"] == "bit.ly/Ab3dE"
