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


def label_dow_swings(
    klines: list[dict],
    *,
    left: int = 2,
    right: int = 2,
    lookback: int = 120,
) -> dict[str, Any]:
    """Label 1H fractal swings as HH/HL/LH/LL (Dow).

    Pivots reuse ``find_pivots`` (default left=right=2). First swing of each
    side is tagged ``H`` / ``L`` (seed); subsequent highs are HH or LH, lows
    HL or LL.
    """

    empty: dict[str, Any] = {
        "swing_highs": [],
        "swing_lows": [],
        "trend": "none",
        "last_hh": None,
        "last_hl": None,
        "last_lh": None,
        "last_ll": None,
    }
    if len(klines) < left + right + 3:
        return empty

    pivot_highs, pivot_lows = find_pivots(klines, left=left, right=right)
    window_start = max(0, len(klines) - lookback)
    highs = [i for i in pivot_highs if i >= window_start]
    lows = [i for i in pivot_lows if i >= window_start]

    swing_highs: list[dict[str, Any]] = []
    prev_high: float | None = None
    for idx in highs:
        price = float(klines[idx]["high"])
        if prev_high is None:
            label = "H"
        else:
            label = "HH" if price > prev_high else "LH"
        swing_highs.append({"index": idx, "price": round(price, 2), "label": label})
        prev_high = price

    swing_lows: list[dict[str, Any]] = []
    prev_low: float | None = None
    for idx in lows:
        price = float(klines[idx]["low"])
        if prev_low is None:
            label = "L"
        else:
            label = "HL" if price > prev_low else "LL"
        swing_lows.append({"index": idx, "price": round(price, 2), "label": label})
        prev_low = price

    def _last(label: str, rows: list[dict[str, Any]]) -> dict[str, Any] | None:
        for row in reversed(rows):
            if row["label"] == label:
                return row
        return None

    last_high = swing_highs[-1] if swing_highs else None
    last_low = swing_lows[-1] if swing_lows else None
    trend = "none"
    if last_high and last_low:
        if last_high["label"] == "HH" and last_low["label"] == "HL":
            trend = "up"
        elif last_high["label"] == "LH" and last_low["label"] == "LL":
            trend = "down"

    return {
        "swing_highs": swing_highs,
        "swing_lows": swing_lows,
        "trend": trend,
        "last_hh": _last("HH", swing_highs),
        "last_hl": _last("HL", swing_lows),
        "last_lh": _last("LH", swing_highs),
        "last_ll": _last("LL", swing_lows),
    }


