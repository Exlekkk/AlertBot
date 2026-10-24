from __future__ import annotations

import argparse
import csv
import io
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.aux_filters import build_aux_filters_proxy
from engine.chart_indicators import build_chart_context
def build_ict_ob_context(_: list[dict[str, Any]]) -> dict[str, Any]:
    """ICT stack hard-deleted; empty stub for replay compatibility."""
    return {}
from engine.indicators import enrich_klines
from engine.key_zones import decide_key_zone_observation
from engine.late_filter import apply_late_filter
from engine.liquidity import build_liquidity_context
def build_msb_ob_context(_klines, _liq) -> dict[str, Any]:
    """MSB-OB stack hard-deleted; OTE comes from chart fibonacci in scanner."""
    return {"direction": "neutral"}
from engine.range_lock import build_range_lock_context
from engine.scanner import SMCTScanner
from engine.trend_matrix import build_trend_matrix_proxy
from engine.trend_segments import decide_trend_segment
from engine.volume_profile import build_volume_profile_context


def _read_csv_text(text: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in csv.DictReader(io.StringIO(text)):
        try:
            rows.append(
                {
                    "open_time": int(row["open_time"]),
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "volume": float(row["volume"]),
                    "close_time": int(row["close_time"]),
                }
            )
        except (KeyError, TypeError, ValueError):
            continue
    return rows


def load_interval(data_dir: Path, interval: str) -> list[dict[str, Any]]:
    by_open_time: dict[int, dict[str, Any]] = {}
    for path in sorted(data_dir.glob(f"BTCUSDT-{interval}-*.zip")):
        with zipfile.ZipFile(path) as archive:
            for name in archive.namelist():
                if not name.endswith(".csv"):
                    continue
                text = archive.read(name).decode("utf-8-sig")
                for row in _read_csv_text(text):
                    by_open_time[row["open_time"]] = row
    for path in sorted(data_dir.glob(f"BTCUSDT-{interval}-*.csv")):
        for row in _read_csv_text(path.read_text(encoding="utf-8-sig")):
            by_open_time[row["open_time"]] = row
    return [by_open_time[key] for key in sorted(by_open_time)]


def _parse_time(value: str, timezone: ZoneInfo, *, end_boundary: bool = False) -> int:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone)
    timestamp_ms = int(parsed.timestamp() * 1000)
    # Binance closed candles end at xx:59:59.999.  A human-supplied replay end
    # such as 23:59:59 should include that final candle instead of dropping it
    # because the parsed boundary lands 999 ms too early.
    if end_boundary and parsed.microsecond == 0:
        timestamp_ms += 999
    return timestamp_ms


