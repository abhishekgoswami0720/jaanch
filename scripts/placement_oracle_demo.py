"""Autonomous Campus Placement Oracle Demo.

Demonstrates Fetch.ai Agent-to-Agent communication:
1. A 'Campus Placement Cell Agent' receives 3 incoming job/internship listings for students.
2. Before publishing them on the student board, it autonomously calls the Jaanch Verification Oracle
   using the JaanchOfferVerification protocol (VerifyOfferRequest -> VerifyOfferResponse).
3. If Jaanch flags a listing as High Risk (>=7), the Placement Agent automatically quarantines
   the listing and generates an alert. Genuine offers (<=3) are published instantly.

Usage:
    JAANCH_MAILBOX=0 python scripts/placement_oracle_demo.py
"""

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("JAANCH_MAILBOX", "0")

from uagents import Agent, Bureau, Context  # noqa: E402
from jaanch.models import VerifyOfferRequest, VerifyOfferResponse  # noqa: E402
import run  # noqa: E402

TEST_LISTINGS = [
    {
        "id": "JOB-2026-01",
        "title": "Member Technical Staff @ Zoho",
        "text": "Offer of employment for Member Technical Staff at Zoho. Interview conducted on 12 Oct. Candidate portal at https://careers.zoho.com.",
        "url": "https://careers.zoho.com",
    },
    {
        "id": "JOB-2026-02",
        "title": "Software Intern @ Unified Mentor",
        "text": "Your profile has been selected for Internship Program at Unified Mentor Pvt. Ltd. Induction Today at 05:00 PM. Join WhatsApp Group: https://chat.whatsapp.com/BaEnmYMEkhq45novAx73l4.",
        "url": "https://chat.whatsapp.com/BaEnmYMEkhq45novAx73l4",
    },
    {
        "id": "JOB-2026-03",
        "title": "Infosys Remote Internship Kit",
        "text": "Selected for Infosys remote internship. Pay ₹1,500 security deposit to recruiter@okaxis before laptop kit dispatch. Contact placement@infosys-careers.in.",
        "url": "http://infosys-careers.in",
    },
]

placement_agent = Agent(name="gla-placement-cell-agent", seed="placement cell seed phrase 2026")
JAANCH_ADDRESS = {"address": ""}
VERIFIED_COUNT = {"count": 0}


@placement_agent.on_event("startup")
async def start_screening(ctx: Context):
    ctx.logger.info("🎓 GLA Placement Cell Agent started. Waiting for Jaanch Oracle...")
    await asyncio.sleep(2)
    ctx.logger.info(f"📋 Received {len(TEST_LISTINGS)} incoming company listings. Submitting to Jaanch Oracle for autonomous screening...")

    for job in TEST_LISTINGS:
        print(f"\n[Placement Agent] -> Sending listing '{job['title']}' to Jaanch Oracle...")
        req = VerifyOfferRequest(offer_text=job["text"], source_url=job["url"])
        await ctx.send(JAANCH_ADDRESS["address"], req)
        await asyncio.sleep(1)


@placement_agent.on_message(VerifyOfferResponse)
async def on_verification_verdict(ctx: Context, sender: str, res: VerifyOfferResponse):
    VERIFIED_COUNT["count"] += 1
    idx = VERIFIED_COUNT["count"] - 1
    job = TEST_LISTINGS[idx]

    print("\n" + "═" * 60)
    print(f"📥 [Placement Agent] <- Received Oracle Verdict for: {job['title']}")
    print(f"   Risk Score: {res.risk_score}/10 | Verdict: {res.verdict.upper()}")

    if res.risk_score >= 7:
        print(f"   🚫 ACTION: QUARANTINED! Listing removed from student board.")
        print(f"   🚩 Detected Reasons: {', '.join(res.reasons)}")
        print(f"   ⚠️ Action: Auto-flagging recruiter domain: {res.checked_domains}")
    elif res.risk_score >= 4:
        print(f"   ⚠️ ACTION: FLAGGED FOR MANUAL REVIEW by Placement Officer.")
        print(f"   🚩 Reasons: {', '.join(res.reasons)}")
    else:
        print(f"   ✅ ACTION: APPROVED! Listing verified & published to student portal.")
    print("═" * 60)

    if VERIFIED_COUNT["count"] >= len(TEST_LISTINGS):
        print("\n🎉 Autonomous screening completed! All student listings secured.")
        await asyncio.sleep(1)
        os._exit(0)


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    port = 8100
    bureau = run.build_bureau(port=port, extra_agents=[placement_agent])
    # Find Jaanch orchestrator address
    for a in bureau._agents:
        if a.name == "jaanch":
            JAANCH_ADDRESS["address"] = a.address

    print("\n🚀 Starting Autonomous B2B Multi-Agent Placement Screening Network...")
    bureau.run()


if __name__ == "__main__":
    main()
