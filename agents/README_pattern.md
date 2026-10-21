# Jaanch Pattern Check

![tag:innovationlab](https://img.shields.io/badge/innovationlab-3D8BD3)
![tag:hackathon](https://img.shields.io/badge/hackathon-5F43F1)

Specialist agent in the Jaanch scam-checking system. It reads the text of a job or internship message (English or Hinglish) and returns red flags with the exact phrase that triggered each one: fee or deposit demands, OTP/UPI PIN/card requests, Aadhaar/PAN/bank requests, task scams, Telegram-only contact, unrealistic pay, no interview, pressure tactics, short links, and free-mail recruiters claiming a big brand. Negated phrases ("no registration fee") are ignored.

Protocol `JaanchPatternCheck`: send `OfferFacts`, receive `PatternReport { signals }`.
