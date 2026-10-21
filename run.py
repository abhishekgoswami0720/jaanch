"""Start all three Jaanch agents in one process.

    python run.py            # connects to Agentverse through mailboxes
    JAANCH_MAILBOX=0 python run.py   # fully local, for testing
"""

import os

from dotenv import load_dotenv
from uagents import Bureau

load_dotenv()

from agents.orchestrator import build_orchestrator  # noqa: E402
from agents.specialists import build_domain_agent, build_pattern_agent  # noqa: E402

MAILBOX = os.getenv("JAANCH_MAILBOX", "1") != "0"


def build_bureau(port: int = 8000, extra_agents=()) -> Bureau:
    domain = build_domain_agent(MAILBOX)
    pattern = build_pattern_agent(MAILBOX)
    jaanch = build_orchestrator(MAILBOX, domain.address, pattern.address)
    print(f"jaanch (talk to this one): {jaanch.address}")
    print(f"jaanch-domain-intel:       {domain.address}")
    print(f"jaanch-pattern-check:      {pattern.address}")
    bureau = Bureau(port=port, endpoint=[f"http://127.0.0.1:{port}/submit"])
    for agent in (jaanch, domain, pattern, *extra_agents):
        bureau.add(agent)
    return bureau


if __name__ == "__main__":
    build_bureau(port=int(os.getenv("JAANCH_PORT", "8000"))).run()
