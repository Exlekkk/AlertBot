#!/usr/bin/env python3
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

from engine.indicators import enrich_klines
from engine.market_data import BinanceMarketDataClient
from engine.prealert_15m import (
    DEFAULT_PREALERT_CONFIG,
    PrealertConfig,
    cooldown_bars_for_decision,
    decision_cadence_keys,
    evaluate_15m_prealert,
    format_prealert_log,
    is_high_quality_new_information,
)


def _now() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _append_line(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(text.rstrip() + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run 15m prealert shadow monitor without Telegram or orders.")
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--interval-seconds", type=int, default=60)
    parser.add_argument("--shadow", action="store_true", help="Required safety flag. This script never sends Telegram.")
    parser.add_argument("--log", default="logs/15m_shadow.log")
    parser.add_argument("--max-risk-pct", type=float, default=DEFAULT_PREALERT_CONFIG.max_risk_pct)
    parser.add_argument("--cooldown-bars", type=int, default=DEFAULT_PREALERT_CONFIG.cooldown_bars)
    parser.add_argument("--fast-cooldown-bars", type=int, default=DEFAULT_PREALERT_CONFIG.fast_cooldown_bars)
    parser.add_argument("--opposite-side-cooldown-bars", type=int, default=DEFAULT_PREALERT_CONFIG.opposite_side_cooldown_bars)
    args = parser.parse_args()

    if not args.shadow:
        print("Refusing to run without --shadow. This test script is log-only.")
        return 2

    cfg = PrealertConfig(
        max_risk_pct=float(args.max_risk_pct),
        cooldown_bars=int(args.cooldown_bars),
        fast_cooldown_bars=int(args.fast_cooldown_bars),
        opposite_side_cooldown_bars=int(args.opposite_side_cooldown_bars),
    )

    client = BinanceMarketDataClient()
    last_sent_by_zone: dict[str, int] = {}
    last_sent_by_cluster: dict[str, tuple[int, str]] = {}
    last_seen_bar: int | None = None

    _append_line(args.log, f"{_now()} shadow_started symbol={args.symbol} interval_seconds={args.interval_seconds}")

    while True:
        try:
            raw_15m = client.get_klines(args.symbol, "15m", limit=300)
            raw_1h = client.get_klines(args.symbol, "1h", limit=300)
            raw_4h = client.get_klines(args.symbol, "4h", limit=180)

            # Drop active candle so the shadow test only reads closed candles.
            k15 = enrich_klines(raw_15m[:-1])
            k1h = enrich_klines(raw_1h[:-1])
            k4h = enrich_klines(raw_4h[:-1])

            decision = evaluate_15m_prealert(args.symbol, k15, k1h, k4h, cfg=cfg)
            latest_open = int(k15[-1].get("open_time", 0) or 0)
            if last_seen_bar == latest_open and not decision.get("should_alert"):
                time.sleep(max(5, int(args.interval_seconds)))
                continue
            last_seen_bar = latest_open

            if decision.get("should_alert"):
                cadence_keys = decision_cadence_keys(decision)
                zone_key = cadence_keys["same_side_zone"]
                cluster_key = cadence_keys["zone_cluster"]
                bar_id = latest_open // (15 * 60 * 1000)
                cooldown_bars = cooldown_bars_for_decision(decision, cfg)

                previous = last_sent_by_zone.get(zone_key)
                if previous is not None and bar_id - previous < cooldown_bars:
                    _append_line(args.log, f"{_now()} suppress_15m_prealert_duplicate {json.dumps(decision, ensure_ascii=False)}")
                else:
                    last_cluster = last_sent_by_cluster.get(cluster_key)
                    if last_cluster is not None:
                        last_cluster_i, last_cluster_side = last_cluster
                        is_opposite_side = last_cluster_side != str(decision["direction"])
                        strong_new_info = is_high_quality_new_information(decision, cfg)
                        if (
                            is_opposite_side
                            and bar_id - last_cluster_i < cfg.opposite_side_cooldown_bars
                            and not strong_new_info
                        ):
                            _append_line(args.log, f"{_now()} suppress_15m_prealert_contradiction {json.dumps(decision, ensure_ascii=False)}")
                            time.sleep(max(5, int(args.interval_seconds)))
                            continue

                    last_sent_by_zone[zone_key] = bar_id
                    last_sent_by_cluster[cluster_key] = (bar_id, str(decision["direction"]))
                    _append_line(args.log, f"{_now()} {format_prealert_log(decision)}")
                    _append_line(args.log, json.dumps(decision, ensure_ascii=False, sort_keys=True))
            else:
                _append_line(args.log, f"{_now()} {format_prealert_log(decision)}")

        except Exception as exc:
            _append_line(args.log, f"{_now()} shadow_error error={exc}")

        time.sleep(max(5, int(args.interval_seconds)))


if __name__ == "__main__":
    raise SystemExit(main())