def build_dow_structure_context(
    klines: list[dict],
    *,
    left: int = 2,
    right: int = 2,
    lookback: int = 120,
    timeframe: str = "1h",
    max_break_bars_ago: int = 2,
) -> dict[str, Any]:
    """1H Dow structure evidence for trial stack (not a hard gate alone).

    - Trend: HH+HL = up, LH+LL = down.
    - Turn evidence: 1H close breaks nearest HL → short; breaks nearest LH → long.
    - Same-way BOS (break prior HH while up / prior LL while down, HL/LH intact)
      is strengthen-only metadata — caller must not solo-formal on it.
    """

    base = label_dow_swings(klines, left=left, right=right, lookback=lookback)
    out: dict[str, Any] = {
        "approx": True,
        "timeframe": timeframe,
        **base,
        "break_hl": None,
        "break_lh": None,
        "bos_same_way": None,
        "active_short_evidence": False,
        "active_long_evidence": False,
        "reason": "insufficient_swings",
    }
    if len(klines) < left + right + 5:
        return out

    tol = _price_tolerance(klines)
    last_index = len(klines) - 1
    close = float(klines[last_index]["close"])

    # L lock: break nearest HL → short; break nearest LH → long.
    # Seed H/L are unlabeled baselines — do not treat as turn evidence.
    nearest_support = None
    for row in reversed(base["swing_lows"]):
        if row["label"] == "HL":
            nearest_support = row
            break
    nearest_resistance = None
    for row in reversed(base["swing_highs"]):
        if row["label"] == "LH":
            nearest_resistance = row
            break

    if nearest_support is not None:
        level = float(nearest_support["price"])
        bars_ago = last_index - int(nearest_support["index"])
        # Break counted on recent closes after the swing is confirmed.
        if close < level - tol and bars_ago >= right:
            # Find which bar first closed below (prefer last bar).
            trigger = last_index
            for j in range(last_index, max(int(nearest_support["index"]) + right, last_index - max_break_bars_ago) - 1, -1):
                if float(klines[j]["close"]) < level - tol:
                    trigger = j
                    break
            if last_index - trigger <= max_break_bars_ago:
                out["break_hl"] = {
                    "active": True,
                    "side": "short",
                    "level": round(level, 2),
                    "swing_index": nearest_support["index"],
                    "swing_label": nearest_support["label"],
                    "trigger_index": trigger,
                    "bars_ago": last_index - trigger,
                    "close": round(close, 2),
                }
                out["active_short_evidence"] = True

    if nearest_resistance is not None:
        level = float(nearest_resistance["price"])
        bars_ago = last_index - int(nearest_resistance["index"])
        if close > level + tol and bars_ago >= right:
            trigger = last_index
            for j in range(last_index, max(int(nearest_resistance["index"]) + right, last_index - max_break_bars_ago) - 1, -1):
                if float(klines[j]["close"]) > level + tol:
                    trigger = j
                    break
            if last_index - trigger <= max_break_bars_ago:
                out["break_lh"] = {
                    "active": True,
                    "side": "long",
                    "level": round(level, 2),
                    "swing_index": nearest_resistance["index"],
                    "swing_label": nearest_resistance["label"],
                    "trigger_index": trigger,
                    "bars_ago": last_index - trigger,
                    "close": round(close, 2),
                }
                out["active_long_evidence"] = True

    # Same-way BOS: structure intact (no opposing break), break prior extreme.
    trend = base["trend"]
    if trend == "up" and not out["active_short_evidence"] and base["last_hh"] is not None:
        hh = base["last_hh"]
        level = float(hh["price"])
        if close > level + tol and last_index - int(hh["index"]) >= right:
            out["bos_same_way"] = {
                "active": True,
                "direction": "up",
                "kind": "bos",
                "level": round(level, 2),
                "swing_index": hh["index"],
                "bars_ago": 0,
                "strengthen_only": True,
            }
    elif trend == "down" and not out["active_long_evidence"] and base["last_ll"] is not None:
        ll = base["last_ll"]
        level = float(ll["price"])
        if close < level - tol and last_index - int(ll["index"]) >= right:
            out["bos_same_way"] = {
                "active": True,
                "direction": "down",
                "kind": "bos",
                "level": round(level, 2),
                "swing_index": ll["index"],
                "bars_ago": 0,
                "strengthen_only": True,
            }

    if out["active_short_evidence"]:
        out["reason"] = "dow_break_hl"
    elif out["active_long_evidence"]:
        out["reason"] = "dow_break_lh"
    elif out["bos_same_way"]:
        out["reason"] = "dow_bos_same_way"
    elif trend == "up":
        out["reason"] = "dow_trend_up_hh_hl"
    elif trend == "down":
        out["reason"] = "dow_trend_down_lh_ll"
    else:
        out["reason"] = "dow_no_clear_trend"
    return out


def detect_small_m_top(
    klines: list[dict],
    *,
    lookback: int = 48,
    atr_mult: float = 0.35,
    supply_zone: tuple[float, float] | None = None,
    max_bars_ago: int = 4,
) -> dict[str, Any] | None:
    """Detect a compact 15m M-top / double-top with rejection.

    Two recent swing highs within tolerance (or both tapping ``supply_zone``),
    a trough between them, and a bearish rejection near the right peak.
    Used as formal-short structure evidence — never a solo alert.
    """

    if len(klines) < 12:
        return None
    window_start = max(0, len(klines) - lookback)
    pivot_highs, _ = find_pivots(klines, left=1, right=1)
    recent = [i for i in pivot_highs if i >= window_start]
    # Also allow the absolute high of the last few bars as a right peak when a
    # sharp wick rejection has not yet earned a fully confirmed pivot.
    last = len(klines) - 1
    local_high_idx = max(range(max(window_start, last - 6), last + 1), key=lambda i: float(klines[i]["high"]))
    if local_high_idx not in recent:
        recent.append(local_high_idx)
    recent = sorted(set(recent))
    if len(recent) < 2:
        return None

    tol = _price_tolerance(klines, atr_mult=atr_mult)
    supply = None
    if supply_zone is not None:
        supply = (min(float(supply_zone[0]), float(supply_zone[1])), max(float(supply_zone[0]), float(supply_zone[1])))

    best = None
    for i in range(len(recent) - 1):
        a = recent[i]
        b = recent[i + 1]
        if b - a < 2:
            continue
        if last - b > max_bars_ago:
            continue
        pa = float(klines[a]["high"])
        pb = float(klines[b]["high"])
        trough = min(float(klines[j]["low"]) for j in range(a, b + 1))
        m_high = max(pa, pb)
        if m_high - trough < tol * 0.8:
            continue  # flat, not an M
        near_equal = abs(pa - pb) <= tol * 1.25
        taps_supply = False
        if supply is not None:
            pad = tol
            right_taps = pb >= supply[0] - pad and pb <= supply[1] + pad * 3
            # Left peak may be the rising shoulder below the band; require it
            # near the right peak or also probing the supply area.
            left_near = abs(pa - pb) <= max(tol * 2.8, (supply[1] - supply[0]) * 0.75) or (
                pa >= supply[0] - pad * 2.5
            )
            taps_supply = bool(right_taps and left_near)
        if not (near_equal or taps_supply):
            continue
        right = klines[b]
        close_b = float(right["close"])
        open_b = float(right["open"])
        high_b = float(right["high"])
        low_b = float(right["low"])
        candle_range = max(high_b - low_b, 1e-9)
        upper_wick = high_b - max(open_b, close_b)
        rejected = close_b < open_b and close_b <= m_high - tol * 0.25 and upper_wick / candle_range >= 0.25
        # Also accept rejection on a later bar that failed under the M high.
        later = klines[b: last + 1]
        later_reject = any(
            float(k["close"]) < float(k["open"])
            and float(k["high"]) >= m_high - tol
            and float(k["close"]) <= m_high - tol * 0.25
            for k in later
        )
        if not (rejected or later_reject):
            continue
        candidate = {
            "active": True,
            "side": "short",
            "pattern": "small_m_top",
            "left_index": a,
            "right_index": b,
            "left_high": round(pa, 2),
            "right_high": round(pb, 2),
            "trough": round(trough, 2),
            "m_high": round(m_high, 2),
            "bars_ago": last - b,
            "near_equal": near_equal,
            "taps_supply": taps_supply,
            "supply_zone": [round(supply[0], 2), round(supply[1], 2)] if supply else None,
        }
        best = candidate
    return best


