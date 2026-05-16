#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Allow running from /opt/smct-alert without installing as a package.
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
    is_high_quality_new_information,
)


def _dt(ms: int) -> str:
    if not ms:
        return ""
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _filter_closed_before(klines: list[dict[str, Any]], open_time: int) -> list[dict[str, Any]]:
    return [k for k in klines if int(k.get("close_time", 0) or 0) <= open_time]


def _outcome(
    decision: dict[str, Any],
    future: list[dict[str, Any]],
    horizon_bars: int = 8,
    target_pct: float = 0.003,
) -> dict[str, Any]:
    side = str(decision.get("direction"))
    entry = float(decision.get("price", 0.0) or 0.0)
    invalid = float(decision.get("invalid_level", 0.0) or 0.0)
    window = future[:horizon_bars]
    if not window or entry <= 0:
        return {
            "mfe_30m": 0.0,
            "mfe_1h": 0.0,
            "mfe_2h": 0.0,
            "mae_2h": 0.0,
            "hit_invalid_first": False,
            "hit_target_first": False,
            "result": "no_future",
        }

    def calc_mfe_mae(bars: list[dict[str, Any]]) -> tuple[float, float]:
        if side == "short":
            mfe = max((entry - float(k["low"])) / entry for k in bars)
            mae = max((float(k["high"]) - entry) / entry for k in bars)
        else:
            mfe = max((float(k["high"]) - entry) / entry for k in bars)
            mae = max((entry - float(k["low"])) / entry for k in bars)
        return max(0.0, mfe), max(0.0, mae)

    mfe_30m, _ = calc_mfe_mae(window[:2])
    mfe_1h, _ = calc_mfe_mae(window[:4])
    mfe_2h, mae_2h = calc_mfe_mae(window[:8])

    hit_invalid_first = False
    hit_target_first = False
    result = "timeout"
    for k in window:
        if side == "short":
            invalid_hit = float(k["high"]) >= invalid
            target_hit = (entry - float(k["low"])) / entry >= target_pct
        else:
            invalid_hit = float(k["low"]) <= invalid
            target_hit = (float(k["high"]) - entry) / entry >= target_pct

        if invalid_hit and not target_hit:
            hit_invalid_first = True
            result = "fail_invalid"
            break
        if target_hit and not invalid_hit:
            hit_target_first = True
            result = "success_target"
            break
        if invalid_hit and target_hit:
            # Same 15m bar touched both; treat as ambiguous / risk-first.
            hit_invalid_first = True
            result = "ambiguous_same_bar"
            break

    if result == "timeout":
        result = "success_mfe" if mfe_1h >= target_pct else "no_followthrough"

    return {
        "mfe_30m": round(mfe_30m, 5),
        "mfe_1h": round(mfe_1h, 5),
        "mfe_2h": round(mfe_2h, 5),
        "mae_2h": round(mae_2h, 5),
        "hit_invalid_first": hit_invalid_first,
        "hit_target_first": hit_target_first,
        "result": result,
    }


