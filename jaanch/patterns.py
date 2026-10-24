"""Language and behaviour red flags in the offer text itself.

Each rule is (id, label, weight, regex). Weights are risk points; the scorer
adds them up. Keywords include common Hinglish phrasing used in WhatsApp scams.
"""

import re

from .brands import ALL_OFFICIAL, ATS_DOMAINS, PUBLIC_FORM_DOMAINS, URL_SHORTENERS
from .extract import display_brand, find_brands, free_mail_used
from .models import OfferFacts, PatternReport, Signal

SOURCE = "pattern-agent"

RULES: list[tuple[str, str, float, str]] = [
    (
        "fee_demand",
        "Asks you to pay a fee or deposit to get the job",
        4.0,
        r"(registration|security|training|joining|processing|kit|onboarding|verification|"
        r"refundable|application|certificate|id card|laptop)\s*(fee|fees|charge|charges|deposit|amount)"
        r"|pay\s+(rs\.?|inr|₹)\s?\d|(fees?|payment)\s+(jama|bhejo|karna|karni|kare)"
        r"|refundable\s+(amount|deposit)",
    ),
    (
        "course_upsell_bait",
        "Presents internship but requires completing paid training/mentorship first",
        3.0,
        r"(course|training|mentorship|certification)\s+(fee|charges?|price|cost|pack)"
        r"|(internship|program)\s+cum\s+training|training\s+plus\s+internship"
        r"|must\s+complete\s+(the\s+)?(training|course|module)\s+(before|to\s+get|for)\s+(internship|stipend)"
        r"|mentor(?:ship)?\s+(fee|charges|deposit)"
        r"|fees?\s+structure|(small|nominal|minimal|one[\s-]time|token)\s+(fees?|charges?|amount|registration)"
        r"|(qualifier|entrance\s+test|course|certification)[^.\n]{0,25}(rs\.?|inr|₹)\s?\d",
    ),
    (
        "training_bundle",
        "Sells a 'training + internship' program: usually a paid course dressed up as an internship",
        1.0,
        r"training\s*(\+|and|&|cum|plus|with)\s*internships?|internships?\s*(\+|and|&|cum|plus|with)\s*training"
        r"|(education|career|admission)\s+counsel+or",
    ),
    (
        "placement_guarantee",
        "Promises 100% or guaranteed placement",
        1.5,
        r"100\s*%\s*(placement|job)|guaranteed\s+(placement|job|internship)|(placement|job)\s+guarantee",
    ),
    (
        "secret_data",
        "Asks for an OTP, UPI PIN, card details or remote access to your phone",
        3.0,
        r"\botp\b|upi\s*pin|\bcvv\b|debit\s*card|credit\s*card|anydesk|teamviewer|screen\s*share",
    ),
    (
        "dangerous_documents",
        "Asks for blank/cancelled cheque, original certificates, or bond",
        2.5,
        r"(blank|cancelled|canceled)\s+cheque|original\s+(certificate|marksheet|documents)"
        r"|service\s+agreement\s+bond|security\s+cheque|surrender\s+(original|documents)",
    ),
    (
        "id_documents",
        "Asks for Aadhaar, PAN or bank details before any interview",
        1.0,
        r"aadhaar|aadhar|pan\s*card|bank\s*(account|details|statement)",
    ),
    (
        "task_scam",
        "Pays you for online 'tasks' like likes, reviews or ratings",
        3.0,
        r"(like|subscribe)\s+(youtube|videos?|channels?)|google\s+(map\s+)?reviews?|rate\s+(hotels?|products?)"
        r"|prepaid\s+tasks?|merchant\s+tasks?|recharge\s+tasks?|daily\s+tasks?|simple\s+tasks?",
    ),
    (
        "off_platform",
        "Moves the conversation to Telegram or a WhatsApp group/chat",
        2.0,
        r"t\.me/|telegram|wa\.me/|chat\.whatsapp\.com/|whatsapp\s+(group|only|me|karo|kare)|(contact|message|text|ping|dm)\s+(hr\s+|us\s+|me\s+)?(on|via)\s+whatsapp|whatsapp\s*(:|-|no\.?|number|on)\s*\+?\d|dm\s+on\s+telegram",
    ),
    (
        "easy_money",
        "Promises unusually high pay for little work",
        2.0,
        r"(earn|kamao|income|salary|payout)[^.\n]{0,30}(rs\.?|inr|₹)\s?\d[\d,]*\s*(/|per|a|daily|every)\s*(day|hour|hr|task)"
        r"|(rs\.?|inr|₹)\s?\d[\d,]*\s*(/|per|a)\s*(day|hour|hr|task)"
        r"|daily\s+(payout|payment|income)|ghar\s+baithe|work\s+from\s+home[^.\n]{0,40}(earn|daily)"
        r"|(rs\.?|inr|₹)\s?\d[\d,]*\s*(-|to)\s*(rs\.?|inr|₹)?\s?\d[\d,]*\s*(/|per|a|every)?\s*(day|daily|hour|hr|task)"
        r"|(earn|kamao|income|earning)[^.\n]{0,40}\b(daily|per\s+day|a\s+day|roz)\b"
        r"|just\s+need\s+(a\s+)?(phone|mobile|smartphone)|no\s+experience\s+(needed|required)[^.\n]{0,40}(earn|₹|rs)",
    ),
    (
        "bait_stipend",
        "Vague or performance-conditional stipend claim ('Up To ₹...')",
        1.0,
        r"stipend\s*:?\s*up\s*to\s*(?:rs\.?|inr|₹)?\s?\d|up\s*to\s*(?:rs\.?|inr|₹)\s?\d[\d,]*\s*(?:stipend|per\s*month|pm)?"
        r"|performance[\s-]based\s+stipend|stipend[^.\n]{0,25}based\s+on\s+performance",
    ),
    (
        "no_interview",
        "Direct selection or induction without interview/application",
        1.5,
        r"no\s+interview|without\s+(any\s+)?interview|direct\s+(selection|joining)|interview\s+nahi"
        r"|profile\s+has\s+been\s+selected|selection\s+.*(?:confirmed|approved)"
        r"|you\s+(are|have\s+been)\s+(shortlisted|selected)\s+(directly|for\s+direct|for\s+the\s+internship)",
    ),
    (
        "urgency",
        "Pressures you to act fast or attend same-day induction",
        1.0,
        r"within\s+\d+\s*(hours?|hrs?|minutes?)|limited\s+(seats|slots|vacanc)|last\s+date\s+(is\s+)?today"
        r"|immediate(ly)?\s+(joining|payment|response)|only\s+(few|\d+)\s+(seats|slots)|jaldi|abhi\s+pay"
        r"|induction\s*:\s*today|induction\s+session\s+today|today\s+at\s+\d{1,2}:\d{2}"
        r"|last\s+chance|final\s+chance|hurry\s+up|no\s+extensions?|first\s+come,?\s+first\s+serve"
        r"|(seats?|slots?|registrations?)\s+(are\s+)?(closing|filling)|only\s+\d+\s+\w+\s+(seats|slots)\s+left",
    ),
    (
        "generic_greeting",
        "Generic 'Dear candidate' greeting instead of your name",
        0.5,
        r"dear\s+(candidate|applicant|student|user|sir/madam)",
    ),
    (
        "scarcity",
        "Artificial scarcity or fast countdown pressure ('Only X slots left')",
        1.0,
        r"only\s+\d+\s*(slots?|seats?|vacanc\w*)\s*(left|remaining)|limited\s+(slots?|seats?)"
        r"|offer\s+expires\s+in\s+\d+\s*(hours?|hrs?|minutes?|days?)|batch\s+filling\s+fast",
    ),
    (
        "mca_claims",
        "Touts MCA / CIN or Govt registration to artificially manufacture trust",
        1.0,
        r"(mca|cin|msme)\s*(registered|approved|certified|no\.?|number|govt|gov)"
        r"|govt\s+approved\s+company|government\s+of\s+india\s+certified",
    ),
    (
        "structured_interview",
        "Structured multi-round interview process mentioned",
        -1.0,
        r"(technical\s+round|coding\s+round|panel\s+interview|take-home\s+assignment|hiring\s+manager\s+round|behavioral\s+round)",
    ),
]

