"""Check one offer from the terminal, without starting any agents.

    python scripts/check.py samples/scam_fee_whatsapp.txt
    python scripts/check.py "Pay ₹999 registration fee to confirm your internship"
"""

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

from jaanch import llm  # noqa: E402
from jaanch.pipeline import run_local  # noqa: E402


async def main(arg: str):
    path = Path(arg)
    text = path.read_text(encoding="utf-8") if path.exists() else arg
    result = await run_local(text)
    print(f"Extracted by {result.facts.extracted_by}: company={result.facts.company} fee={result.facts.fee} "
          f"pay={result.facts.pay} domains={result.facts.domains} emails={result.facts.emails}")
    print(f"\nRISK {result.risk}/10 · {result.verdict_text}")
    for s in result.signals:
        print(f"  {s.weight:+.1f}  {s.label}  [{s.source}: {s.evidence[:80]}]")
    for e in result.errors:
        print(f"  (note) {e}")
    print("\n" + await llm.explain(text, result.risk, result.verdict_text, result.signals))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    load_dotenv()
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    asyncio.run(main(sys.argv[1]))
