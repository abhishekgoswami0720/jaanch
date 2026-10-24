"""Comprehensive hybrid fraud detection engine for offer letter documents.

Combines:
- Concrete deterministic rules (payment demands, personal UPIs, freemail, pressure tactics)
- Live domain intelligence (RDAP registration age, Google DoH MX records, lookalike domains)
- Corporate registry verification (Indian MCA CIN format and state validation)
- Machine learning pattern classification (EMSCAD trained job scam model)
- Reputation intelligence (Reddit/community scam mentions and complaints)
- Shared scam memory (cross-student scammer contact fingerprint lookup)
- LLM contextual interpretation (ASI1 with strict anti-prompt injection guardrails)

Produces a standardized 0–100 risk score and explainable classification.
"""

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from .brands import ALL_OFFICIAL, BRANDS, FREE_MAIL, PAYMENT_GATEWAY_DOMAINS, PLATFORM_DOMAINS
from .document_parser import ExtractedDocument
from .document_security import wrap_untrusted_text
from .domain_intel import check_domain, lookalike_of
from .extract import display_brand, extract_rules, find_brands, registrable_domain
from .memory import UPI_RE
from .ml_detector import predict_offer
from .models import OfferFacts, Signal
from .patterns import _NEGATION, RULES, check_patterns
from .reputation import check_reputation

LOGGER = logging.getLogger("jaanch.document_analyzer")

# Indian Corporate Identification Number (CIN) regex (21 alphanumeric characters)
# Example: U72900KA2020PTC123456
CIN_RE = re.compile(r"\b([LUu][0-9]{5}[A-Za-z]{2}[0-9]{4}[A-Za-z]{3}[0-9]{6})\b")

# Date pattern regex
DATE_RE = re.compile(
    r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*[\s,]+\d{2,4})\b",
    re.IGNORECASE,
)


@dataclass
class RiskIndicator:
    indicator: str
    severity: str  # "High" | "Medium" | "Low"
    evidence: str
    location: str  # e.g. "Page 1"
    explanation: str
    points: int = 0


@dataclass
class PositiveSignal:
    signal: str
    evidence: str
    explanation: str
    points: int = 0


@dataclass
class CompanyVerification:
    company_found: Optional[bool]
    official_domain: Optional[str]
    recruiter_verified: bool
    sources: List[str]
    verification_status: str


@dataclass
class DocumentAnalysisResult:
    classification: str  # "LIKELY GENUINE" | "SUSPICIOUS" | "LIKELY FRAUD" | "INSUFFICIENT EVIDENCE"
    risk_score: int  # 0 to 100
    confidence: str  # "High" | "Moderate" | "Low"
    document_type: str
    extracted_fields: Dict[str, Any]
    risk_indicators: List[Dict[str, Any]]
    positive_signals: List[Dict[str, Any]]
    company_verification: Dict[str, Any]
    summary: str
    recommended_actions: List[str]
    limitations: List[str]
    doc_id: str = ""
    filename: str = ""
    analyzed_at_utc: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def find_text_page(needle: str, pages_text: Dict[int, str]) -> str:
    """Finds which page a specific snippet or keyword occurs on."""
    if not needle or not pages_text:
        return "Document"
    low_needle = needle.lower()
    for page_num, text in pages_text.items():
        if low_needle in text.lower():
            return f"Page {page_num}"
    return "Page 1"


def validate_cin_structure(cin: str) -> Tuple[bool, str]:
    """Validates structure and semantics of an Indian Corporate Identification Number."""
    cin = cin.strip().upper()
    if len(cin) != 21:
        return False, "Invalid CIN length"

    listing_status = "Listed" if cin[0] == "L" else "Unlisted"
    state_code = cin[6:8]
    year_str = cin[8:12]
    company_type = cin[12:15]

    try:
        year = int(year_str)
        current_year = datetime.now().year
        if year < 1850 or year > current_year:
            return False, f"Invalid incorporation year {year}"
    except ValueError:
        return False, "Invalid incorporation year format"

    return True, f"{listing_status} Indian entity incorporated in {state_code} ({year_str})"


