from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from config import HEARTBEAT_STALE_AFTER_SECONDS, SMCT_RUNTIME_STATE_FILE


class RuntimeStateStore:
    def __init__(self, state_file: str | None = None):
        self.state_file = Path(state_file or SMCT_RUNTIME_STATE_FILE)
        self.state: dict[str, Any] = {
            "last_scan_at": 0.0,
            "last_scan_ok": False,
            "last_scan_error": "",
            "last_symbol": "",
            "last_summary": {},
            "last_sent_signal": {},
            "last_webhook": {},
        }
        self._load()

    def _load(self) -> None:
        try:
            if self.state_file.exists():
                self.state.update(json.loads(self.state_file.read_text()))
        except Exception:
            pass

    def _save(self) -> None:
        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            self.state_file.write_text(json.dumps(self.state, ensure_ascii=False, indent=2))
        except Exception:
            pass

    def mark_scan(self, ok: bool, symbol: str, summary: dict[str, Any] | None = None, error: str = "") -> None:
        self.state["last_scan_at"] = time.time()
        self.state["last_scan_ok"] = bool(ok)
        self.state["last_scan_error"] = error
        self.state["last_symbol"] = symbol
        self.state["last_summary"] = summary or {}
        self._save()

    def mark_sent_signal(self, signal: dict[str, Any]) -> None:
        self.state["last_sent_signal"] = {
            "signal": signal.get("signal"),
            "symbol": signal.get("symbol"),
            "direction": signal.get("direction"),
            "price": signal.get("price"),
            "state_1h": signal.get("state_1h"),
            "trigger_15m_state": signal.get("trigger_15m_state"),
            "tai_budget_mode": signal.get("tai_budget_mode"),
            "sent_at": time.time(),
        }
        self._save()

    def mark_webhook_send(self, symbol: str, signal: str) -> None:
        self.state["last_webhook"] = {
            "symbol": symbol,
            "signal": signal,
            "status": "sent",
            "at": time.time(),
        }
        self._save()

    def mark_webhook_skip(self, symbol: str, signal: str, reason: str) -> None:
        self.state["last_webhook"] = {
            "symbol": symbol,
            "signal": signal,
            "status": "skipped",
            "reason": reason,
            "at": time.time(),
        }
        self._save()

    def get_snapshot(self) -> dict[str, Any]:
        return dict(self.state)

    def build_health_payload(self) -> dict[str, Any]:
        last_scan_at = float(self.state.get("last_scan_at", 0.0) or 0.0)
        age = max(0, int(time.time() - last_scan_at)) if last_scan_at else None
        stale = age is None or age > HEARTBEAT_STALE_AFTER_SECONDS
        return {
            "ok": bool(self.state.get("last_scan_ok")) and not stale,
            "stale": stale,
            "seconds_since_last_scan": age,
            "last_scan_error": self.state.get("last_scan_error", ""),
            "last_symbol": self.state.get("last_symbol", ""),
            "last_summary": self.state.get("last_summary", {}),
            "last_sent_signal": self.state.get("last_sent_signal", {}),
            "last_webhook": self.state.get("last_webhook", {}),
        }
