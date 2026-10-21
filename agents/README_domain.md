# Jaanch Domain Intel

![tag:innovationlab](https://img.shields.io/badge/innovationlab-3D8BD3)
![tag:hackathon](https://img.shields.io/badge/hackathon-5F43F1)

Specialist agent in the Jaanch scam-checking system. Given the domains and email addresses from a job offer, it returns evidence:
- domain registration date from RDAP (flags domains under 30 days and under 6 months old),
- whether the domain has mail servers (MX over DNS-over-HTTPS) and whether it exists at all,
- lookalikes of well-known employers (`infosys-careers.in`, `wipr0.com`, `tcshiring.com`),
- a trust signal when the email comes from the named company's official domain.

Protocol `JaanchDomainIntel`: send `OfferFacts`, receive `DomainReport { signals, checked, errors }`.