_COMPILED = [(i, l, w, re.compile(p, re.IGNORECASE)) for i, l, w, p in RULES]

_BIG_NAMES = (r"iit|iim|nit|iisc|aiims|indian\s+institute|microsoft|google|ibm|meta|amazon|wipro|tcs|infosys"
              r"|accenture|cisco|apple|oracle|deloitte|isro|drdo|nasscom|aicte")
_AFFILIATION = re.compile(
    r"(collaboration|collab|association|partnership|tie[\s-]?up|partnered)\s+with\s+[^.\n]{0,60}?\b(" + _BIG_NAMES + r")\b"
    r"|powered\s*(by)?\s+(ibm|microsoft|meta|google|amazon)|certified\s+by\s+(" + _BIG_NAMES + r")\b",
    re.IGNORECASE,
)


def _snippet(text: str, m: re.Match, pad: int = 30) -> str:
    s, e = max(0, m.start() - pad), min(len(text), m.end() + pad)
    return ("…" if s else "") + text[s:e].replace("\n", " ").strip() + ("…" if e < len(text) else "")


_NEGATION = re.compile(r"\b(no|zero|not|never|without|don'?t|do not|nahi|mat)\b[^.!?,;\n]{0,32}$", re.IGNORECASE)


def _first_unnegated(rx: re.Pattern, text: str):
    """First match that isn't negated, so "no registration fee" doesn't count as a fee demand."""
    for m in rx.finditer(text):
        if not _NEGATION.search(text[max(0, m.start() - 40):m.start()]):
            return m
    return None


