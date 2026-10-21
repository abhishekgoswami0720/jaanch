"""Start the Jaanch agents.

    python run.py                 # all three agents in one process (Bureau)
    python run.py jaanch          # one agent per terminal: jaanch | domain | pattern
    JAANCH_MAILBOX=0 python run.py    # fully local, for testing

With mailboxes on, each agent prints an Agent Inspector link: open it and
click Connect -> Mailbox to put that agent on Agentverse. If ASI:One can't
reach the agents when they share one process, run them in three terminals.
"""

import os
import sys

from dotenv import load_dotenv
from uagents import Bureau
from uagents.crypto import Identity

load_dotenv()

from agents.orchestrator import build_orchestrator  # noqa: E402
from agents.specialists import (  # noqa: E402
    DOMAIN_DEV_SEED,
    PATTERN_DEV_SEED,
    build_domain_agent,
    build_pattern_agent,
)

MAILBOX = os.getenv("JAANCH_MAILBOX", "1") != "0"


def _address(seed_var: str, dev_seed: str) -> str:
    return Identity.from_seed(os.getenv(seed_var) or dev_seed, 0).address


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


def run_single(which: str, port: int) -> None:
    if which == "jaanch":
        agent = build_orchestrator(MAILBOX, _address("JAANCH_DOMAIN_SEED", DOMAIN_DEV_SEED),
                                   _address("JAANCH_PATTERN_SEED", PATTERN_DEV_SEED), port=port)
    elif which == "domain":
        agent = build_domain_agent(MAILBOX, port=port)
    elif which == "pattern":
        agent = build_pattern_agent(MAILBOX, port=port)
    else:
        sys.exit("usage: python run.py [jaanch|domain|pattern]")
    print(f"{agent.name}: {agent.address}")
    agent.run()


if __name__ == "__main__":
    port = int(os.getenv("JAANCH_PORT", "8000"))
    if len(sys.argv) > 1:
        offsets = {"jaanch": 0, "domain": 1, "pattern": 2}
        run_single(sys.argv[1], port + offsets.get(sys.argv[1], 0))
    else:
        build_bureau(port=port).run()
