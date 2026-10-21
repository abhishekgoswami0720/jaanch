# Jaanch: check a job offer before it checks your wallet

![tag:innovationlab](https://img.shields.io/badge/innovationlab-3D8BD3)
![tag:hackathon](https://img.shields.io/badge/hackathon-5F43F1)

**Jaanch** (Hindi for *check*) is a set of three AI agents on Fetch.ai's Agentverse. A student pastes a suspicious job or internship message into **ASI:One**. Jaanch's agents check the message and the sender against live evidence and return a **1–10 risk score** with the reasons behind it and what to do next. Other agents, such as job-search or career agents, can call the same check before they recommend a listing.

Built for **Fetch-A-Thon 3.0** (Masters' Union, 24 Oct 2026) by Team Chiranjivi.

## The problem
- **93%** of Indian employees and job seekers say they have encountered suspicious or fraudulent job opportunities, and **51%** are not confident they can tell a genuine recruiter from a scammer ([Indeed survey via Business Today, Jul 2026](https://www.businesstoday.in/jobs/story/more-than-9-in-10-job-seekers-encounter-fake-job-offers-542006-2026-07-09)).
- **Half** of the respondents in that survey say *being able to verify the recruiter's identity* is the biggest sign of trust. That verification is exactly what Jaanch automates.
- In Dec 2023 the government blocked **100+ websites** running task-based part-time job frauds that hooked people through "Ghar baithe job" ads and then moved them to WhatsApp and Telegram ([MHA/I4C via The News Minute](https://www.thenewsminute.com/news/govt-blocks-100-websites-involved-in-job-scams-illegal-investments)).

## How it works

```
 Student in ASI:One ──ChatMessage──▶  jaanch (orchestrator)
                                       │ 1. ASI1 + rules extract company, pay, fee,
                                       │    emails, domains, links
                                       ├──OfferFacts──▶ jaanch-domain-intel
                                       │                 RDAP domain age · MX records ·
                                       │                 brand lookalikes · official email
                                       ├──OfferFacts──▶ jaanch-pattern-check
                                       │                 fee/OTP/ID requests · task scams ·
                                       │                 Telegram · pressure · short links
                                       │ 2. evidence → fixed-formula 1–10 score
                                       │ 3. ASI1 explains in plain English/Hinglish
 ◀── verdict + interactive card ───────┘
 Other agents ──VerifyOfferRequest──▶ jaanch ──VerifyOfferResponse (score, reasons)──▶
```

- **ASI1 never sets the score.** The score is a sum of weighted evidence (table below), so the same message always gets the same score and every point traces back to a fact. ASI1 pulls structured facts out of messy text and writes the explanation.
- **Recovery from failure:** if a specialist agent doesn't reply within 20 s, the orchestrator runs that check itself. If ASI1 is unreachable, rule-based extraction and a template explanation take over. A network failure in domain lookups is reported, not treated as evidence.
- **No false alarms from negation:** "there is *no* registration fee" does not count as a fee demand.

### Agents

| Agent | Role | Protocols | Address |
|---|---|---|---|
| `jaanch` | Talks to users in ASI:One; coordinates the check | AgentChatProtocol 0.3.0, JaanchOfferVerification 1.0.0 | *fill in after first run* |
| `jaanch-domain-intel` | Domain age, mail server, lookalikes | JaanchDomainIntel 0.1.0 | *fill in after first run* |
| `jaanch-pattern-check` | Red flags in the text | JaanchPatternCheck 0.1.0 | *fill in after first run* |

### Evidence and weights

| Evidence | Points |
|---|---|
| Asks for a fee or deposit | +4 |
| Domain imitates a known employer (`infosys-careers.in`, `wipr0.com`) | +3 |
| Domain registered < 30 days ago | +3 |
| Asks for OTP / UPI PIN / card / remote access | +3 |
| Paid "tasks" (likes, reviews, ratings) | +3 |
| Claims a big brand but uses Gmail/Yahoo/Outlook | +2.5 |
| Moves you to Telegram / personal WhatsApp | +2 |
| Unrealistic pay for little work | +2 |
| Domain doesn't exist | +2 |
| Domain < 6 months old · email domain has no mail server · no interview | +1.5 each |
| Asks for Aadhaar/PAN/bank before interview · pressure to act fast · short links · free-mail recruiter | +1 each |
| Generic "Dear candidate" | +0.5 |
| Email from the named company's official domain | −2 |
| Domain older than 5 years | −1 |

Score = 2 + sum of points, clamped to 1–10. 1–3 low risk, 4–6 suspicious, 7–10 high risk.

## Run it

Needs Python 3.10–3.13.

```bash
pip install -r requirements.txt
cp .env.example .env        # add ASI1_API_KEY and three seed phrases

python scripts/check.py samples/scam_fee_whatsapp.txt     # one check, no agents
JAANCH_MAILBOX=0 python scripts/local_demo.py             # all agents + test clients, locally
python run.py                                             # all agents, connected to Agentverse
pytest -q                                                 # 39 tests, no network needed
```

On Windows, set variables with `set JAANCH_MAILBOX=0` before the command.

### Put it on Agentverse and ASI:One
1. Get an ASI1 API key at asi1.ai/dashboard/api-keys and put it in `.env` with three long random seed phrases.
2. `python run.py`. It prints the three agent addresses; copy them into the table above.
3. Open the Agent Inspector link printed for `jaanch`, click **Connect → Mailbox**. Repeat for the two specialists.
4. In Agentverse, open the `jaanch` profile and check that the README and badges show. Click **Chat with Agent** to open ASI:One, then paste a sample from `samples/`.
5. Share the ASI:One chat to get the public chat URL for the submission.

## What's built vs. next
**Built:** three agents with the Chat Protocol and a public verification protocol, ASI1 extraction and explanation with fallbacks, live RDAP/MX/lookalike checks, Hinglish red flags, an ASI:One interactive card with "How do I report this?" (1930 / cybercrime.gov.in / Chakshu), a local demo, and 39 tests.

**Next:**
- Payment Protocol for a paid deep report.
- A shared registry where reports from verified students raise the risk of repeat scam numbers and domains.
- Reading screenshots of offers, since most scams arrive as images on WhatsApp.
- A larger employer list.

## Team Chiranjivi
Abhishek Goswami · Akshat Gupta, GLA University, Mathura.