def build_structure_15m_context(
    klines_15m: list[dict],
    *,
    supply_zones: list[tuple[float, float]] | None = None,
) -> dict[str, Any]:
    """Bundle 15m M-top / supply-reject cues for formal trial evidence."""

    empty: dict[str, Any] = {
        "approx": True,
        "timeframe": "15m",
        "small_m_top": None,
        "supply_reject": False,
        "reject_high": None,
        "active": False,
        "reason": "insufficient_history",
    }
    if len(klines_15m) < 12:
        return empty
    latest = klines_15m[-1]
    high = float(latest["high"])
    close = float(latest["close"])
    open_ = float(latest["open"])
    low = float(latest["low"])
    atr = _atr_value(klines_15m)
    pad = max(atr * 0.2, abs(close) * 0.0006)

    chosen_supply = None
    supply_reject = False
    reject_high = None
    scan = klines_15m[-6:]
    for zone in supply_zones or []:
        zl, zh = min(zone), max(zone)
        for bar in scan:
            bh = float(bar["high"])
            bc = float(bar["close"])
            bo = float(bar["open"])
            if bh >= zl - pad and bc <= zl + pad and bc < bo:
                supply_reject = True
                chosen_supply = (zl, zh)
                reject_high = bh
                break
        if supply_reject:
            break
    # Fall back: strong upper-wick rejection on a recent bar.
    if not supply_reject:
        for bar in reversed(scan):
            bh = float(bar["high"])
            bc = float(bar["close"])
            bo = float(bar["open"])
            bl = float(bar["low"])
            candle_range = max(bh - bl, 1e-9)
            upper_wick = bh - max(bo, bc)
            if bc < bo and upper_wick / candle_range >= 0.35 and (bh - bc) >= atr * 0.35:
                supply_reject = True
                reject_high = bh
                break
    high = reject_high if reject_high is not None else high

    m_top = detect_small_m_top(
        klines_15m,
        supply_zone=chosen_supply,
        max_bars_ago=6,
    )
    # If supply zone known but M detector missed equal highs, retry with zone tap.
    if m_top is None and chosen_supply is not None:
        m_top = detect_small_m_top(klines_15m, supply_zone=chosen_supply, atr_mult=0.55, max_bars_ago=6)

    active = bool(m_top and m_top.get("active") and supply_reject)
    return {
        "approx": True,
        "timeframe": "15m",
        "small_m_top": m_top,
        "supply_reject": supply_reject,
        "reject_high": round(float(reject_high if reject_high is not None else high), 2) if supply_reject else None,
        "supply_zone": [round(chosen_supply[0], 2), round(chosen_supply[1], 2)] if chosen_supply else None,
        "active": active,
        "reason": "m15_supply_reject_m_top" if active else ("supply_reject_only" if supply_reject else ("m_top_only" if m_top else "no_pattern")),
    }

