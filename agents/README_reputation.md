# Jaanch Reputation Intel: community scam reports

![tag:innovationlab](https://img.shields.io/badge/innovationlab-3D8BD3)
![tag:hackathon](https://img.shields.io/badge/hackathon-5F43F1)

A specialist agent in the **Jaanch** job-scam checker. Given the facts of a job or internship offer (company name, websites), it searches public Reddit discussions for scam, fake-internship and upfront-fee complaints about that company or domain, and returns the findings as evidence.

The very largest employers (TCS, Infosys, Wipro, HCL, IBM) are skipped on purpose: people often ask "is X a scam?" about real companies, and that would cause false alarms.

## Protocol
`JaanchReputationIntel 0.1.0`
- Request: `OfferFacts` (company, domains, emails, links, text)
- Response: `ReputationReport { signals: [Signal], checked: [str], errors: [str] }`

Used by the `jaanch` agent (`@jaanch-scam-check` on ASI:One). If this agent doesn't answer within 12 seconds, `jaanch` answers without it, so a slow Reddit never holds up the verdict.

Built by Team Chiranjivi for Fetch-A-Thon 3.0.
