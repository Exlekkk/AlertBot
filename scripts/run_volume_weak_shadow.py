#!/usr/bin/env python3
"""Log-only shadow for unclosed abnormal-volume weak reminders.

Keeps the forming (last) candle — intentional for this weak path.
Never sends Telegram. Refuses without --shadow.
Does not touch 1H formal cooldown / observation / trial paths.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import KLINE_LIMIT, KLINE_LIMIT_15M
from engine.indicators import enrich_klines
from engine.market_data import BinanceMarketDataClient
from engine.volume_weak import (
    DEFAULT_COOLDOWN_BARS_15M,
    DEFAULT_OPPOSITE_COOLDOWN_BARS,
    evaluate_forming_volume_weak,
    format_volume_weak_log,
)


def _now() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _append_line(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(text.rstrip() + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run forming abnormal-volume weak-reminder shadow (log-only)."
    )
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--interval-seconds", type=int, default=60)
    parser.add_argument(
        "--shadow",
        action="store_true",
        help="Required safety flag. This script never sends Telegram.",
    )
    parser.add_argument("--log", default="logs/volume_weak_shadow.log")
    parser.add_argument("--cooldown-bars", type=int, default=DEFAULT_COOLDOWN_BARS_15M)
    parser.add_argument(
        "--opposite-cooldown-bars", type=int, default=DEFAULT_OPPOSITE_COOLDOWN_BARS
    )
    args = parser.parse_args()

    if not args.shadow:
        print("Refusing to run without --shadow. This test script is log-only.")
        return 2

    client = BinanceMarketDataClient()
    last_sent_by_side: dict[str, int] = {}
    last_side: str | None = None
    last_side_bar: int | None = None
    last_seen_open: int | None = None

    _append_line(
        args.log,
        f"{_now()} volume_weak_shadow_started symbol={args.symbol} "
        f"interval_seconds={args.interval_seconds}",
    )

    while True:
        try:
            raw_15m = client.get_klines(args.symbol, "15m", limit=KLINE_LIMIT_15M)
            raw_1h = client.get_klines(args.symbol, "1h", limit=KLINE_LIMIT)
            # Keep forming candle (do NOT drop last) — weak path only.
            k15 = enrich_klines(raw_15m)
            k1h = enrich_klines(raw_1h)

            decision = evaluate_forming_volume_weak(args.symbol, k15, k1h)
            latest_open = int((k15[-1] if k15 else {}).get("open_time", 0) or 0)
            if last_seen_open == latest_open and not decision.get("should_alert"):
                time.sleep(max(5, int(args.interval_seconds)))
                continue
            last_seen_open = latest_open

            if decision.get("should_alert"):
                side = str(decision.get("side") or "")
                bar_id = latest_open // (15 * 60 * 1000) if latest_open else 0
                prev = last_sent_by_side.get(side)
                if prev is not None and bar_id - prev < int(args.cooldown_bars):
                    _append_line(
                        args.log,
                        f"{_now()} suppress_volume_weak_duplicate "
                        f"{json.dumps(decision, ensure_ascii=False)}",
                    )
                elif (
                    last_side is not None
                    and last_side_bar is not None
                    and last_side != side
                    and bar_id - last_side_bar < int(args.opposite_cooldown_bars)
                ):
                    _append_line(
                        args.log,
                        f"{_now()} suppress_volume_weak_opposite "
                        f"{json.dumps(decision, ensure_ascii=False)}",
                    )
                else:
                    last_sent_by_side[side] = bar_id
                    last_side = side
                    last_side_bar = bar_id
                    _append_line(args.log, f"{_now()} {format_volume_weak_log(decision)}")
                    _append_line(
                        args.log, json.dumps(decision, ensure_ascii=False, sort_keys=True)
                    )
            else:
                _append_line(args.log, f"{_now()} {format_volume_weak_log(decision)}")

        except Exception as exc:
            _append_line(args.log, f"{_now()} volume_weak_shadow_error error={exc}")

        time.sleep(max(5, int(args.interval_seconds)))


if __name__ == "__main__":
    raise SystemExit(main())
