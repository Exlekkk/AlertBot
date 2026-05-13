from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from config import TREND_SNAPSHOT_STATE_FILE

STATE_FILE = Path(TREND_SNAPSHOT_STATE_FILE)


def make_snapshot_key(decision: dict) -> str:
    zl, zh = decision["zone"]
    zone_hash = hashlib.md5(f"{zl:.2f}-{zh:.2f}".encode()).hexdigest()[:10]
    return f"{decision['symbol']}|{decision['timeframe']}|{decision['alert_type']}|{decision['direction']}|{zone_hash}|{decision['state_version']}"


def load_trend_state(symbol: str, timeframe: str = "1h") -> dict[str, Any]:
    try:
        if not STATE_FILE.exists():
            return {"direction": "neutral", "has_snapshot": False}
        data = json.loads(STATE_FILE.read_text())
        return data.get(f"{symbol}|{timeframe}", {"direction": "neutral", "has_snapshot": False})
    except Exception:
        return {"direction": "neutral", "has_snapshot": False}


def save_trend_state(symbol: str, timeframe: str, direction: str, signature: str) -> None:
    data = {}
    try:
        if STATE_FILE.exists():
            data = json.loads(STATE_FILE.read_text())
    except Exception:
        data = {}
    data[f"{symbol}|{timeframe}"] = {"direction": direction, "has_snapshot": True, "signature": signature}
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(STATE_FILE.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(STATE_FILE)

def load_observation_state(symbol: str, timeframe: str = "1h") -> dict[str, Any]:
    """Load re-entry state for key-zone observation alerts."""
    try:
        if not STATE_FILE.exists():
            return {"inside_zone": False, "active_zone_hash": "", "reentry_count": 0}
        data = json.loads(STATE_FILE.read_text())
        observations = data.get("_observations", {})
        return observations.get(
            f"{symbol}|{timeframe}",
            {"inside_zone": False, "active_zone_hash": "", "reentry_count": 0},
        )
    except Exception:
        return {"inside_zone": False, "active_zone_hash": "", "reentry_count": 0}


def save_observation_state(symbol: str, timeframe: str, state: dict[str, Any]) -> None:
    """Persist key-zone observation state.

    The scanner writes this every loop, not only after a Telegram send.  That
    lets the observation layer re-arm after price leaves a zone and later
    re-enters it, while still avoiding repeated messages inside the same zone.
    """
    data: dict[str, Any] = {}
    try:
        if STATE_FILE.exists():
            data = json.loads(STATE_FILE.read_text())
    except Exception:
        data = {}

    observations = data.setdefault("_observations", {})
    observations[f"{symbol}|{timeframe}"] = dict(state)

    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(STATE_FILE.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(STATE_FILE)

