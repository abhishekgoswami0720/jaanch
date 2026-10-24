import asyncio

import pytest
from conftest import NOW, make_fetch, sample

from jaanch.domain_intel import check_domains, lookalike_of
from jaanch.extract import extract_rules, registrable_domain
from jaanch.models import Signal
from jaanch.patterns import check_patterns
from jaanch.pipeline import run_local
from jaanch.scoring import score


def run(text, fetch=None):
    return asyncio.run(run_local(text, fetch=fetch or make_fetch(), now=NOW))


# ---- end to end on the samples ------------------------------------------------

@pytest.mark.parametrize("name", ["scam_fee_whatsapp.txt", "scam_task_hinglish.txt", "scam_lookalike_email.txt"])
def test_scams_are_high_risk(name):
    r = run(sample(name))
    assert r.verdict == "high_risk", (r.risk, [s.id for s in r.signals])


def test_middle_of_the_scale():
    r = run(sample("suspicious_new_startup.txt"))
    assert r.verdict == "suspicious", (r.risk, [(s.id, s.weight) for s in r.signals])


@pytest.mark.parametrize("name", ["genuine_internshala.txt", "genuine_campus_offer.txt"])
def test_genuine_offers_are_low_risk(name):
    r = run(sample(name))
    assert r.verdict == "low_risk", (r.risk, [(s.id, s.weight) for s in r.signals])


def test_lookalike_email_evidence():
    r = run(sample("scam_lookalike_email.txt"))
    ids = {s.id for s in r.signals}
    assert {"lookalike", "domain_new", "no_mx", "fee_demand", "short_link", "id_documents"} <= ids
    assert "infosys-careers.in" in r.checked


def test_freemail_brand_and_telegram():
    r = run(sample("scam_fee_whatsapp.txt"))
    ids = {s.id for s in r.signals}
    assert {"freemail_brand", "off_platform", "fee_demand", "no_interview", "urgency"} <= ids
    assert "t.me" not in r.checked  # messaging links are not domain-checked


def test_hinglish_task_scam():
    ids = {s.id for s in run(sample("scam_task_hinglish.txt")).signals}
    assert {"task_scam", "easy_money", "off_platform", "no_interview"} <= ids


def test_whatsapp_induction_bait_scam():
    text = (
        "Your profile has been selected for the Internship Program at Unified Mentor Pvt. Ltd.\n"
        "Induction: Today ⏰ Time: 05:00 PM\n"
        "Internship Highlights: Stipend UP TO 7500 RS\n"
        "Join WhatsApp Group: https://chat.whatsapp.com/BaEnmYMEkhq45novAx73l4\n"
        "Please join the WhatsApp group and attend the induction session on time."
    )
    r = run(text)
    ids = {s.id for s in r.signals}
    assert {"off_platform", "no_interview", "urgency", "bait_stipend"} <= ids
    assert r.risk >= 6


def test_course_upsell_and_cheque_blackmail():
    text = (
        "Selected candidates must pay mentorship fee of Rs 2,500 and submit a cancelled cheque "
        "along with original certificates for the 3-month internship program."
    )
    r = run(text)
    ids = {s.id for s in r.signals}
    assert {"course_upsell_bait", "dangerous_documents"} <= ids
    assert r.verdict == "high_risk"


def test_enterprise_ats_and_structured_interview_green_flags():
    text = (
        "Thank you for interviewing with us. Please track your application for Backend Engineer on Lever: "
        "https://jobs.lever.co/techcorp/12345. Next is a technical round and hiring manager round."
    )
    r = run(text)
    ids = {s.id for s in r.signals}
    assert {"ats_portal", "structured_interview"} <= ids
    assert r.verdict == "low_risk"


def test_scarcity_mca_claims_and_phone_only():
    text = (
        "Only 3 slots left! Batch filling fast. We are a Govt approved company with CIN registered. "
        "Contact HR directly at +91 9876543210 for immediate joining."
    )
    r = run(text)
    ids = {s.id for s in r.signals}
    assert {"scarcity", "mca_claims", "phone_only_contact"} <= ids


def test_academic_institution_bonus():
    text = "Campus placements coordinator. Check details on https://placement.gla.ac.in/jobs"
    r = run(text)
    ids = {s.id for s in r.signals}
    assert "academic_institution" in ids


# ---- resilience ----------------------------------------------------------------

def test_network_down_still_answers():
    r = asyncio.run(run_local(sample("scam_lookalike_email.txt"), fetch=make_fetch(fail=True), now=NOW))
    assert r.verdict == "high_risk"  # text + lookalike evidence alone are enough
    assert r.errors


def test_rdap_missing_is_not_treated_as_fake():
    """Registries without RDAP must not make a real domain look fake."""
    world = {"swiggy.in": (None, True, True)}

    async def fetch(url):
        if "/domain/" in url:
            return 404, None
        return await make_fetch(world)(url)

    facts = extract_rules("Apply at https://careers.swiggy.in")
    report = asyncio.run(check_domains(facts, fetch=fetch, now=NOW))
    assert not any(s.id == "not_registered" for s in report.signals)


def test_nonexistent_domain():
    facts = extract_rules("Contact hr@ghost-company-hiring.com")
    report = asyncio.run(check_domains(facts, fetch=make_fetch(), now=NOW))
    assert any(s.id == "not_registered" for s in report.signals)


# ---- units ---------------------------------------------------------------------

@pytest.mark.parametrize("domain,brand", [
    ("infosys-careers.in", "infosys"), ("tcshiring.com", "tcs"), ("wipr0.com", "wipro"),
    ("amazom.in", "amazon"), ("infosys.co", "infosys"), ("flipkart-jobs.online", "flipkart"),
])
def test_lookalikes(domain, brand):
    assert lookalike_of(domain)[0] == brand


