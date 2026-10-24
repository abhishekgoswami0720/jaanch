# ASI:One Agent Challenge — Submission Dossier
## Project: Jaanch (जाँच) — Recruitment & Internship Fraud Detection Agent Network

> **Try it in ASI:One:** Search for **`@jaanch-scam-check`** on [ASI:One](https://asi1.ai) and paste any suspicious job offer or internship message.

---

### 1. Executive Summary

- **Project Name:** Jaanch (जाँच — Hindi for *"Check"* or *"Investigate"*)
- **Category:** Safety, Consumer Protection, Decentralized Trust & Multi-Agent Oracles
- **GitHub Repository:** [https://github.com/abhishekgoswami0720/jaanch](https://github.com/abhishekgoswami0720/jaanch)
- **Primary ASI:One Handle:** `@jaanch-scam-check`
- **Primary Agent Address:** `agent1qvvzp4xwu6c9ct6xrj8swxeet8aep6g36jf5cafegdfzh633zq3n7m4sd5u`
- **Total Test Suite:** 117 passing automated unit and integration tests

---

### 2. The Real-World Problem & Target Users

#### The Problem
Recruitment and fake internship fraud has surged dramatically across India and globally. Over **₹20,000 Crore (~$2.4 Billion USD)** was stolen through cyber-enabled employment scams in 2025 alone:
- Desperate college students and fresh graduates are targeted with fake appointment letters imitating reputed IT companies (Wipro, TCS, Infosys, Zoho).
- Scammers coerce victims into paying upfront *"training fees"*, *"seat reservation charges"*, *"laptop security deposits"*, or direct payments via personal UPI handles (`recruiter@okaxis`, `rzp.io` payment links).
- Victims are lured into WhatsApp/Telegram task traps (rating YouTube videos, reviewing hotels) before being extorted.
- 50%+ of students in campus recruitment surveys state that knowing whether a recruiter domain and offer letter is genuine before paying would have prevented financial disaster.

#### Target Users
1. **Students & Job Seekers:** Vulnerable freshers seeking quick, free, explainable fraud checks directly inside chat.
2. **University Placement Cells:** Campus placement officers screening thousands of incoming corporate recruitment drives before publishing listings to student portals.
3. **Victims of Scams:** People who need immediate, timestamped, tamper-evident evidence dockets to submit to police or the **1930 National Cybercrime Helpline / cybercrime.gov.in**.

---

### 3. Solution Overview: From Intent to Action

Jaanch is not a basic chatbot or thin wrapper around an LLM. It is an **autonomous multi-agent recruitment security network** operating on Fetch.ai's Agentverse that turns user intent into concrete investigative and protective action:

```
                      ┌────────────────────────────────────────┐
                      │             ASI:One User               │
                      │  (@jaanch-scam-check / Web Interface)  │
                      └───────────────────┬────────────────────┘
                                          │ ACP (Agent Chat Protocol)
                                          ▼
                      ┌────────────────────────────────────────┐
                      │           Jaanch Orchestrator          │
                      │ agent1qvvzp4xwu6c9ct6xrj8swxeet8aep6g  │
                      └───────┬───────────┼───────────┬────────┘
                              │           │           │
       ┌──────────────────────┘           │           └──────────────────────┐
       ▼                                  ▼                                  ▼
┌──────────────────────┐       ┌──────────────────────┐       ┌──────────────────────┐
│  jaanch-domain-intel │       │ jaanch-pattern-check │       │jaanch-reputation-intel│
│  • RDAP domain age   │       │ • Fee demands, UPI   │       │ • Reddit discussions │
│  • DNS MX mail server│       │ • Instant offer traps│       │ • r/developersIndia  │
│  • Brand lookalikes  │       │ • Task scam lures    │       │ • Developer blacklist│
└──────────────────────┘       └──────────────────────┘       └──────────────────────┘
       │                                  │                                  │
       └──────────────────────┬───────────┴──────────────────────────────────┘
                              ▼
                      ┌────────────────────────────────────────┐
                      │    Shared Cryptographic Scam Memory    │
                      │    (HMAC-SHA256 privacy-preserving)    │
                      └───────────────────┬────────────────────┘
                                          ▼
                      ┌────────────────────────────────────────┐
                      │        ASI:One Interactive Card        │
                      │  • Badges & 1-10 Explainable Risk Score│
                      │  • Forensic Evidence Log               │
                      │  • 🚨 "How do I report this?"          │
                      │  • 📋 "Copy Cybercrime Docket"         │
                      │  • 💳 "Signed report (0.1 FET)"        │
                      └───────────────────┬────────────────────┘
                                          ▼
                      ┌────────────────────────────────────────┐
                      │         AgentPaymentProtocol           │
                      │  • 0.1 FET payment on Fetch ledger     │
                      │  • Cryptographically signed report     │
                      │  • Offline verification via script     │
                      └────────────────────────────────────────┘
```

---

### 4. Live Agentverse Directory & Agent Addresses

Jaanch operates 4 specialized agents actively hosted on Fetch.ai's Agentverse:

| Agent Name | Role / Functionality | Protocols Implemented | Agent Address |
|---|---|---|---|
| **`jaanch`** (`@jaanch-scam-check`) | User interaction in ASI:One, document analysis, multi-agent dispatch, payment settlement | `AgentChatProtocol 0.3.0`<br>`JaanchOfferVerification 1.0.0`<br>`AgentPaymentProtocol 0.1.0` | `agent1qvvzp4xwu6c9ct6xrj8swxeet8aep6g36jf5cafegdfzh633zq3n7m4sd5u` |
| **`jaanch-domain-intel`** | Live RDAP registry lookups, domain age, DNS MX mail servers, typosquatting & brand lookalike checks | `JaanchDomainIntel 0.1.0` | `agent1qgu0xxylvpa9kv7he3vux9kj5x2l9ffdlad0hsh84nv23vf7avyw68j33th` |
| **`jaanch-pattern-check`** | 20+ specialized fraud pattern heuristics (advance fee demands, UPI handles, WhatsApp migration, task scams) | `JaanchPatternCheck 0.1.0` | `agent1qtwpt528nq7x73s3jxwtpfq9056wltxkwwn8d5393cdd2e4rpyxkjm34s46` |
| **`jaanch-reputation-intel`** | Real-time Reddit community sentiment, blacklist queries (`r/developersIndia`, `r/Indian_Academia`) | `JaanchReputationIntel 0.1.0` | `agent1qtg4nqryw3sqduwj9gvmkjdkl5kaut4eccujk5eekjmj298cgpvzjmd8gx7` |

---

### 5. Fulfillment of Challenge Criteria

#### Mandatory Requirements

1. **Registered on Agentverse & Discoverable on ASI:One:**
   - Live on Agentverse with registered manifests.
   - Searchable on [ASI:One](https://asi1.ai) via **`@jaanch-scam-check`**.
2. **Implements Agent Chat Protocol (ACP):**
   - Implemented via `uagents_core.contrib.protocols.chat` with `ChatMessage`, `TextContent`, and `MetadataContent`.
3. **Primary User Workflow Entirely Within ASI:One:**
   - Users never leave ASI:One. Pasting an offer returns an interactive card with a 1-10 risk score, verified evidence, reporting advice, cybercrime docket generation, and signed reports.
4. **Meaningful Tool Execution & Multi-Agent Orchestration:**
   - The Orchestrator gathers facts and queries three specialist agents concurrently via `ctx.send_and_receive`.
   - Real-time tools include:
     - **Live RDAP Lookups:** Directly queries ICANN/ARIN registrar RDAP servers to compute domain age in days.
     - **Live DNS MX Resolution:** Queries authoritative DNS servers to verify whether recruiters have active corporate mail servers.
     - **Reddit Community Sentiment:** Searches live Reddit threads for scam and fee complaints.
     - **MCA Validation:** Checks Ministry of Corporate Affairs CIN registration patterns.
     - **OCR Scanner:** Dual-engine OCR with local Tesseract and ASI1 Vision fallback.
5. **Public GitHub Repository with Instructions:**
   - Complete repo, setup instructions, architecture documentation, and test suite at [https://github.com/abhishekgoswami0720/jaanch](https://github.com/abhishekgoswami0720/jaanch).

---

### 6. Bonus Criteria Implementation

#### 1. Payment Protocol & Credible Monetization Model
- **Protocol:** Fully implements Fetch.ai's official `AgentPaymentProtocol` (`uagents_core.contrib.protocols.payment`, role `seller`).
- **Fair Dual-Tier Model:**
  - **Free Tier (Students):** Instant risk analysis, red flag detection, 1930 reporting instructions, and copyable cybercrime evidence docket remain **100% free forever**.
  - **Premium Tier (0.1 FET per report):** University placement cells, victims filing court/police cases, and HR tech platforms pay a nominal fee of **0.1 FET** for a **Cryptographically Signed Evidence Report**.
- **On-Chain Settlement & Replay Protection:**
  - Jaanch issues `RequestPayment(accepted_funds=[Funds(amount="0.1", currency="FET")])`.
  - When the buyer commits payment, Jaanch inspects the transaction directly on the **Fetch.ai Dorado Testnet ledger** (`fet_payments.verify_payment`), verifies the recipient address and amount, marks the transaction hash as consumed to prevent replay attacks, and issues `CompletePayment`.
  - The signed report is sealed using the agent's private cryptographic identity (`ctx.agent.identity`) and can be verified offline by any third party using `python scripts/verify_report.py report.txt`.

#### 2. Effective Use of ASI:One Interactive Cards
- Interactive cards provide an intuitive, action-oriented experience:
  - **Verdict Card:** Renders status badges, risk level (1-10), heading, bulleted evidence points, and checked domains.
  - **Action Buttons:**
    - `🚨 How do I report this?`: Gives step-by-step reporting instructions (Helpline 1930, cybercrime.gov.in, Chakshu).
    - `📋 Copy Cybercrime Docket`: Generates a pre-formatted, legal-ready complaint report containing suspect phone numbers, UPI handles, lookalike domains, and evidence log.
    - `💳 Signed report (0.1 FET)`: Initiates the AgentPaymentProtocol transaction.
    - `🔄 Check another offer`: Resets the session with instructions.

#### 3. Strong Reliability & Graceful Recovery
- **Specialist Agent Fallbacks:** If any specialist agent (`domain`, `pattern`, `reputation`) does not reply within 20 seconds, Jaanch runs the analysis locally without dropping the user's conversation.
- **LLM Degradation Recovery:** If the ASI1 API is unavailable or rate-limited, Jaanch automatically falls back to regex extraction, rule-based heuristics, and the trained ML model.
- **Network Resilience:** If WHOIS/RDAP servers throttle requests, domain age errors are logged gracefully without failing the overall risk score.

#### 4. Autonomous Placement Cell Oracle (B2B Multi-Agent Flow)
- Demonstrates autonomous agent-to-agent collaboration:
  - A university placement cell agent (`gla-placement-cell-agent`) receives corporate listings.
  - It autonomously queries the Jaanch Oracle using the `JaanchOfferVerification` protocol.
  - If a listing is flagged as a scam (>=7/10), it is quarantined automatically.
  - If genuine (<=3/10), the placement agent approves the listing and commits payment via `AgentPaymentProtocol` to obtain an official verification seal.
  - Run locally in one command: `python scripts/placement_oracle_demo.py`.

---

### 7. Step-by-Step Instructions to Run and Test

#### 1. Setup & Environment
```bash
git clone https://github.com/abhishekgoswami0720/jaanch
cd jaanch

# Create virtual environment & install dependencies
python -m venv .venv
source .venv/bin/activate  # On Windows: .\.venv\Scripts\activate
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Add your ASI1_API_KEY (optional: if omitted, deterministic fallback heuristics run)
```

#### 2. Run the Full Test Suite
```bash
pytest -v
# Output: 117 passed in ~17s
```

#### 3. Run Autonomous B2B Multi-Agent Placement Screening
```bash
python scripts/placement_oracle_demo.py
```

#### 4. Run the Jaanch Web App & REST API
```bash
python run.py web
# Open http://localhost:8010 in your browser
```

#### 5. Verify a Signed Evidence Report
```bash
python scripts/verify_report.py samples/signed_report_example.txt
```

---

### 8. Short Video Demo Walkthrough Script

1. **Scene 1: Introduction (0:00 - 0:30)**
   - Highlight the epidemic of recruitment and fake internship scams targeting students.
   - Show ASI:One interface and search for `@jaanch-scam-check`.
2. **Scene 2: Instant Scam Detection in ASI:One (0:30 - 1:15)**
   - Paste a real-world scam offer demanding a ₹1,500 security deposit via WhatsApp.
   - Show Jaanch returning an Interactive Verdict Card: **Risk 9/10 (High Risk)** with evidence points (lookalike domain, advance fee trap, WhatsApp redirection).
   - Click **"Copy Cybercrime Docket"** to reveal the pre-formatted report for `cybercrime.gov.in`.
3. **Scene 3: Autonomous Multi-Agent Placement Oracle (1:15 - 2:00)**
   - Run `python scripts/placement_oracle_demo.py`.
   - Show the university placement agent sending 3 listings to Jaanch:
     - Zoho offer: Verified genuine (1/10) -> Approved for students.
     - Infosys deposit scam: Flagged (9/10) -> Quarantined automatically.
4. **Scene 4: Payment Protocol Settlement (2:00 - 2:45)**
   - Trigger the **"Signed report (0.1 FET)"** flow.
   - Demonstrate `RequestPayment` -> `CommitPayment` verified against the Fetch.ai Dorado ledger -> `CompletePayment` -> Cryptographically signed report delivered and verified offline.
5. **Scene 5: Conclusion & Post-Hackathon Roadmap (2:45 - 3:00)**
   - Summarize the social impact: protecting millions of freshers while establishing a sustainable, decentralized B2B verification oracle on Fetch.ai.
