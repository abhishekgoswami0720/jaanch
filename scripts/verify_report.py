"""Prove a Jaanch signed evidence report is genuine and unedited.

Copy the whole report message from ASI:One into a text file, then run:
    python scripts/verify_report.py report.txt
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jaanch.evidence_report import verify_report  # noqa: E402


def parse(message: str) -> tuple[dict, str, str]:
    block = re.search(r"```json\s*(\{.*\})\s*```", message, re.DOTALL)
    signer = re.search(r"Signed by Jaanch:\**\s*`(agent1[0-9a-z]+)`", message)
    signature = re.search(r"Signature:\**\s*`(sig1[0-9a-z]+)`", message)
    if not (block and signer and signature):
        raise ValueError("couldn't find the report JSON, signer and signature in that text")
    return json.loads(block.group(1)), signer.group(1), signature.group(1)


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    report, signer, signature = parse(Path(sys.argv[1]).read_text(encoding="utf-8"))
    if verify_report(report, signer, signature):
        print(f"VALID: signed by {signer}; report {report['report_id']} from {report['checked_at_utc']}, unedited.")
        return 0
    print("NOT VALID: the report was edited or was not signed by this agent.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
