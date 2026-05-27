import hashlib
import json
from datetime import datetime
from pathlib import Path

USAGE_FILE = Path("/tmp/intent_gap_usage.json")
FREE_DAILY_LIMIT = 3


def fingerprint_from_headers(headers: dict) -> str:
    raw = headers.get("X-Forwarded-For", "") or headers.get("x-forwarded-for", "")
    ip = raw.split(",")[0].strip() if raw else headers.get("Host", "unknown")
    return hashlib.sha256(ip.encode("utf-8")).hexdigest()[:16]


def _load() -> dict:
    if not USAGE_FILE.exists():
        return {}
    try:
        return json.loads(USAGE_FILE.read_text())
    except Exception:
        return {}


def _save(usage: dict) -> None:
    USAGE_FILE.parent.mkdir(parents=True, exist_ok=True)
    USAGE_FILE.write_text(json.dumps(usage))


def _today() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d")


def runs_remaining(fingerprint: str) -> int:
    usage = _load()
    key = f"{fingerprint}:{_today()}"
    return max(0, FREE_DAILY_LIMIT - usage.get(key, 0))


def record_run(fingerprint: str) -> None:
    usage = _load()
    today = _today()
    key = f"{fingerprint}:{today}"
    usage[key] = usage.get(key, 0) + 1
    usage = {k: v for k, v in usage.items() if k.endswith(today)}
    _save(usage)