def check_patterns(facts: OfferFacts) -> PatternReport:
    text = facts.text
    signals: list[Signal] = []

    for rule_id, label, weight, rx in _COMPILED:
        m = _first_unnegated(rx, text)
        if m:
            signals.append(Signal(id=rule_id, label=label, weight=weight, evidence=_snippet(text, m), source=SOURCE))

    # A fee the extractor found but the keyword rule missed (e.g. "send ₹1,999 to confirm").
    if facts.fee and not any(s.id == "fee_demand" for s in signals):
        signals.append(
            Signal(id="fee_demand", label="Asks you to pay a fee or deposit to get the job",
                   weight=4.0, evidence=facts.fee, source=SOURCE)
        )

    shorteners = sorted(set(facts.domains) & URL_SHORTENERS)
    if shorteners:
        signals.append(Signal(id="short_link", label="Hides the real website behind a short link",
                              weight=1.0, evidence=", ".join(shorteners), source=SOURCE))

    free = free_mail_used(facts)
    brands = find_brands(text)
    if free and brands:
        signals.append(
            Signal(
                id="freemail_brand",
                label=f"Claims to hire for {display_brand(brands[0])} but uses a free email address",
                weight=2.5,
                evidence=", ".join(free),
                source=SOURCE,
            )
        )
    elif free:
        signals.append(Signal(id="freemail", label="Recruiter writes from a free email address",
                              weight=1.0, evidence=", ".join(free), source=SOURCE))

    # "In collaboration with IIT / Microsoft" with no link to that institution or company
    claim = _first_unnegated(_AFFILIATION, text)
    own_domains = set(facts.domains) | {e.split("@", 1)[1] for e in facts.emails}
    official = any(d in ALL_OFFICIAL or d.endswith((".ac.in", ".edu", ".edu.in", ".gov.in", ".nic.in"))
                   for d in own_domains)
    if claim and not official:
        signals.append(Signal(id="fake_affiliation",
                              label="Claims a tie-up with an IIT or a big company, but gives no official link to prove it",
                              weight=2.0, evidence=_snippet(text, claim), source=SOURCE))

    # Public forms (Google Forms, linktree) used for big company recruitment
    public_forms = sorted(set(facts.domains) & PUBLIC_FORM_DOMAINS)
    if public_forms and not brands and re.search(r"regist|enrol|apply|internship", text, re.I):
        signals.append(Signal(id="public_form_recruitment",
                              label="Collects registrations on a Google Form instead of a company website",
                              weight=1.0, evidence=", ".join(public_forms), source=SOURCE))
    if public_forms and brands:
        signals.append(
            Signal(
                id="public_form_recruitment",
                label=f"Claims to hire for {display_brand(brands[0])} using a public form/link",
                weight=1.5,
                evidence=", ".join(public_forms),
                source=SOURCE,
            )
        )

    # Standard corporate Applicant Tracking System (ATS) used -> high confidence legitimate
    ats_used = sorted(set(facts.domains) & ATS_DOMAINS)
    if ats_used:
        signals.append(
            Signal(
                id="ats_portal",
                label="Uses verified enterprise Applicant Tracking System (ATS)",
                weight=-2.0,
                evidence=", ".join(ats_used),
                source=SOURCE,
            )
        )

    # Official College / University Placement domain (.edu, .ac.in)
    academic_domains = [d for d in facts.domains if d.endswith(".edu") or d.endswith(".ac.in")]
    if academic_domains:
        signals.append(
            Signal(
                id="academic_institution",
                label="Verified educational or campus placement domain (.ac.in / .edu)",
                weight=-2.0,
                evidence=", ".join(academic_domains),
                source=SOURCE,
            )
        )

    # Recruiter only uses personal mobile numbers with no official email or domain
    if facts.phones and not facts.emails and not facts.domains:
        signals.append(
            Signal(
                id="phone_only_contact",
                label="Only personal mobile number provided with no official company email",
                weight=1.5,
                evidence=", ".join(facts.phones[:3]),
                source=SOURCE,
            )
        )

    # Personal UPI ID provided for payment / fees
    if facts.upis:
        signals.append(
            Signal(
                id="personal_upi_demand",
                label="Directs payment to a personal UPI VPA handle instead of an official merchant gateway",
                weight=3.0,
                evidence=", ".join(facts.upis[:2]),
                source=SOURCE,
            )
        )

    # CIN / MCA corporate claims verification
    if facts.cins:
        # Check CIN structure: L/U (listed/unlisted), 5 digits, 2 state letters, 4 year digits, 3 ownership letters, 6 digits
        for cin in facts.cins:
            year = int(cin[8:12]) if cin[8:12].isdigit() else 0
            if year > 2026 or year < 1900:
                signals.append(
                    Signal(
                        id="fake_cin_number",
                        label="Fabricated Ministry of Corporate Affairs CIN registration number",
                        weight=3.0,
                        evidence=cin,
                        source=SOURCE,
                    )
                )

    return PatternReport(signals=signals)
