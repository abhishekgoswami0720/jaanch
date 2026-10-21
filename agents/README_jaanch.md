# Jaanch: job and internship scam checker

![tag:innovationlab](https://img.shields.io/badge/innovationlab-3D8BD3)
![tag:hackathon](https://img.shields.io/badge/hackathon-5F43F1)
![domain:career-safety](https://img.shields.io/badge/career--safety-E5484D)

Paste a job or internship offer (a WhatsApp or Telegram message, an email, or offer-letter text). Jaanch checks it with live evidence and replies with a **1–10 risk score**, the reasons behind it, and what to do next.

## What it checks
- **The message**: fee or deposit demands, OTP / UPI PIN / card requests, "like videos and earn" task scams, Telegram-only contact, unrealistic daily pay, no interview, pressure to act fast. English and Hinglish.
- **The sender** (via the `jaanch-domain-intel` agent): how old the recruiter's website is (RDAP), whether its email domain can receive mail (MX), and whether it imitates a big employer such as Infosys, TCS or Amazon.
- **The claim**: a recruiter using Gmail while claiming to hire for a big company.

The score is a fixed formula over this evidence, not an LLM opinion, so the same message always gets the same score. ASI1 extracts facts from messy text and explains the result in plain words.

## Example
Input: *"TCS work from home internship… pay the refundable registration fee of ₹1,499 within 24 hours… tcs.hr.recruit2026@gmail.com… t.me/tcs_wfh_jobs"*

Output: **High risk: this looks like a scam (10/10)**: asks for a fee, claims to be TCS but uses Gmail, moves you to Telegram, no interview. Next step: don't pay; report at cybercrime.gov.in or call 1930.

## For other agents
Job-search and career agents can call Jaanch before recommending a listing, using the `JaanchOfferVerification` protocol:
- Request `VerifyOfferRequest { offer_text: str, source_url: str | null }`
- Response `VerifyOfferResponse { risk_score: int, verdict: "low_risk" | "suspicious" | "high_risk", reasons: [str], checked_domains: [str] }`

Built by Team Chiranjivi for Fetch-A-Thon 3.0.
