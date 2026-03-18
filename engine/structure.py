from __future__ import annotations

from typing import Any


def _last_close(klines: list[dict]) -> float:
    return float(klines[-1]["close"])


def _fallback_atr(klines: list[dict], period: int = 14) -> float:
    if not klines:
        return 0.0
    sample = klines[-period:]
    ranges = [abs(float(k["high"]) - float(k["low"])) for k in sample]
    if not ranges:
        return abs(_last_close(klines)) * 0.002
    return sum(ranges) / len(ranges)


def _atr_value(klines: list[dict]) -> float:
    latest = klines[-1]
    value = float(latest.get("atr", 0.0) or 0.0)
    if value > 0:
        return value
    return _fallback_atr(klines)


def _price_tolerance(klines: list[dict], atr_mult: float = 0.18) -> float:
    atr = _atr_value(klines)
    close = max(abs(_last_close(klines)), 1.0)
    return max(atr * atr_mult, close * 0.0006)


def find_pivots(klines: list[dict], left: int = 2, right: int = 2) -> tuple[list[int], list[int]]:
    pivot_highs: list[int] = []
    pivot_lows: list[int] = []
    if len(klines) < left + right + 1:
        return pivot_highs, pivot_lows

    for i in range(left, len(klines) - right):
        high = float(klines[i]["high"])
        low = float(klines[i]["low"])

        if all(high > float(klines[j]["high"]) for j in range(i - left, i)) and all(
            high >= float(klines[j]["high"]) for j in range(i + 1, i + right + 1)
        ):
            pivot_highs.append(i)

        if all(low < float(klines[j]["low"]) for j in range(i - left, i)) and all(
            low <= float(klines[j]["low"]) for j in range(i + 1, i + right + 1)
        ):
            pivot_lows.append(i)

    return pivot_highs, pivot_lows


def detect_structure_events(
    klines: list[dict],
    left: int = 2,
    right: int = 2,
    lookback: int = 120,
) -> list[dict[str, Any]]:
    if len(klines) < 10:
        return []

    pivot_highs, pivot_lows = find_pivots(klines, left=left, right=right)
    broken_highs: set[int] = set()
    broken_lows: set[int] = set()
    events: list[dict[str, Any]] = []
    bias = 0
    tol = _price_tolerance(klines)
    start = max(left + right + 1, len(klines) - lookback)

    for bar_index in range(start, len(klines)):
        close = float(klines[bar_index]["close"])

        high_candidates = [idx for idx in pivot_highs if idx <= bar_index - right and idx not in broken_highs]
        low_candidates = [idx for idx in pivot_lows if idx <= bar_index - right and idx not in broken_lows]

        if high_candidates:
            pivot_idx = high_candidates[-1]
            level = float(klines[pivot_idx]["high"])
            if close > level + tol:
                kind = "mss" if bias == -1 else "bos"
                events.append(
                    {
                        "kind": kind,
                        "direction": "up",
                        "pivot_index": pivot_idx,
                        "trigger_index": bar_index,
                        "level": level,
                    }
                )
                bias = 1
                broken_highs.add(pivot_idx)

        if low_candidates:
            pivot_idx = low_candidates[-1]
            level = float(klines[pivot_idx]["low"])
            if close < level - tol:
                kind = "mss" if bias == 1 else "bos"
                events.append(
                    {
                        "kind": kind,
                        "direction": "down",
                        "pivot_index": pivot_idx,
                        "trigger_index": bar_index,
                        "level": level,
                    }
                )
                bias = -1
                broken_lows.add(pivot_idx)

    return events


def detect_last_bos(klines: list[dict], pivot_highs: list[int] | None = None, pivot_lows: list[int] | None = None) -> str:
    events = detect_structure_events(klines)
    for event in reversed(events):
        if event["kind"] == "bos":
            return "up" if event["direction"] == "up" else "down"
    return "none"


def detect_last_mss(klines: list[dict], pivot_highs: list[int] | None = None, pivot_lows: list[int] | None = None) -> str:
    events = detect_structure_events(klines)
    for event in reversed(events):
        if event["kind"] == "mss":
            return "up" if event["direction"] == "up" else "down"
    return "none"


def latest_structure_event(
    klines: list[dict],
    direction: str | None = None,
    kinds: tuple[str, ...] | None = None,
    max_bars_ago: int | None = None,
) -> dict[str, Any] | None:
    events = detect_structure_events(klines)
    if not events:
        return None

    last_index = len(klines) - 1
    for event in reversed(events):
        if direction and event["direction"] != direction:
            continue
        if kinds and event["kind"] not in kinds:
            continue
        if max_bars_ago is not None and last_index - int(event["trigger_index"]) > max_bars_ago:
            continue
        return event
    return None


def higher_highs_lows(klines: list[dict], length: int = 10) -> bool:
    if len(klines) < length:
        return False
    segment = klines[-length:]
    return float(segment[-1]["high"]) > float(segment[0]["high"]) and float(segment[-1]["low"]) > float(segment[0]["low"])


def lower_highs_lows(klines: list[dict], length: int = 10) -> bool:
    if len(klines) < length:
        return False
    segment = klines[-length:]
    return float(segment[-1]["high"]) < float(segment[0]["high"]) and float(segment[-1]["low"]) < float(segment[0]["low"])


def is_bullish_fvg(klines: list[dict]) -> bool:
    if len(klines) < 3:
        return False
    a, _, c = klines[-3], klines[-2], klines[-1]
    tol = _price_tolerance(klines, atr_mult=0.05)
    return float(c["low"]) > float(a["high"]) + tol


def is_bearish_fvg(klines: list[dict]) -> bool:
    if len(klines) < 3:
        return False
    a, _, c = klines[-3], klines[-2], klines[-1]
    tol = _price_tolerance(klines, atr_mult=0.05)
    return float(c["high"]) < float(a["low"]) - tol