def _summary(rows: list[dict[str, Any]], duplicate_skips: int, contradiction_skips: int, target_pct: float) -> str:
    lines = []
    lines.append("15m early-entry shadow backtest summary")
    lines.append("mode=shadow_only does_not_affect_1h=true")
    lines.append(f"target_pct={target_pct:.4%}")
    lines.append(f"signals={len(rows)}")
    lines.append(f"duplicate_skips={duplicate_skips}")
    lines.append(f"contradiction_skips={contradiction_skips}")

    if not rows:
        lines.append("No signals found under current filters.")
        lines.append("")
        lines.append("Interpretation guide:")
        lines.append("- 15m is only an entry-location reminder; 1H remains the official alert body.")
        lines.append("- If no signals appear, check whether 1H context gates are too strict.")
        return "\n".join(lines) + "\n"

    for side in ("long", "short"):
        subset = [r for r in rows if r["direction"] == side]
        if not subset:
            lines.append(f"{side}: 0")
            continue
        wins = [r for r in subset if str(r["result"]).startswith("success")]
        fails = [r for r in subset if str(r["result"]) in {"fail_invalid", "ambiguous_same_bar"}]
        avg_mfe_1h = sum(float(r["mfe_1h"]) for r in subset) / len(subset)
        avg_mfe_2h = sum(float(r["mfe_2h"]) for r in subset) / len(subset)
        avg_mae_2h = sum(float(r["mae_2h"]) for r in subset) / len(subset)
        avg_lead = sum(float(r["lead_to_1h_close_min"]) for r in subset) / len(subset)
        lines.append(
            f"{side}: total={len(subset)} win={len(wins)} fail={len(fails)} "
            f"win_rate={len(wins)/len(subset):.1%} avg_lead={avg_lead:.1f}m "
            f"avg_mfe_1h={avg_mfe_1h:.3%} avg_mfe_2h={avg_mfe_2h:.3%} "
            f"avg_mae_2h={avg_mae_2h:.3%}"
        )

    active_days = max(1.0, len({str(r["trigger_time"])[:10] for r in rows}))
    per_day = len(rows) / active_days
    lines.append(f"approx_signals_per_active_day={per_day:.2f}")

    setup_counts: dict[str, int] = {}
    for r in rows:
        key = str(r.get("setup_type") or r.get("reaction_type") or "unknown")
        setup_counts[key] = setup_counts.get(key, 0) + 1
    lines.append("setup_counts=" + ", ".join(f"{k}:{v}" for k, v in sorted(setup_counts.items())))

    lines.append("")
    lines.append("Interpretation guide:")
    lines.append("- 15m should provide earlier entry-location reminders, not rewrite 1H logic.")
    lines.append("- Healthy first pass: both long/short can appear, win_rate preferably >=55%.")
    lines.append("- 1-4 signals/day is a baseline reference, not a hard cap.")
    lines.append("- Active/high-volatility days may produce more valid reminders if each has new structure information.")
    lines.append("- Reject versions that rely on single FVG / single TAI / single zone-touch triggers.")
    lines.append("- Review duplicate_skips and contradiction_skips to check noise control, not a fixed daily limit.")
    lines.append("- Compare lead_to_1h_close_min with TradingView to confirm it is early enough.")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Shadow backtest BTC 15m prealerts without Telegram or orders.")
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--out", default="reports/15m_prealert_backtest.csv")
    parser.add_argument("--summary", default="reports/15m_prealert_summary.txt")
    parser.add_argument("--target-pct", type=float, default=0.003, help="Target move used for success evaluation, default 0.003 = 0.30%%")
    parser.add_argument("--max-risk-pct", type=float, default=DEFAULT_PREALERT_CONFIG.max_risk_pct)
    parser.add_argument("--cooldown-bars", type=int, default=DEFAULT_PREALERT_CONFIG.cooldown_bars)
    parser.add_argument("--fast-cooldown-bars", type=int, default=DEFAULT_PREALERT_CONFIG.fast_cooldown_bars)
    parser.add_argument("--opposite-side-cooldown-bars", type=int, default=DEFAULT_PREALERT_CONFIG.opposite_side_cooldown_bars)
    args = parser.parse_args()

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    os.makedirs(os.path.dirname(args.summary) or ".", exist_ok=True)

    client = BinanceMarketDataClient()
    limit_15m = min(1000, max(220, args.days * 96 + 120))
    limit_1h = min(1000, max(220, args.days * 24 + 180))
    limit_4h = min(1000, max(120, args.days * 6 + 100))

    raw_15m = client.get_klines(args.symbol, "15m", limit=limit_15m)
    raw_1h = client.get_klines(args.symbol, "1h", limit=limit_1h)
    raw_4h = client.get_klines(args.symbol, "4h", limit=limit_4h)

    klines_15m = enrich_klines(raw_15m[:-1])
    klines_1h = enrich_klines(raw_1h[:-1])
    klines_4h = enrich_klines(raw_4h[:-1])

    cfg = PrealertConfig(
        max_risk_pct=float(args.max_risk_pct),
        cooldown_bars=int(args.cooldown_bars),
        fast_cooldown_bars=int(args.fast_cooldown_bars),
        opposite_side_cooldown_bars=int(args.opposite_side_cooldown_bars),
    )

    rows: list[dict[str, Any]] = []
    last_sent_by_zone: dict[str, int] = {}
    last_sent_by_cluster: dict[str, tuple[int, str]] = {}
    duplicate_skips = 0
    contradiction_skips = 0

    warmup = max(cfg.min_klines_15m, 80)
    for i in range(warmup, len(klines_15m) - 8):
        current = klines_15m[i]
        current_open = int(current["open_time"])
        h1_subset = _filter_closed_before(klines_1h, current_open)
        h4_subset = _filter_closed_before(klines_4h, current_open)
        if len(h1_subset) < cfg.min_klines_1h or len(h4_subset) < 20:
            continue

        decision = evaluate_15m_prealert(
            args.symbol,
            klines_15m[: i + 1],
            h1_subset,
            h4_subset,
            cfg=cfg,
        )
        if not decision.get("should_alert"):
            continue

        cadence_keys = decision_cadence_keys(decision)
        zone_key = cadence_keys["same_side_zone"]
        cluster_key = cadence_keys["zone_cluster"]
        cooldown_bars = cooldown_bars_for_decision(decision, cfg)

        last_i = last_sent_by_zone.get(zone_key)
        if last_i is not None and i - last_i < cooldown_bars:
            duplicate_skips += 1
            continue

        last_cluster = last_sent_by_cluster.get(cluster_key)
        if last_cluster is not None:
            last_cluster_i, last_cluster_side = last_cluster
            is_opposite_side = last_cluster_side != str(decision["direction"])
            strong_new_info = is_high_quality_new_information(decision, cfg)
            if (
                is_opposite_side
                and i - last_cluster_i < cfg.opposite_side_cooldown_bars
                and not strong_new_info
            ):
                contradiction_skips += 1
                continue

        last_sent_by_zone[zone_key] = i
        last_sent_by_cluster[cluster_key] = (i, str(decision["direction"]))

        outcome = _outcome(decision, klines_15m[i + 1 :], target_pct=float(args.target_pct))
        lead_to_1h_close_min = 60 - ((current_open // 60000) % 60)
        row = {
            "trigger_time": _dt(current_open),
            "direction": decision["direction"],
            "title": decision["title"],
            "price": decision["price"],
            "zone_low": decision["zone_low"],
            "zone_high": decision["zone_high"],
            "invalid_level": decision["invalid_level"],
            "zone_source": decision["zone_source"],
            "zone_cluster_hash": decision.get("zone_cluster_hash", ""),
            "cadence_mode": decision.get("cadence_mode", ""),
            "recommended_cooldown_bars": decision.get("recommended_cooldown_bars", ""),
            "htf_context": decision["htf_context"],
            "momentum_desc": decision["momentum_desc"],
            "temperature_desc": decision["temperature_desc"],
            "lead_to_1h_close_min": int(lead_to_1h_close_min),
            "setup_type": decision.get("setup_type", ""),
            "liquidity_event": decision.get("liquidity_event", ""),
            "structure_context": decision.get("structure_context", ""),
            "poi_type": decision.get("poi_type", decision.get("zone_source", "")),
            "key_level_context": decision.get("key_level_context", ""),
            "reaction_type": decision.get("reaction_type", ""),
            "momentum_filter": decision.get("momentum_filter", decision.get("momentum_desc", "")),
            "tai_regime": decision.get("tai_regime", ""),
            "early_entry_reason": decision.get("early_entry_reason", ""),
            "trigger_score": decision.get("trigger_score", decision.get("score", "")),
            "reject_reason": decision.get("reject_reason", ""),
            "risk_pct": decision.get("risk_pct", ""),
            "room_pct": decision.get("room_pct", ""),
            "reaction_score": decision.get("reaction_score", ""),
            "zone_width_pct": decision.get("zone_width_pct", ""),
            "zone_position": decision.get("zone_position", ""),
            "rar_now": decision.get("rar_now", ""),
            "rar_trigger": decision.get("rar_trigger", ""),
            "price_impulse": decision.get("price_impulse", ""),
            "volume_ratio": decision.get("volume_ratio", ""),
            **outcome,
        }
        rows.append(row)

    fieldnames = [
        "trigger_time",
        "direction",
        "title",
        "price",
        "zone_low",
        "zone_high",
        "invalid_level",
        "zone_source",
        "zone_cluster_hash",
        "cadence_mode",
        "recommended_cooldown_bars",
        "htf_context",
        "momentum_desc",
        "temperature_desc",
        "lead_to_1h_close_min",
        "setup_type",
        "liquidity_event",
        "structure_context",
        "poi_type",
        "key_level_context",
        "reaction_type",
        "momentum_filter",
        "tai_regime",
        "early_entry_reason",
        "trigger_score",
        "reject_reason",
        "risk_pct",
        "room_pct",
        "reaction_score",
        "zone_width_pct",
        "zone_position",
        "rar_now",
        "rar_trigger",
        "price_impulse",
        "volume_ratio",
        "mfe_30m",
        "mfe_1h",
        "mfe_2h",
        "mae_2h",
        "hit_invalid_first",
        "hit_target_first",
        "result",
    ]
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    summary_text = _summary(rows, duplicate_skips=duplicate_skips, contradiction_skips=contradiction_skips, target_pct=float(args.target_pct))
    Path(args.summary).write_text(summary_text, encoding="utf-8")
    print(summary_text)
    print(f"csv={args.out}")
    print(f"summary={args.summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