@pytest.mark.parametrize("domain", [
    "infosys.com", "tcsion.com", "zoho.com", "internshala.com", "gla.ac.in", "electronicshub.org",
    "april-events.com", "metallica.com",
])
def test_not_lookalikes(domain):
    assert lookalike_of(domain) is None


def test_official_email_lowers_risk():
    facts = extract_rules("Infosys offer: please accept on the portal. Contact recruitment@infosys.com")
    report = asyncio.run(check_domains(facts, fetch=make_fetch(), now=NOW))
    assert any(s.id == "official_email" and s.weight < 0 for s in report.signals)


def test_registrable_domain():
    assert registrable_domain("careers.infosys.com") == "infosys.com"
    assert registrable_domain("mail.gla.ac.in") == "gla.ac.in"
    assert registrable_domain("www.tcs.com") == "tcs.com"


def test_extract_contacts():
    f = extract_rules("Mail hr.team@gmail.com or visit https://bit.ly/abc, call +91 98765 43210. Fee ₹999 payable.")
    assert f.emails == ["hr.team@gmail.com"]
    assert "bit.ly" in f.domains and "gmail.com" not in f.domains
    assert f.phones == ["+919876543210"]
    assert f.fee


def test_genuine_stipend_is_not_easy_money():
    f = extract_rules("Stipend ₹15,000 per month for 6 months. Interview on Friday.")
    assert not any(s.id == "easy_money" for s in check_patterns(f).signals)


def test_score_is_deterministic_and_bounded():
    sigs = [Signal(id=f"s{i}", label="x", weight=3.0) for i in range(10)]
    assert score(sigs) == 10
    assert score([Signal(id="a", label="x", weight=-5)]) == 1
    assert score([]) == 2
    # The same kind of signal is counted once
    assert score([Signal(id="a", label="x", weight=2)] * 3) == 4


@pytest.mark.parametrize("text", [
    "There is no registration fee at any stage.",
    "We never ask for your OTP or bank details.",
    "Selection is not without interview: two rounds on Friday.",
])
def test_negated_phrases_are_not_red_flags(text):
    ids = {s.id for s in check_patterns(extract_rules(text)).signals}
    assert not ids & {"fee_demand", "secret_data", "id_documents"}, ids


def test_negation_does_not_leak_across_sentences():
    ids = {s.id for s in check_patterns(extract_rules("No interview needed! Pay registration fee ₹999 now")).signals}
    assert {"fee_demand", "no_interview"} <= ids


def test_email_local_part_is_not_a_domain():
    f = extract_rules("Send screenshot to tcs.hr.recruit2026@gmail.com and hr.team@gmail.com")
    assert f.domains == [] and f.urls == []


def test_brand_display_names():
    sigs = check_patterns(extract_rules("TCS hiring! mail tcs.jobs@gmail.com")).signals
    assert any("TCS" in s.label for s in sigs)


def test_rdap_goes_to_the_registry_first():
    """rdap.org can refuse scripts (HTTP 403), so ask the registry IANA lists for the ending."""
    import jaanch.domain_intel as di
    di._rdap_servers.clear()
    asked = []
    base = make_fetch()

    async def fetch(url):
        asked.append(url)
        return await base(url)

    report = asyncio.run(check_domains(extract_rules("Apply at https://careers.zoho.com"), fetch=fetch, now=NOW))
    assert "https://rdap.registry.test/com/v1/domain/zoho.com" in asked
    assert not any("rdap.org" in u for u in asked)
    assert any(s.id == "domain_old" for s in report.signals)


def test_rdap_falls_back_to_rdap_org_when_registry_refuses():
    import jaanch.domain_intel as di
    di._rdap_servers.clear()
    base = make_fetch()

    async def fetch(url):
        if "rdap.registry.test" in url:
            return 403, None
        return await base(url)

    report = asyncio.run(check_domains(extract_rules("Apply at https://careers.zoho.com"), fetch=fetch, now=NOW))
    assert any(s.id == "domain_old" for s in report.signals)


# ---- paid "training + internship" forwards (real WhatsApp messages, redacted) ----

@pytest.mark.parametrize("name", [
    "real/01_brand_names_training.txt", "real/02_iit_collaboration_training.txt",
    "real/04_wipro_tcs_mentor_fees.txt",
])
def test_paid_training_internships_are_high_risk(name):
    r = run(sample(name))
    assert r.verdict == "high_risk", (r.risk, [(s.id, s.weight) for s in r.signals])


def test_paid_qualifier_is_at_least_suspicious():
    r = run(sample("real/05_iit_certification_qualifier.txt"))
    assert r.verdict in {"suspicious", "high_risk"}, (r.risk, [(s.id, s.weight) for s in r.signals])


def test_affiliation_backed_by_official_domain_is_not_flagged():
    text = "Summer research internship in collaboration with IIT Delhi. Apply at https://www.iitd.ac.in/internships"
    ids = {s.id for s in check_patterns(extract_rules(text)).signals}
    assert "fake_affiliation" not in ids


def test_one_fee_is_not_counted_twice():
    ids = [s.id for s in run(sample("scam_fee_whatsapp.txt")).signals]
    assert "fee_demand" in ids and "course_upsell_bait" not in ids


def test_part_time_earn_daily_whatsapp():
    r = run("Part time job! Earn ₹2000-5000 daily from home, just need a phone. Contact HR on WhatsApp 98XXXXXXXX")
    ids = {s.id for s in r.signals}
    assert {"easy_money", "off_platform"} <= ids and r.verdict != "low_risk"
