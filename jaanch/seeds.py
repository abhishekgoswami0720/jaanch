"""Agent seeds. A seed is the agent's private key: whoever knows it can act as the agent.

If a specialist's own seed isn't set but JAANCH_SEED is, a private seed is derived
from JAANCH_SEED, so no agent silently falls back to a public dev seed. run.py and
the agents use this same function, so the orchestrator always knows the right
addresses.
"""

import os


def resolve_seed(var: str, dev_default: str, warn: bool = True) -> str:
    seed = os.getenv(var)
    if seed:
        return seed
    main = os.getenv("JAANCH_SEED")
    if main and var != "JAANCH_SEED":
        return f"{main} :: {var}"
    if warn:
        print(f"[warn] {var} and JAANCH_SEED are not set; using a public dev seed. Set JAANCH_SEED before deploying.")
    return dev_default