def detect_recent_equal_levels(
    klines: list[dict],
    lookback: int = 80,
    atr_mult: float = 0.18,
) -> dict[str, dict[str, Any] | None]:
    pivot_highs, pivot_lows = find_pivots(klines)
    tol = _price_tolerance(klines, atr_mult=atr_mult)
    last_index = len(klines) - 1

    eqh = None
    eql = None

    recent_highs = [idx for idx in pivot_highs if idx >= max(0, len(klines) - lookback)]
    for i in range(1, len(recent_highs)):
        a = recent_highs[i - 1]
        b = recent_highs[i]
        pa = float(klines[a]["high"])
        pb = float(klines[b]["high"])
        if abs(pa - pb) <= tol:
            eqh = {
                "active": True,
                "price": round((pa + pb) / 2.0, 2),
                "first_index": a,
                "second_index": b,
                "bars_ago": last_index - b,
            }

    recent_lows = [idx for idx in pivot_lows if idx >= max(0, len(klines) - lookback)]
    for i in range(1, len(recent_lows)):
        a = recent_lows[i - 1]
        b = recent_lows[i]
        pa = float(klines[a]["low"])
        pb = float(klines[b]["low"])
        if abs(pa - pb) <= tol:
            eql = {
                "active": True,
                "price": round((pa + pb) / 2.0, 2),
                "first_index": a,
                "second_index": b,
                "bars_ago": last_index - b,
            }

    return {"eqh": eqh, "eql": eql}


def detect_recent_fvg_fill(
    klines: list[dict],
    direction: str,
    create_lookback: int = 90,
    retest_lookback: int = 16,
) -> dict[str, Any] | None:
    if len(klines) < 8:
        return None

    tol = _price_tolerance(klines, atr_mult=0.05)
    start = max(2, len(klines) - create_lookback)
    zones: list[dict[str, Any]] = []

    for i in range(start, len(klines)):
        a = klines[i - 2]
        c = klines[i]
        if direction == "bull":
            if float(c["low"]) > float(a["high"]) + tol:
                zones.append(
                    {
                        "direction": "bull",
                        "created_index": i,
                        "zone_low": float(a["high"]),
                        "zone_high": float(c["low"]),
                    }
                )
        else:
            if float(c["high"]) < float(a["low"]) - tol:
                zones.append(
                    {
                        "direction": "bear",
                        "created_index": i,
                        "zone_low": float(c["high"]),
                        "zone_high": float(a["low"]),
                    }
                )

    if not zones:
        return None

    end_index = len(klines) - 1
    for zone in reversed(zones):
        fill_index = None
        for j in range(zone["created_index"] + 1, len(klines)):
            low = float(klines[j]["low"])
            high = float(klines[j]["high"])
            if low <= zone["zone_high"] + tol and high >= zone["zone_low"] - tol:
                fill_index = j
                break
        if fill_index is None:
            continue
        if end_index - fill_index > retest_lookback:
            continue
        return {
            "active": True,
            "direction": direction,
            "created_index": zone["created_index"],
            "fill_index": fill_index,
            "zone_low": round(zone["zone_low"], 2),
            "zone_high": round(zone["zone_high"], 2),
            "bars_ago": end_index - fill_index,
        }
    return None


def detect_recent_liquidity_sweep(
    klines: list[dict],
    direction: str,
    lookback: int = 16,
) -> dict[str, Any] | None:
    if len(klines) < lookback + 3:
        return None

    tol = _price_tolerance(klines, atr_mult=0.08)
    latest = klines[-1]
    prev = klines[-2]
    recent = klines[-(lookback + 2):-2]
    if not recent:
        return None

    if direction == "bull":
        ref = min(float(k["low"]) for k in recent)
        prev_swept = float(prev["low"]) < ref - tol and float(prev["close"]) > ref - tol and float(latest["close"]) >= float(prev["close"])
        latest_swept = float(latest["low"]) < ref - tol and float(latest["close"]) > ref + tol
        if prev_swept or latest_swept:
            return {
                "active": True,
                "direction": direction,
                "level": round(ref, 2),
                "bars_ago": 1 if prev_swept else 0,
            }
    else:
        ref = max(float(k["high"]) for k in recent)
        prev_swept = float(prev["high"]) > ref + tol and float(prev["close"]) < ref + tol and float(latest["close"]) <= float(prev["close"])
        latest_swept = float(latest["high"]) > ref + tol and float(latest["close"]) < ref - tol
        if prev_swept or latest_swept:
            return {
                "active": True,
                "direction": direction,
                "level": round(ref, 2),
                "bars_ago": 1 if prev_swept else 0,
            }
    return None


def detect_near_pivot_level(
    klines: list[dict],
    direction: str,
    lookback: int = 20,
) -> dict[str, Any] | None:
    pivot_highs, pivot_lows = find_pivots(klines)
    tol = _price_tolerance(klines, atr_mult=0.25)
    latest = klines[-1]
    if direction == "bull":
        recent = [idx for idx in pivot_lows if idx >= max(0, len(klines) - lookback)]
        if not recent:
            return None
        idx = recent[-1]
        price = float(klines[idx]["low"])
        if abs(float(latest["close"]) - price) <= tol * 2.0:
            return {"active": True, "price": round(price, 2), "index": idx}
    else:
        recent = [idx for idx in pivot_highs if idx >= max(0, len(klines) - lookback)]
        if not recent:
            return None
        idx = recent[-1]
        price = float(klines[idx]["high"])
        if abs(float(latest["close"]) - price) <= tol * 2.0:
            return {"active": True, "price": round(price, 2), "index": idx}
    return None
