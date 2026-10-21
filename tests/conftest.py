import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

NOW = datetime(2026, 10, 21, tzinfo=timezone.utc)

# Pretend internet: domain -> (registration date or None, has MX, exists)
WORLD = {
    "zoho.com": ("1996-08-26T04:00:00Z", True, True),
    "internshala.com": ("2010-06-29T08:53:10Z", True, True),
    "infosys-careers.in": ("2026-10-09T11:02:00Z", False, True),
    "infosys.com": ("1992-03-30T05:00:00Z", True, True),
    "fresh-hiring.com": ("2026-10-15T00:00:00Z", True, True),
    "young-startup.in": ("2026-07-01T00:00:00Z", True, True),
}


def make_fetch(world=None, fail=False):
    world = WORLD if world is None else world

    async def fetch(url: str):
        if fail:
            raise ConnectionError("network down")
        if "rdap.org/domain/" in url:
            domain = url.rsplit("/", 1)[1]
            if domain not in world or not world[domain][2]:
                return 404, None
            created = world[domain][0]
            return 200, {"ldhName": domain.upper(),
                         "events": [{"eventAction": "registration", "eventDate": created},
                                    {"eventAction": "expiration", "eventDate": "2030-01-01T00:00:00Z"}]}
        if "dns.google/resolve" in url:
            domain = url.split("name=")[1].split("&")[0]
            if domain not in world or not world[domain][2]:
                return 200, {"Status": 3, "Question": [{"name": domain + ".", "type": 15}]}
            answer = [{"name": domain + ".", "type": 15, "TTL": 300, "data": "10 mx." + domain + "."}]
            return 200, {"Status": 0, "Answer": answer if world[domain][1] else []}
        return 404, None

    return fetch


@pytest.fixture
def fetch():
    return make_fetch()


@pytest.fixture(autouse=True)
def no_llm(monkeypatch):
    """Tests never call ASI1; the rule-based path must stand on its own."""
    monkeypatch.delenv("ASI1_API_KEY", raising=False)
    monkeypatch.delenv("ASI_ONE_API_KEY", raising=False)


def sample(name: str) -> str:
    return (ROOT / "samples" / name).read_text(encoding="utf-8")