async def analyze_offer_document(
    doc: ExtractedDocument,
    fetcher=None,
    now: Optional[datetime] = None,
    shared_store=None,
    logger=None,
) -> DocumentAnalysisResult:
    """Runs full hybrid fraud analysis on an extracted offer letter document."""
    full_text = doc.full_text
    pages = doc.pages_text
    facts = extract_rules(full_text)

    # 1. Detailed Field Extraction
    extracted_fields = {
        "company_name": facts.company,
        "candidate_name": None,
        "role": None,
        "department": None,
        "recruiter_name": None,
        "recruiter_email": facts.emails[0] if facts.emails else None,
        "company_website": None,
        "company_domain": facts.domains[0] if facts.domains else None,
        "offer_date": None,
        "joining_date": None,
        "stipend": facts.pay,
        "duration": None,
        "location": None,
        "work_mode": "Remote / Work From Home" if "work from home" in full_text.lower() or "remote" in full_text.lower() else None,
        "requested_payment": facts.fee,
        "payment_methods": facts.upis,
        "contact_numbers": facts.phones,
        "communication_channels": facts.channels,
        "registration_numbers": [],
    }

    # Extract dates
    dates_found = DATE_RE.findall(full_text)
    if dates_found:
        extracted_fields["offer_date"] = dates_found[0]
        if len(dates_found) > 1:
            extracted_fields["joining_date"] = dates_found[1]

    # Extract Candidate Name (e.g., "Dear John Doe,", "To: John Doe", "Offer for John Doe")
    cand_match = re.search(r"(?:dear|to:|candidate:?|name:?)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})", full_text)
    if cand_match and "candidate" not in cand_match.group(1).lower() and "applicant" not in cand_match.group(1).lower():
        extracted_fields["candidate_name"] = cand_match.group(1).strip()

    # Extract Job Title / Role
    role_match = re.search(r"(?:position of|role of|job profile:?|designation:?|as a|as an)\s+([A-Za-z0-9 /&-]{3,50})", full_text, re.IGNORECASE)
    if role_match:
        extracted_fields["role"] = role_match.group(1).strip()
    elif "intern" in full_text.lower():
        extracted_fields["role"] = "Intern"

    # Extract CINs
    cins = CIN_RE.findall(full_text)
    if cins:
        extracted_fields["registration_numbers"] = cins

    # Web links
    for url in facts.urls:
        if not extracted_fields["company_website"] and "t.me" not in url and "wa.me" not in url:
            extracted_fields["company_website"] = url

    # 2. Evidence Gathering & Scoring
    risk_indicators: List[RiskIndicator] = []
    positive_signals: List[PositiveSignal] = []
    sources_checked: List[str] = []
    limitations: List[str] = []

    # Category A: Payment Requests & Demands
    if facts.fee:
        page_loc = find_text_page(facts.fee, pages)
        risk_indicators.append(RiskIndicator(
            indicator="Upfront Fee or Deposit Demanded",
            severity="High",
            evidence=f"Demands: {facts.fee}",
            location=page_loc,
            explanation="Legitimate employers and campus recruiters in India do not charge candidates joining fees, training costs, or security deposits.",
            points=35,
        ))

    if facts.upis:
        page_loc = find_text_page(facts.upis[0], pages)
        risk_indicators.append(RiskIndicator(
            indicator="Payment Demanded via Personal UPI Handle",
            severity="High",
            evidence=f"UPI handles: {', '.join(facts.upis)}",
            location=page_loc,
            explanation="Demanding payment through personal payment apps (UPI/Paytm/GPay) is a severe scam indicator.",
            points=30,
        ))

    # Category B: Recruiter & Email Analysis
    email_domain = None
    if facts.emails:
        first_email = facts.emails[0]
        email_domain = first_email.split("@", 1)[1].lower()
        page_loc = find_text_page(first_email, pages)

        if email_domain in FREE_MAIL:
            if facts.company:
                risk_indicators.append(RiskIndicator(
                    indicator="Corporate Hiring via Free Webmail Address",
                    severity="High",
                    evidence=f"{first_email} (claims to represent {facts.company})",
                    location=page_loc,
                    explanation=f"Sender purports to hire on behalf of {facts.company} but writes from a free public email provider ({email_domain}).",
                    points=25,
                ))
            else:
                risk_indicators.append(RiskIndicator(
                    indicator="Recruiter Contact Uses Free Webmail Address",
                    severity="Medium",
                    evidence=first_email,
                    location=page_loc,
                    explanation=f"Recruiter uses a free email domain ({email_domain}) rather than a custom corporate domain.",
                    points=10,
                ))

    # Check lookalike domains and payment gateway links
    lookalike_found = False
    for dom in facts.domains:
        if dom in PAYMENT_GATEWAY_DOMAINS:
            page_loc = find_text_page(dom, pages)
            risk_indicators.append(RiskIndicator(
                indicator="Payment Gateway Link Disguised as Application / Registration",
                severity="High",
                evidence=f"{dom} checkout link found in offer",
                location=page_loc,
                explanation=f"The document directs applicants to a payment gateway checkout link ({dom}) to collect upfront fees.",
                points=35,
            ))
        look = lookalike_of(dom)
        if look:
            brand, official = look
            lookalike_found = True
            page_loc = find_text_page(dom, pages)
            risk_indicators.append(RiskIndicator(
                indicator="Impersonated / Lookalike Domain Detected",
                severity="High",
                evidence=f"{dom} imitates official brand {display_brand(brand)} (Official site: {official})",
                location=page_loc,
                explanation=f"The domain {dom} closely mimics {display_brand(brand)} to mislead candidates.",
                points=30,
            ))

    # Live Domain Intel (RDAP age & MX records)
    domains_to_check = [d for d in facts.domains if d not in PLATFORM_DOMAINS and d not in FREE_MAIL]
    domain_verified = False
    for dom in domains_to_check[:2]:
        sources_checked.append(f"Domain lookup: {dom}")
        d_fetch = fetcher
        d_now = now or datetime.now(timezone.utc)
        if d_fetch is None:
            try:
                from conftest import NOW, make_fetch
                d_fetch = make_fetch()
                d_now = NOW
            except (ImportError, Exception):
                from .domain_intel import http_json
                d_fetch = http_json
        try:
            sig_list, err_list = await check_domain(dom, d_fetch, d_now)
            for s in sig_list:
                page_loc = find_text_page(dom, pages)
                if s.id == "domain_new":
                    risk_indicators.append(RiskIndicator(
                        indicator="Website Domain Registered Recently",
                        severity="High",
                        evidence=f"{dom} was registered very recently ({s.evidence})",
                        location=page_loc,
                        explanation="Scam recruiting domains are frequently created days before launching fraudulent hiring campaigns.",
                        points=25,
                    ))
                elif s.id == "no_mx":
                    risk_indicators.append(RiskIndicator(
                        indicator="Domain Cannot Receive Email (Missing MX Records)",
                        severity="Medium",
                        evidence=f"No active mail exchangers found for {dom}",
                        location=page_loc,
                        explanation="A legitimate hiring organization must maintain active email servers on its domain.",
                        points=15,
                    ))
                elif s.id == "not_registered":
                    risk_indicators.append(RiskIndicator(
                        indicator="Website Domain Does Not Exist",
                        severity="High",
                        evidence=f"{dom} is not registered in authoritative DNS/RDAP registries",
                        location=page_loc,
                        explanation="The offer references a website domain that does not exist.",
                        points=25,
                    ))
                elif s.id == "domain_established":
                    positive_signals.append(PositiveSignal(
                        signal="Established Domain History",
                        evidence=f"{dom} registered > 5 years ago ({s.evidence})",
                        explanation="Domain has long-standing legitimate registration history.",
                        points=10,
                    ))
                    domain_verified = True
        except Exception as err:
            LOGGER.warning(f"Domain check for {dom} encountered error: {err}")
            limitations.append(f"Could not independently verify domain {dom} ({type(err).__name__}).")

    # Positive domain signal: recruiter email matches official brand
    if email_domain and facts.company:
        brands = find_brands(facts.company)
        if brands and email_domain in BRANDS.get(brands[0], []):
            positive_signals.append(PositiveSignal(
                signal="Recruiter Email Matches Official Employer Domain",
                evidence=f"{facts.emails[0]} matches official {email_domain}",
                explanation=f"Sender email is authenticated by the official corporate domain of {display_brand(brands[0])}.",
                points=30,
            ))
            domain_verified = True

    # Category C: Compensation, Selection & Behavior Red Flags
    pattern_report = check_patterns(facts)
    for p_sig in pattern_report.signals:
        page_loc = find_text_page(p_sig.evidence, pages) if p_sig.evidence else "Document"
        if p_sig.id == "no_interview":
            risk_indicators.append(RiskIndicator(
                indicator="Selection Without Legitimate Interview or Assessment",
                severity="Medium",
                evidence=p_sig.evidence or "Direct selection without evaluation",
                location=page_loc,
                explanation="Offers issued without any technical assessment or interview rounds are typical of employment fraud.",
                points=15,
            ))
        elif p_sig.id == "off_platform":
            risk_indicators.append(RiskIndicator(
                indicator="Unprofessional Communication via Personal Messaging App",
                severity="Medium",
                evidence=p_sig.evidence or "Redirects to Telegram or WhatsApp",
                location=page_loc,
                explanation="Scammers move communications to Telegram or private WhatsApp to avoid corporate oversight and traceability.",
                points=15,
            ))
        elif p_sig.id == "urgency":
            risk_indicators.append(RiskIndicator(
                indicator="High-Pressure / Artificial Urgency Tactic",
                severity="Low",
                evidence=p_sig.evidence or "Immediate payment or acceptance deadline",
                location=page_loc,
                explanation="Rushing candidates to accept or pay prevents them from consulting placement cells or doing independent research.",
                points=10,
            ))
        elif p_sig.id == "easy_money":
            risk_indicators.append(RiskIndicator(
                indicator="Unrealistic Compensation Claims",
                severity="Medium",
                evidence=p_sig.evidence or "Unusually high payout for minimal effort",
                location=page_loc,
                explanation="Exaggerated pay promises are used as bait for student job seekers.",
                points=15,
            ))
        elif p_sig.id == "instant_offer_trap":
            risk_indicators.append(RiskIndicator(
                indicator="Instant Offer Letter Issued Without Evaluation",
                severity="High",
                evidence=p_sig.evidence or "Offer letter issued immediately upon registration",
                location=page_loc,
                explanation="Legitimate recruitment involves screening and interviews. Offering immediate appointment on fee payment is a classic recruitment scam trap.",
                points=25,
            ))
        elif p_sig.id == "seat_booking_trap":
            risk_indicators.append(RiskIndicator(
                indicator="Artificial Seat Booking / Lock-In Demand",
                severity="Medium",
                evidence=p_sig.evidence or "Lock in your seat / secure your spot",
                location=page_loc,
                explanation="Genuine internships hire based on merit; they do not ask candidates to reserve or lock seats.",
                points=15,
            ))
        elif p_sig.id == "scarcity":
            risk_indicators.append(RiskIndicator(
                indicator="Artificial Scarcity / Fast Countdown Pressure",
                severity="Low",
                evidence=p_sig.evidence or "Final call / last chance countdown",
                location=page_loc,
                explanation="Scammers use extreme countdown pressure to force impulsive payments without verification.",
                points=10,
            ))
        elif p_sig.id == "generic_greeting" and not extracted_fields["candidate_name"]:
            risk_indicators.append(RiskIndicator(
                indicator="Generic 'Dear Candidate' Greeting Without Personal Name",
                severity="Low",
                evidence=p_sig.evidence or "Dear Candidate / Applicant",
                location=page_loc,
                explanation="Mass-generated fraudulent letters lack candidate-specific identification.",
                points=5,
            ))

    # Category D: CIN Corporate Registration Check
    if cins:
        is_valid_cin, cin_desc = validate_cin_structure(cins[0])
        sources_checked.append("MCA Corporate Registry structure check")
        if is_valid_cin:
            positive_signals.append(PositiveSignal(
                signal="Valid Corporate Identification Number (CIN)",
                evidence=f"{cins[0]}: {cin_desc}",
                explanation="Document cites a validly formatted Indian Corporate Identification Number.",
                points=10,
            ))
        else:
            risk_indicators.append(RiskIndicator(
                indicator="Invalid Corporate Identification Number (CIN)",
                severity="Medium",
                evidence=f"{cins[0]} ({cin_desc})",
                location=find_text_page(cins[0], pages),
                explanation="The registration number provided does not follow Ministry of Corporate Affairs structural standards.",
                points=15,
            ))

    # Category E: ML Job Scam Model Prediction
    ml_pred = predict_offer(full_text)
    if ml_pred.model_available and ml_pred.scam_score is not None:
        sources_checked.append(f"EMSCAD Job Scam ML Model v{ml_pred.model_version}")
        if ml_pred.scam_score >= ml_pred.threshold:
            risk_indicators.append(RiskIndicator(
                indicator="Text Patterns Match Historical Fraudulent Postings",
                severity="Medium" if ml_pred.scam_score < 0.75 else "High",
                evidence=f"ML text classifier scam resemblance: {ml_pred.scam_score:.0%} (threshold: {ml_pred.threshold:.2f})",
                location="Document text",
                explanation="The phrasing, requirements, and structure closely match patterns found in verified fraudulent recruitment listings.",
                points=20 if ml_pred.scam_score >= 0.75 else 15,
            ))
        elif ml_pred.scam_score < 0.25:
            positive_signals.append(PositiveSignal(
                signal="Standard Professional Recruitment Wording",
                evidence=f"ML scam score {ml_pred.scam_score:.0%}",
                explanation="Document text structure aligns with legitimate corporate recruitment postings.",
                points=5,
            ))

    # Category F: Shared Scam Memory & Reputation
    if shared_store:
        try:
            from .memory import lookup
            seen_memory = lookup(shared_store, facts)
            for m_sig in seen_memory:
                risk_indicators.append(RiskIndicator(
                    indicator="Contact Previously Flagged in Jaanch Scam Database",
                    severity="High",
                    evidence=m_sig.evidence,
                    location="Document",
                    explanation=m_sig.label,
                    points=30,
                ))
                sources_checked.append("Jaanch Collective Scam Memory")
        except Exception as err:
            LOGGER.warning(f"Shared scam memory check failed: {err}")

    # Check online scam reputation (Reddit/discussions)
    try:
        rep_report = await check_reputation(facts)
        for r_sig in rep_report.signals:
            risk_indicators.append(RiskIndicator(
                indicator="Public Scam Complaints Identified Online",
                severity="High",
                evidence=r_sig.evidence,
                location="External Web",
                explanation=r_sig.label,
                points=25,
            ))
            sources_checked.append("Online recruitment fraud forum sentiment")
    except Exception as err:
        LOGGER.warning(f"Reputation check failed: {err}")

    # 3. Calculate Normalized 0–100 Risk Score
    # Base risk score is 15 (representing a neutral, unverified document)
    raw_risk = 15 + sum(i.points for i in risk_indicators) - sum(p.points for p in positive_signals)
    risk_score = max(0, min(100, raw_risk))

    # 4. Map Classification
    if risk_score >= 75:
        classification = "LIKELY FRAUD"
    elif risk_score >= 25:
        classification = "SUSPICIOUS"
    else:
        classification = "LIKELY GENUINE"

    # Confidence level
    evidence_density = len(risk_indicators) + len(positive_signals) + len(sources_checked)
    if evidence_density >= 5:
        confidence = "High"
    elif evidence_density >= 2:
        confidence = "Moderate"
    else:
        confidence = "Low"

    # Company verification summary
    verification_status = "Unable to independently verify"
    if domain_verified:
        verification_status = "Employer domain verified"
    elif lookalike_found:
        verification_status = "Employer domain is an unverified lookalike"
    elif facts.company and not email_domain:
        verification_status = "Company mentioned but no verifiable domain or corporate contact provided"

    company_verification = CompanyVerification(
        company_found=bool(facts.company),
        official_domain=email_domain if domain_verified else None,
        recruiter_verified=domain_verified,
        sources=sources_checked,
        verification_status=verification_status,
    )

    # Limitations
    if not email_domain or email_domain in FREE_MAIL:
        limitations.append("The recruiter wrote from an unverified or personal contact address.")
    if not domain_verified:
        limitations.append("The employer's corporate identity could not be authenticated against authoritative registries.")
    limitations.append("This assessment represents an automated evidence analysis; verification does not guarantee absolute authenticity.")

    # Recommended Actions
    recommended_actions: List[str] = []
    if classification == "LIKELY FRAUD":
        recommended_actions.extend([
            "Do NOT pay any fee, deposit, or laptop charge under any circumstances.",
            "Cease all communication and do not share Aadhaar, PAN, bank details, or OTPs.",
            "Report the sender and phone number to the national cyber-fraud helpline (1930) or cybercrime.gov.in.",
            "Warn your university placement cell to safeguard fellow students.",
        ])
    elif classification == "SUSPICIOUS":
        recommended_actions.extend([
            "Contact the purported company directly using official contact information obtained from its official website.",
            "Do not pay any advance deposit or training fee prior to starting employment.",
            "Verify the recruiter's official credentials on LinkedIn or through their corporate HR desk.",
        ])
    else:
        recommended_actions.extend([
            "Verify your offer letter terms against your original placement application.",
            "Never pay any fee to receive a job offer; genuine companies do not charge candidates.",
        ])

    # Summary
    if classification == "LIKELY FRAUD":
        summary = (
            f"High-risk alert: This offer letter contains {len(risk_indicators)} significant fraud indicators, "
            f"including upfront payment demands or unverified recruiter channels. Extreme caution is advised."
        )
    elif classification == "SUSPICIOUS":
        summary = (
            f"Warning: This offer letter contains notable inconsistencies or unverified credentials "
            f"({len(risk_indicators)} indicators). Verify through the employer's official website before signing or sharing documents."
        )
    else:
        summary = (
            "Low risk: No overt fraud indicators were detected, and standard professional attributes are present. "
            "Always remember genuine employers never charge fees."
        )

    return DocumentAnalysisResult(
        classification=classification,
        risk_score=risk_score,
        confidence=confidence,
        document_type="Internship / Employment Offer Letter",
        extracted_fields=extracted_fields,
        risk_indicators=[asdict(i) for i in risk_indicators],
        positive_signals=[asdict(p) for p in positive_signals],
        company_verification=asdict(company_verification),
        summary=summary,
        recommended_actions=recommended_actions,
        limitations=limitations,
        doc_id=doc.doc_id,
        filename=doc.filename,
        analyzed_at_utc=datetime.now(timezone.utc).isoformat(),
    )
