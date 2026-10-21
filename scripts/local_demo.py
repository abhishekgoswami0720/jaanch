"""Run all agents locally plus a test client that pastes the sample messages
into Jaanch over the Chat Protocol, and one other agent that uses the
JaanchOfferVerification protocol. Prints every reply, then exits.

    JAANCH_MAILBOX=0 python scripts/local_demo.py
"""

import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("JAANCH_MAILBOX", "0")

from uagents import Agent, Context  # noqa: E402
from uagents_core.contrib.protocols.chat import (  # noqa: E402
    ChatAcknowledgement,
    ChatMessage,
    MetadataContent,
    TextContent,
)

from jaanch.models import VerifyOfferRequest, VerifyOfferResponse  # noqa: E402
import run  # noqa: E402

SAMPLES = sorted((ROOT / "samples").glob("*.txt"))
client = Agent(name="demo-student", seed="jaanch local demo client seed")
job_agent = Agent(name="demo-job-search-agent", seed="jaanch local demo job agent seed")
replies: dict[str, str] = {}
done = asyncio.Event()
JAANCH = {"address": ""}


@client.on_event("startup")
async def paste_samples(ctx: Context):
    await asyncio.sleep(2)
    for path in SAMPLES:
        await ctx.send(JAANCH["address"], ChatMessage(content=[TextContent(text=path.read_text(encoding="utf-8"))]))
        await asyncio.sleep(0.5)


@client.on_message(ChatAcknowledgement)
async def on_ack(ctx: Context, sender: str, msg: ChatAcknowledgement):
    pass


@client.on_message(ChatMessage)
async def on_reply(ctx: Context, sender: str, msg: ChatMessage):
    text = "".join(c.text for c in msg.content if isinstance(c, TextContent))
    card = next((c.metadata for c in msg.content if isinstance(c, MetadataContent)), None)
    n = len(replies)
    print(f"\n===== Jaanch reply {n + 1} =====\n{text}")
    if card:
        payload = json.loads(card["card_payload"])
        print(f"[card: kind={card['card_kind']}, {len(json.dumps(payload))} bytes]")
    replies[f"chat{n}"] = text
    if len(replies) >= len(SAMPLES) + 1:
        done.set()


@job_agent.on_event("startup")
async def ask_before_recommending(ctx: Context):
    await asyncio.sleep(3)
    listing = (ROOT / "samples" / "scam_lookalike_email.txt").read_text(encoding="utf-8")
    reply, status = await ctx.send_and_receive(
        JAANCH["address"], VerifyOfferRequest(offer_text=listing), response_type=VerifyOfferResponse, timeout=60)
    print(f"\n===== Agent-to-agent trust check =====\n{reply}")
    replies["verify"] = str(reply)
    if len(replies) >= len(SAMPLES) + 1:
        done.set()


async def main():
    bureau = run.build_bureau(port=8010, extra_agents=(client, job_agent))
    JAANCH["address"] = next(a.address for a in bureau._agents if a.name == "jaanch")
    task = asyncio.create_task(bureau.run_async())
    try:
        await asyncio.wait_for(done.wait(), timeout=180)
    finally:
        print(f"\n{len(replies)} replies received")
        task.cancel()


if __name__ == "__main__":
    asyncio.run(main())
