"""Employers that scammers commonly impersonate, with their official domains.

Used to catch lookalike domains (infosys-careers.in) and free-mail recruiters
claiming to hire for a big brand. Extend this list on the day; it is plain data.
"""

BRANDS: dict[str, list[str]] = {
    "tcs": ["tcs.com"],
    "tata consultancy": ["tcs.com"],
    "infosys": ["infosys.com"],
    "wipro": ["wipro.com"],
    "hcl": ["hcltech.com", "hcl.com"],
    "tech mahindra": ["techmahindra.com"],
    "cognizant": ["cognizant.com"],
    "accenture": ["accenture.com"],
    "capgemini": ["capgemini.com"],
    "ltimindtree": ["ltimindtree.com"],
    "deloitte": ["deloitte.com"],
    "kpmg": ["kpmg.com"],
    "pwc": ["pwc.com", "pwc.in"],
    "ernst & young": ["ey.com"],
    "ey": ["ey.com"],
    "ibm": ["ibm.com"],
    "oracle": ["oracle.com"],
    "amazon": ["amazon.com", "amazon.in", "amazon.jobs"],
    "flipkart": ["flipkart.com"],
    "google": ["google.com"],
    "microsoft": ["microsoft.com"],
    "meta": ["meta.com", "fb.com"],
    "apple": ["apple.com"],
    "adobe": ["adobe.com"],
    "samsung": ["samsung.com"],
    "zoho": ["zoho.com"],
    "freshworks": ["freshworks.com"],
    "reliance": ["ril.com", "jio.com", "relianceretail.com"],
    "jio": ["jio.com"],
    "airtel": ["airtel.in", "airtel.com"],
    "paytm": ["paytm.com"],
    "zomato": ["zomato.com"],
    "swiggy": ["swiggy.in", "swiggy.com"],
    "hdfc": ["hdfcbank.com", "hdfc.com"],
    "icici": ["icicibank.com"],
    "sbi": ["sbi.co.in"],
    "byju": ["byjus.com"],
    "internshala": ["internshala.com"],
    "naukri": ["naukri.com"],
    "linkedin": ["linkedin.com"],
    "isro": ["isro.gov.in"],
    "drdo": ["drdo.gov.in"],
}

# Short brand names only count as a mention when they appear as a whole word.
SHORT_BRANDS = {"tcs", "hcl", "ibm", "sbi", "pwc", "jio", "meta", "ey"}

FREE_MAIL = {
    "gmail.com", "googlemail.com", "yahoo.com", "yahoo.in", "yahoo.co.in",
    "outlook.com", "hotmail.com", "live.com", "rediffmail.com", "proton.me",
    "protonmail.com", "icloud.com", "aol.com", "zohomail.in", "gmx.com",
    "yandex.com", "mail.com",
}

URL_SHORTENERS = {
    "bit.ly", "tinyurl.com", "cutt.ly", "rb.gy", "t.ly", "is.gd", "goo.gl",
    "shorturl.at", "rebrand.ly", "tiny.cc", "ow.ly", "s.id",
}

# Messaging platforms, not company websites: never run domain-age checks on them.
PLATFORM_DOMAINS = {
    "t.me", "telegram.me", "wa.me", "whatsapp.com", "chat.whatsapp.com",
    "forms.gle", "docs.google.com", "drive.google.com", "linktr.ee",
}

# Recognized Applicant Tracking Systems (ATS) used by legitimate employers
ATS_DOMAINS = {
    "greenhouse.io", "lever.co", "workday.com", "myworkdayjobs.com",
    "smartrecruiters.com", "ashbyhq.com", "recruitee.com", "bamboohr.com",
    "jobvite.com", "icims.com", "rippling.com", "darwinbox.com",
}

# Free forms or link-in-bio portals that big companies never use for official hiring
PUBLIC_FORM_DOMAINS = {
    "forms.gle", "docs.google.com", "linktr.ee", "notion.site", "typeform.com",
}

ALL_OFFICIAL = {d for domains in BRANDS.values() for d in domains}

# Genuine domains that contain a brand name but are not the main site.
# Without this list they would be flagged as lookalikes.
RELATED_OFFICIAL = {
    "tcsion.com", "infosysbpm.com", "infosysapps.com", "wiprodigital.com",
    "amazonaws.com", "googleapis.com", "googleusercontent.com", "withgoogle.com",
    "microsoftonline.com", "office.com", "sharepoint.com", "linkedin.cn",
    "hdfclife.com", "hdfcergo.com", "icicidirect.com", "icicilombard.com",
    "sbicard.com", "sbilife.co.in", "jiomart.com", "zohocorp.com",
    "deloitte.co.in", "kpmg.co.in", "accenture.in", "ibm.net", "google.co.in",
}