def replay(
    raw_1h: list[dict[str, Any]],
    raw_4h: list[dict[str, Any]],
    start_ms: int,
    end_ms: int,
    timezone: ZoneInfo,
) -> list[dict[str, Any]]:
    scanner = SMCTScanner.__new__(SMCTScanner)
    observation_state: dict[str, Any] = {}
    trend_state: dict[str, Any] = {"direction": "neutral", "has_snapshot": False}
    output: list[dict[str, Any]] = []

    for index, raw_bar in enumerate(raw_1h):
        close_time = int(raw_bar["close_time"])
        if close_time < start_ms or close_time > end_ms:
            continue

        raw_1h_window = raw_1h[: index + 1]
        raw_4h_window = [bar for bar in raw_4h if int(bar["close_time"]) <= close_time]
        if len(raw_1h_window) < 80 or len(raw_4h_window) < 25:
            continue

        klines_1h = enrich_klines(raw_1h_window[-500:])
        klines_4h = enrich_klines(raw_4h_window[-500:])
        liq = build_liquidity_context(klines_1h)
        msb = build_msb_ob_context(klines_1h, liq)
        ict = build_ict_ob_context(klines_1h)
        chart_1h = build_chart_context(klines_1h)
        msb["fibonacci"] = chart_1h.get("fibonacci", {})
        # classic_market hard-deleted
        matrix = build_trend_matrix_proxy(klines_1h)
        vp = build_volume_profile_context(klines_1h)
        aux = build_aux_filters_proxy(klines_1h, klines_4h)
        aux["volume_orderflow"] = chart_1h.get("volume_orderflow", {})
        aux["killzone"] = chart_1h.get("killzone", {})
        fib_trend = str((chart_1h.get("fibonacci") or {}).get("trend", "neutral"))
        direction_1h = "long" if fib_trend == "bull" else "short" if fib_trend == "bear" else "neutral"
        htf = scanner._htf_context(klines_4h, direction_1h)
        try:
            range_lock = build_range_lock_context(klines_1h, htf, liq, msb, matrix, aux, vp, ict=ict)
        except TypeError:  # v1.3.8 signature
            range_lock = build_range_lock_context(klines_1h, htf, liq, msb, matrix, aux, vp)
        decision = decide_trend_segment(
            "BTCUSDT",
            "1h",
            htf,
            liq,
            msb,
            matrix,
            aux,
            trend_state=trend_state,
            vp=vp,
            ict=ict,
        )

        if not decision.get("should_alert"):
            try:
                decision = decide_key_zone_observation(
                    "BTCUSDT",
                    "1h",
                    klines_1h,
                    htf,
                    liq,
                    msb,
                    matrix,
                    aux,
                    observation_state=observation_state,
                    vp=vp,
                    range_lock=range_lock,
                    ict=ict,
                )
            except TypeError:  # v1.3.8 signature
                decision = decide_key_zone_observation(
                    "BTCUSDT",
                    "1h",
                    klines_1h,
                    htf,
                    liq,
                    msb,
                    matrix,
                    aux,
                    observation_state=observation_state,
                    vp=vp,
                    range_lock=range_lock,
                )
            if decision.get("observation_update") is not None:
                # Replay assumes successful delivery for alert rows.
                observation_state = dict(decision["observation_update"])

        decision = apply_late_filter(decision, klines_1h)
        if decision.get("should_alert") and decision.get("alert_type") in {
            "BULLISH_STRUCTURE_SHIFT",
            "BEARISH_STRUCTURE_SHIFT",
        }:
            trend_state = {"direction": decision.get("direction"), "has_snapshot": True}

        local_time = datetime.fromtimestamp(close_time / 1000.0, tz=timezone).isoformat(timespec="minutes")
        output.append(
            {
                "local_time": local_time,
                "price": round(float(decision.get("price", 0.0) or 0.0), 2),
                "alert_type": decision.get("alert_type", ""),
                "original_alert_type": decision.get("original_alert_type", ""),
                "direction": decision.get("direction", ""),
                "should_alert": bool(decision.get("should_alert", False)),
                "suppress_reason": decision.get("suppress_reason", ""),
                "market_phase": decision.get("market_phase", ""),
                "box_position": decision.get("market_box_position", range_lock.get("box_position", "")),
                "range_lock": bool(range_lock.get("active", False)),
                "range_cluster": range_lock.get("cluster", ""),
                "ict_source": ict.get("source", "none"),
                "ict_exact": bool(ict.get("is_exact", False)),
                "ict_coexist": bool(ict.get("coexist", False)),
                "ict_bull_active": bool(ict.get("bullish_active", False)),
                "ict_bear_active": bool(ict.get("bearish_active", False)),
                "ict_bull_distance_atr": ict.get("bullish_distance_atr", ""),
                "ict_bear_distance_atr": ict.get("bearish_distance_atr", ""),
                "ict_structure_event": ict.get("structure_event", ""),
                "ict_structure_event_age": ict.get("structure_event_age", ""),
                "premium_discount": ict.get("premium_discount", ""),
                "msb_direction": msb.get("direction", ""),
                "matrix_direction": matrix.get("matrix_direction", ""),
                "classical_cycle": matrix.get("classic_market", {}).get("cycle", ""),
                "fibonacci_trend": chart_1h.get("fibonacci", {}).get("trend", ""),
                "in_ote": chart_1h.get("fibonacci", {}).get("in_ote", ""),
                "vp_position": vp.get("position", ""),
                "volume_context_source": vp.get("source", ""),
                "orderflow_source": chart_1h.get("volume_orderflow", {}).get("source", ""),
                "rar_slope": round(float(aux.get("rar_slope", 0.0) or 0.0), 3),
                "inertia_slope": round(float(aux.get("inertia_slope", 0.0) or 0.0), 3),
                "price_impulse": round(float(aux.get("price_impulse", 0.0) or 0.0), 3),
                "momentum": aux.get("momentum_desc", ""),
                "trial_score": decision.get("trial_score", ""),
                "opposite_score": decision.get("trial_opposite_score", ""),
                "direction_advantage": decision.get("trial_direction_advantage", ""),
                "zone_chase_atr": decision.get("trial_zone_chase_atr", ""),
                "risk_atr": decision.get("trial_risk_atr", ""),
                "reward_risk": decision.get("trial_reward_risk", ""),
                "recent_extension_atr": decision.get("trial_recent_extension_atr", ""),
                "directional_catalyst": decision.get("trial_directional_catalyst", ""),
                "zone_source": decision.get("zone_source", ""),
                "zone_low": decision.get("zone_low", ""),
                "zone_high": decision.get("zone_high", ""),
                "invalid_level": decision.get("invalid_level", ""),
                "trial_evidence": "|".join(str(x) for x in decision.get("trial_evidence", [])),
            }
        )

    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay AlertBot 1H decisions from Binance Vision kline archives.")
    parser.add_argument("--data-dir", required=True, type=Path)
    parser.add_argument("--start", required=True, help="ISO time, interpreted in --timezone when offset is omitted")
    parser.add_argument("--end", required=True, help="ISO time, interpreted in --timezone when offset is omitted")
    parser.add_argument("--timezone", default="Asia/Singapore")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    timezone = ZoneInfo(args.timezone)
    rows = replay(
        load_interval(args.data_dir, "1h"),
        load_interval(args.data_dir, "4h"),
        _parse_time(args.start, timezone),
        _parse_time(args.end, timezone, end_boundary=True),
        timezone,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()) if rows else ["local_time"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {len(rows)} rows to {args.output}")


if __name__ == "__main__":
    main()
