from __future__ import annotations

import hashlib


def make_snapshot_key(decision: dict) -> str:
    zl, zh = decision["zone"]
    zone_hash = hashlib.md5(f"{zl:.2f}-{zh:.2f}".encode()).hexdigest()[:10]
    return f"{decision['symbol']}|{decision['timeframe']}|{decision['alert_type']}|{decision['direction']}|{zone_hash}|{decision['state_version']}"
