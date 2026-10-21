![tag:innovationlab](https://img.shields.io/badge/innovationlab-3D8BD3)
![tag:hackathon](https://img.shields.io/badge/hackathon-5F43F1)

<p align="center">
<picture><source media="(prefers-color-scheme: dark)" srcset="assets/banner-dark.svg"><source media="(prefers-color-scheme: light)" srcset="assets/banner-light.svg"><img alt="Jaanch: check a job offer before it checks your wallet" src="assets/banner-dark.svg" width="100%"></picture>
</p>

**Got a job or internship offer that feels too good to be true?** Paste it into Jaanch. In a few seconds you get a **risk score from 1 to 10**, the reasons behind it, and what to do next.

*Jaanch* (जाँच) means "check" in Hindi. It runs as three small AI agents on Fetch.ai's Agentverse, and you talk to it in **ASI:One**, like any chat app.

---

## Why this matters

Fake job offers are everywhere, and they target students and first-time job seekers the most.

<p align="center">
<picture><source media="(prefers-color-scheme: dark)" srcset="assets/survey-dark.svg"><source media="(prefers-color-scheme: light)" srcset="assets/survey-light.svg"><img alt="93 of every 100 Indian job seekers have seen a fake or suspicious offer; 51 can't tell a real recruiter from a scammer; 50 say knowing who the recruiter is matters most" src="assets/survey-dark.svg" width="100%"></picture>
</p>

<sub>Source: [Indeed survey reported by Business Today, July 2026](https://www.businesstoday.in/jobs/story/more-than-9-in-10-job-seekers-encounter-fake-job-offers-542006-2026-07-09)</sub>

In December 2023 the government blocked **more than 100 websites** running "work from home" job scams. They pulled people in with *"Ghar baithe job"* ads and then moved them to WhatsApp and Telegram ([MHA/I4C via The News Minute](https://www.thenewsminute.com/news/govt-blocks-100-websites-involved-in-job-scams-illegal-investments)).

Half the people in that survey said that knowing who the recruiter really is would make them trust an offer. **Checking that is exactly what Jaanch does for you.**

---

## How it works

```mermaid
flowchart LR
    A["📩 You paste the offer<br/>into ASI:One"] --> B["🧠 Jaanch reads it<br/>company, pay, fee,<br/>emails, links"]
    B --> C["🌐 Website checker<br/>How old is the website?<br/>Does it copy a big brand?<br/>Can it even receive email?"]
    B --> D["🚩 Red-flag checker<br/>Asks for money or OTP?<br/>Moves you to Telegram?<br/>Rushes you?"]
    C --> E["🔢 Adds up the points<br/>score from 1 to 10"]
    D --> E
    E --> F["💬 Plain answer<br/>score + reasons +<br/>what to do next"]
```

Two helper agents do the checking at the same time, so the answer comes back fast. Job-search and career agents can also ask Jaanch to check a listing *before* they show it to you.

---

## How to read the score

<p align="center">
<picture><source media="(prefers-color-scheme: dark)" srcset="assets/scale-dark.svg"><source media="(prefers-color-scheme: light)" srcset="assets/scale-light.svg"><img alt="Score scale: 1 to 3 low risk, 4 to 6 suspicious, 7 to 10 high risk" src="assets/scale-dark.svg" width="100%"></picture>
</p>

Every offer starts at **2**. Each warning sign adds points and each good sign takes some away:

| What Jaanch finds | Points |
|---|:---:|
| 💸 Asks you to **pay a fee or deposit** to get the job | **+4** |
| 🎭 Website **copies a big company's name** (like `infosys-careers.in` or `wipr0.com`) | **+3** |
| 🆕 Website was **made less than 30 days ago** | **+3** |
| 🔐 Asks for your **OTP, UPI PIN, card details** or remote access to your phone | **+3** |
| 👍 Pays you for **"tasks"** like liking videos or writing reviews | **+3** |
| 📧 Says it's a big company but emails from **Gmail, Yahoo or Outlook** | **+2.5** |
| ✈️ Moves you to **Telegram or a personal WhatsApp** | **+2** |
| 🤑 Promises **a lot of money for very little work** | **+2** |
| ❓ The website **doesn't exist** at all | **+2** |
| 🕐 Website less than 6 months old · its email can't receive mail · **no interview** | **+1.5** each |
| 🪪 Wants **Aadhaar, PAN or bank details** before any interview · **rushes you** · uses **short links** · recruiter on a free email | **+1** each |
| 👋 Starts with a generic **"Dear candidate"** | **+0.5** |
| ✅ Email comes from the **company's real website** | **−2** |
| ✅ Website is **more than 5 years old** | **−1** |

The score always stays between 1 and 10.

---

## Does it work?

We wrote six test messages that copy real Indian job scams (and two genuine offers) and ran them through Jaanch:

<p align="center">
<picture><source media="(prefers-color-scheme: dark)" srcset="assets/results-dark.svg"><source media="(prefers-color-scheme: light)" srcset="assets/results-light.svg"><img alt="Scores: fake Infosys email 10, fake TCS WhatsApp 10, Hinglish task scam 10, new startup offer 5, Internshala listing 1, Zoho campus offer 1" src="assets/results-dark.svg" width="100%"></picture>
</p>

All three scams scored **10**, both genuine offers scored **1**, and the borderline one landed in the middle. The messages are in [`samples/`](samples/).

### Where does a score come from?

Here's the fake Infosys email, point by point:

<p align="center">
<picture><source media="(prefers-color-scheme: dark)" srcset="assets/breakdown-dark.svg"><source media="(prefers-color-scheme: light)" srcset="assets/breakdown-light.svg"><img alt="Fake Infosys email: deposit +4, copies Infosys +3, website 11 days old +3, can't receive mail +1.5, wants Aadhaar/PAN/bank +1, pressure +1, short link +1, Dear Applicant +0.5; total 17, capped at 10" src="assets/breakdown-dark.svg" width="100%"></picture>
</p>

Every point comes from something you can see in the message or check about the website.

---

## Why you can trust the score

- **The AI never decides the score.** The AI only reads the messy message and explains the result in simple words. The score itself is plain maths over the evidence, so the same message always gets the same score.
- **It understands "no".** *"There is **no** registration fee"* is not counted as asking for a fee.
- **It keeps working when something breaks.** If a helper agent doesn't answer in 20 seconds, the main agent does that check itself. If the AI is down, simple rules take over. If a website lookup fails, Jaanch says so instead of guessing.
- **It speaks Hinglish.** Many scams are written in Hinglish, and Jaanch catches those red flags too.

---

## Think it's a scam? Do this

1. **Don't pay anything** and stop replying. Never share an OTP, PIN or ID documents.
2. **Already paid or shared bank details?** Call the cyber-fraud helpline **1930** right away. The faster you report, the better the chance of freezing the money.
3. File a complaint at **[cybercrime.gov.in](https://cybercrime.gov.in)**. Keep screenshots, the sender's number or email, and any payment IDs.
4. Report the number on **[Sanchar Saathi → Chakshu](https://sancharsaathi.gov.in)**, and block the chat in WhatsApp or Telegram.
5. Tell your college placement cell so they can warn other students.

In ASI:One, tap **"How do I report this?"** on Jaanch's answer to get these steps.

---

## For developers

<details>
<summary><b>Agents and protocols</b></summary>

<br>

| Agent | What it does | Protocols | Address |
|---|---|---|---|
| `jaanch` | Talks to users in ASI:One and runs the check | AgentChatProtocol 0.3.0, JaanchOfferVerification 1.0.0 | *fill in after first run* |
| `jaanch-domain-intel` | Domain age (RDAP), mail server (MX), lookalike brands | JaanchDomainIntel 0.1.0 | *fill in after first run* |
| `jaanch-pattern-check` | Red flags in the text | JaanchPatternCheck 0.1.0 | *fill in after first run* |

```mermaid
sequenceDiagram
    participant U as Student in ASI:One
    participant J as jaanch
    participant D as jaanch-domain-intel
    participant P as jaanch-pattern-check
    U->>J: ChatMessage (the offer)
    J->>J: ASI1 + rules extract company, pay, fee, emails, links
    par checks run in parallel
        J->>D: OfferFacts
        D-->>J: domain age, MX, lookalikes
    and
        J->>P: OfferFacts
        P-->>J: red flags in the text
    end
    Note over J: no reply in 20 s → runs that check itself
    J->>J: fixed formula → score 1–10
    J-->>U: verdict, reasons, interactive card
```

Other agents can call the same check:

- Request: `VerifyOfferRequest { offer_text: str, source_url: str | null }`
- Response: `VerifyOfferResponse { risk_score: int, verdict: "low_risk" | "suspicious" | "high_risk", reasons: [str], checked_domains: [str] }`

</details>

<details>
<summary><b>Run it yourself</b></summary>

<br>

Needs Python 3.10–3.13.

```bash
pip install -r requirements.txt
cp .env.example .env        # add ASI1_API_KEY and three seed phrases

python scripts/check.py samples/scam_fee_whatsapp.txt     # one check, no agents
JAANCH_MAILBOX=0 python scripts/local_demo.py             # all agents + test clients, locally
python run.py                                             # all agents, connected to Agentverse
python run.py jaanch    # or: domain / pattern; one agent per terminal
pytest -q                                                 # 40 tests, no network needed
```

On Windows, set variables with `set JAANCH_MAILBOX=0` before the command.

</details>

<details>
<summary><b>Put it on Agentverse and ASI:One</b></summary>

<br>

1. Get an ASI1 API key at asi1.ai/dashboard/api-keys and put it in `.env` with three long random seed phrases.
2. `python run.py`. It prints the three agent addresses; copy them into the agents table above. (If ASI:One can't reach the agents when they share one process, run `python run.py jaanch`, `python run.py domain` and `python run.py pattern` in three terminals instead.)
3. Open the Agent Inspector link printed for `jaanch`, click **Connect → Mailbox**. Repeat for the two specialists.
4. In Agentverse, open the `jaanch` profile and check that the README and badges show. Click **Chat with Agent** to open ASI:One, then paste a sample from `samples/`.
5. Share the ASI:One chat to get the public chat URL for the submission.

</details>

<details>
<summary><b>Project layout</b></summary>

<br>

```
agents/        the three uAgents (orchestrator + two specialists) and their Agentverse READMEs
jaanch/        the checking logic: extraction, domain intel, patterns, scoring, ASI1 calls
samples/       six test messages
scripts/       one-off check from the terminal, and a local demo
tests/         40 tests with a fake internet, so they run offline
run.py         starts the agents
```

</details>

---

## What's built and what's next

**Built:** three agents with the Chat Protocol and a public verification protocol, ASI1 extraction and explanation with fallbacks, live website checks, Hinglish red flags, an ASI:One card with "How do I report this?", a local demo, and 40 tests.

**Next:**
- 📸 Read **screenshots** of offers, since most scams arrive as images on WhatsApp.
- 🤝 A shared list where reports from verified students raise the risk of repeat scam numbers and websites.
- 💳 A paid deep report using the Payment Protocol.
- 🏢 A bigger list of real employers to compare against.

---

<p align="center">
Built for <b>Fetch-A-Thon 3.0</b> (Masters' Union, 24 Oct 2026) by <b>Team Chiranjivi</b><br>
Abhishek Goswami · Akshat Gupta · Anirudh Kumar · Parv Mishra · Anmol Gola · GLA University, Mathura
</p>
