"""Separate, durable early-observation delivery ledger (no formal state writes)."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from engine.early_observation import INTERVAL_MS


class EarlyObservationStore:
    def __init__(self, path: str):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, timeout=5)
        self.db.execute('''CREATE TABLE IF NOT EXISTS delivery (
            symbol TEXT, timeframe TEXT, side TEXT, bar INTEGER,
            low REAL, high REAL, sent_ms INTEGER, status TEXT,
            PRIMARY KEY(symbol, timeframe, side))''')
        self.db.commit()

    def close(self):
        self.db.close()

    @staticmethod
    def _overlap(zone, low, high):
        return min(zone[1], high) >= max(zone[0], low)

    def reserve(self, d: dict, now_ms: int) -> bool:
        """Reserve before network IO. Unknown delivery stays reserved to avoid
        retry spam; preference is at-most-once over a possible duplicate.
        SQLite serializes competing scanner instances; state errors fail closed.
        """
        try:
            self.db.execute("BEGIN IMMEDIATE")
            rows = self.db.execute("SELECT timeframe, side, bar, low, high, sent_ms FROM delivery WHERE symbol=?", (d["symbol"],)).fetchall()
            duration = INTERVAL_MS[d["timeframe"]]
            for tf, side, bar, low, high, sent in rows:
                if tf == d["timeframe"]:
                    bars = (d["open_time"]-bar)//duration
                    if bars < (4 if side == d["direction"] else 2):
                        self.db.rollback()
                        return False
                # Coalesce simultaneous same-area observations without sharing
                # candle IDs/cooldown slots between the two source timeframes.
                elif now_ms-sent < 900_000 and self._overlap(d["zone"], low, high):
                    self.db.rollback()
                    return False
            self.db.execute("INSERT OR REPLACE INTO delivery VALUES (?,?,?,?,?,?,?,?)", (
                d["symbol"], d["timeframe"], d["direction"], d["open_time"],
                *d["zone"], now_ms, "reserved"))
            self.db.commit()
            return True
        except Exception:
            self.db.rollback()
            raise

    def delivered(self, d: dict):
        with self.db:
            self.db.execute("UPDATE delivery SET status='delivered' WHERE symbol=? AND timeframe=? AND side=? AND bar=?", (
                d["symbol"], d["timeframe"], d["direction"], d["open_time"]))

    def already_observed_close(self, d: dict, closed_open: int) -> bool:
        """Suppress only the matching first 1H close after a delivered early
        observation. Later closed structures retain their normal semantics.
        """
        row = self.db.execute("SELECT bar, low, high, status FROM delivery WHERE symbol=? AND timeframe='1h' AND side=?", (
            d["symbol"], d["direction"])).fetchone()
        return bool(row and row[0] == closed_open and row[3] == "delivered" and self._overlap(d["zone"], row[1], row[2]))
