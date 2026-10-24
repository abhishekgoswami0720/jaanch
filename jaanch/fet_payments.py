"""Checking that a FET payment really reached Jaanch's wallet on the Fetch.ai ledger.

Used by the Payment Protocol handler before anything paid is delivered.
Testnet (Dorado, test FET from the faucet) is the default, so the demo never
spends real money; set JAANCH_FET_TESTNET=false for mainnet.
"""

import os
import re
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

FET_DECIMALS = 10**18


def use_testnet() -> bool:
    return os.getenv("JAANCH_FET_TESTNET", "true").strip().lower() not in ("0", "false", "no")


def network_name() -> str:
    return "stable-testnet" if use_testnet() else "mainnet"


def denom() -> str:
    return "atestfet" if use_testnet() else "afet"


def price_fet() -> str:
    raw = os.getenv("JAANCH_REPORT_PRICE_FET", "0.1").strip()
    try:
        if Decimal(raw) <= 0:
            raise InvalidOperation
    except InvalidOperation:
        return "0.1"
    return raw


def to_base_units(amount_fet: str) -> int:
    return int(Decimal(amount_fet) * FET_DECIMALS)


def _paid_amount(amount_field: str, coin_denom: str) -> int:
    """'100000000000000000atestfet,5afet' -> amount in the given denom."""
    total = 0
    for part in (amount_field or "").split(","):
        m = re.fullmatch(r"\s*(\d+)([a-z/0-9]+)\s*", part)
        if m and m.group(2) == coin_denom:
            total += int(m.group(1))
    return total


def check_transfer(tx: Any, recipient: str, expected_amount_fet: str,
                   buyer: Optional[str] = None, coin_denom: Optional[str] = None) -> tuple[bool, str]:
    """Check a cosmpy TxResponse-like object for a successful transfer to `recipient`."""
    coin_denom = coin_denom or denom()
    if tx is None:
        return False, "transaction not found"
    if getattr(tx, "code", 1) != 0:
        return False, "transaction failed on the ledger"

    transfers = []
    events = getattr(tx, "events", None) or {}
    if "transfer" in events:
        transfers.append(events["transfer"])
    for log in getattr(tx, "logs", None) or []:
        log_events = getattr(log, "events", None) or {}
        if "transfer" in log_events:
            transfers.append(log_events["transfer"])

    expected = to_base_units(expected_amount_fet)
    for t in transfers:
        if t.get("recipient") != recipient:
            continue
        if buyer and t.get("sender") not in (None, buyer):
            continue
        if _paid_amount(t.get("amount", ""), coin_denom) >= expected:
            return True, "ok"
    return False, f"no transfer of {expected_amount_fet} FET to Jaanch's wallet in this transaction"


def fetch_tx(tx_hash: str) -> Any:
    """Look the transaction up on the Fetch.ai ledger (blocking; run it in a thread)."""
    from cosmpy.aerial.client import LedgerClient, NetworkConfig

    config = NetworkConfig.fetchai_stable_testnet() if use_testnet() else NetworkConfig.fetchai_mainnet()
    return LedgerClient(config).query_tx(tx_hash)


def verify_payment(tx_hash: str, recipient: str, expected_amount_fet: str,
                   buyer: Optional[str] = None) -> tuple[bool, str]:
    if not tx_hash or not re.fullmatch(r"[0-9A-Fa-f]{64}", tx_hash.strip()):
        return False, "that doesn't look like a Fetch.ai transaction hash"
    try:
        tx = fetch_tx(tx_hash.strip().upper())
    except Exception as err:
        return False, f"couldn't find the transaction on the ledger yet ({type(err).__name__})"
    return check_transfer(tx, recipient, expected_amount_fet, buyer=buyer)
