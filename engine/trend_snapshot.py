from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

STATE_FILE = Path('/tmp/alertbot_trend_snapshot.json')


def make_snapshot_key(decision: dict) -> str:
    zl, zh = decision["zone"]
    zone_hash = hashlib.md5(f"{zl:.2f}-{zh:.2f}".encode()).hexdigest()[:10]
    return f"{decision['symbol']}|{decision['timeframe']}|{decision['alert_type']}|{decision['direction']}|{zone_hash}|{decision['state_version']}"


def load_trend_state(symbol: str, timeframe: str = "1h") -> dict[str, Any]:
    if not STATE_FILE.exists():
        return {"direction": "neutral", "has_snapshot": False}
    data = json.loads(STATE_FILE.read_text())
    key = f"{symbol}|{timeframe}"
    return data.get(key, {"direction": "neutral", "has_snapshot": False})


def save_trend_state(symbol: str, timeframe: str, direction: str, signature: str) -> None:
    data = {}
    if STATE_FILE.exists():
        data = json.loads(STATE_FILE.read_text())
    data[f"{symbol}|{timeframe}"] = {"direction": direction, "has_snapshot": True, "signature": signature}
    STATE_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
