from collections import Counter

from engine.structure import (
    detect_last_bos,
    detect_last_mss,
    find_pivots,
    higher_highs_lows,
    is_bearish_fvg,
    is_bullish_fvg,
    lower_highs_lows,
)


SIGNAL_PRIORITY = {
    "A_LONG": 1,
    "A_SHORT": 1,
    "B_PULLBACK_LONG": 2,
    "B_PULLBACK_SHORT": 2,
    "C_LEFT_LONG": 3,
    "C_LEFT_SHORT": 3,
}


def classify_4h_trend(klines_4h: list[dict]) -> str:
    pivot_highs, pivot_lows = find_pivots(klines_4h)
    bos = detect_last_bos(klines_4h, pivot_highs, pivot_lows)
    k = klines_4h[-1]

    bull_score = sum(
        [
            k["close"] > k["ema120"],
            k["ema10"] > k["ema20"],
            k["ema20"] > k["ema120"],
            bos == "up",
        ]
    )
    bear_score = sum(
        [
            k["close"] < k["ema120"],
            k["ema10"] < k["ema20"],
            k["ema20"] < k["ema120"],
            bos == "down",
        ]
    )
    if bull_score >= 2:
        return "bull"
    if bear_score >= 2:
        return "bear"
    return "neutral"


def classify_1h_trend(klines_1h: list[dict]) -> str:
    pivot_highs, pivot_lows = find_pivots(klines_1h)
    bos = detect_last_bos(klines_1h, pivot_highs, pivot_lows)
    mss = detect_last_mss(klines_1h, pivot_highs, pivot_lows)
    k = klines_1h[-1]

    bull_score = sum(
        [
            k["close"] > k["ema20"],
            k["ema10"] > k["ema20"],
            k["ema20"] > k["ema120"],
            (bos == "up" or mss == "up"),
            higher_highs_lows(klines_1h, 10),
        ]
    )
    bear_score = sum(
        [
            k["close"] < k["ema20"],
            k["ema10"] < k["ema20"],
            k["ema20"] < k["ema120"],
            (bos == "down" or mss == "down"),
            lower_highs_lows(klines_1h, 10),
        ]
    )

    if bull_score >= 3:
        return "bull"
    if bear_score >= 3:
        return "bear"
    if bull_score > bear_score:
        return "lean_bull"
    if bear_score > bull_score:
        return "lean_bear"
    return "neutral"


def _volume_expanded(last_two_15m: list[dict]) -> bool:
    return any(k["volume"] > k["vol_sma20"] * 1.3 for k in last_two_15m)


def _sideways_filter(klines_15m: list[dict]) -> bool:
    recent = klines_15m[-12:]
    if len(recent) < 12:
        return False
    highs = max(k["high"] for k in recent)
    lows = min(k["low"] for k in recent)
    range_pct = (highs - lows) / max(lows, 1e-9)
    ema_tight = abs(recent[-1]["ema10"] - recent[-1]["ema20"]) < recent[-1]["atr"] * 0.15
    weak_volume = sum(k["volume"] < k["vol_sma20"] * 0.9 for k in recent) >= 8
    return range_pct < 0.01 and ema_tight and weak_volume


def _hard_sideways_filter(klines_15m: list[dict]) -> bool:
    recent = klines_15m[-12:]
    if len(recent) < 12:
        return False
    highs = max(k["high"] for k in recent)
    lows = min(k["low"] for k in recent)
    range_pct = (highs - lows) / max(lows, 1e-9)
    ema_tight = abs(recent[-1]["ema10"] - recent[-1]["ema20"]) < recent[-1]["atr"] * 0.08
    weak_volume = sum(k["volume"] < k["vol_sma20"] * 0.85 for k in recent) >= 10
    return range_pct < 0.006 and ema_tight and weak_volume


def _is_strictly_monotonic(values: list[float], direction: str) -> bool:
    if len(values) < 2:
        return False
    if direction == "up":
        return all(values[i] < values[i + 1] for i in range(len(values) - 1))
    return all(values[i] > values[i + 1] for i in range(len(values) - 1))


def _is_soft_monotonic(values: list[float], direction: str, min_progress_steps: int) -> bool:
    if len(values) < 2:
        return False

    progresses = 0
    for i in range(len(values) - 1):
        if direction == "up" and values[i + 1] > values[i]:
            progresses += 1
        if direction == "down" and values[i + 1] < values[i]:
            progresses += 1
    return progresses >= min_progress_steps


def _pick_best_per_direction(signals: list[dict]) -> list[dict]:
    best_by_direction = {}
    for signal in signals:
        direction = signal["direction"]
        previous = best_by_direction.get(direction)
        if not previous or signal["priority"] < previous["priority"]:
            best_by_direction[direction] = signal
    return sorted(best_by_direction.values(), key=lambda s: s["priority"])


def _evaluate_branch(name: str, checks: dict[str, bool], near_miss_signals: list[dict], blocked_counter: Counter):
    failed = [check_name for check_name, ok in checks.items() if not ok]
    if not failed:
        return True

    detail = {"candidate": name, "failed_checks": failed}
    if len(failed) <= 2:
        near_miss_signals.append(detail)
    else:
        for reason in failed:
            blocked_counter[f"{name}:{reason}"] += 1
    return False


def detect_signals(symbol: str, klines_4h: list[dict], klines_1h: list[dict], klines_15m: list[dict]) -> dict:
    trend_4h = classify_4h_trend(klines_4h)
    trend_1h = classify_1h_trend(klines_1h)
    latest_4h = klines_4h[-1]
    latest_1h = klines_1h[-1]
    piv_h, piv_l = find_pivots(klines_15m)
    bos_15 = detect_last_bos(klines_15m, piv_h, piv_l)
    mss_15 = detect_last_mss(klines_15m, piv_h, piv_l)
    latest = klines_15m[-1]
    last2 = klines_15m[-2:]
    atr = latest["atr"]
    sideways = _sideways_filter(klines_15m)
    hard_sideways = _hard_sideways_filter(klines_15m)

    bullish_structure = bos_15 == "up" or mss_15 == "up"
    bearish_structure = bos_15 == "down" or mss_15 == "down"
    vol_ok = _volume_expanded(last2)

    near_resistance = piv_h and abs(klines_15m[piv_h[-1]]["high"] - latest["close"]) < atr * 0.3
    near_support = piv_l and abs(latest["close"] - klines_15m[piv_l[-1]]["low"]) < atr * 0.3

    a_near_resistance = piv_h and abs(klines_15m[piv_h[-1]]["high"] - latest["close"]) < atr * 0.5
    a_near_support = piv_l and abs(latest["close"] - klines_15m[piv_l[-1]]["low"]) < atr * 0.5
    a_long_not_overextended = (latest["close"] - latest["ema20"]) <= atr * 2.0
    a_short_not_overextended = (latest["ema20"] - latest["close"]) <= atr * 2.0

    recent = klines_15m[-6:]
    a_late_long_extension = (
        len(recent) >= 6
        and (recent[-1]["close"] - recent[0]["close"]) > atr * 2.4
        and (max(k["high"] for k in recent[-3:]) - min(k["low"] for k in recent[-3:])) < atr * 0.9
    )
    a_late_short_extension = (
        len(recent) >= 6
        and (recent[0]["close"] - recent[-1]["close"]) > atr * 2.4
        and (max(k["high"] for k in recent[-3:]) - min(k["low"] for k in recent[-3:])) < atr * 0.9
    )

    trend_1h_soft_bull = trend_1h in ("bull", "lean_bull", "neutral") or (
        latest_1h["ema10"] > latest_1h["ema20"] or latest_1h["close"] > latest_1h["ema20"]
    )
    trend_1h_soft_bear = trend_1h in ("bear", "lean_bear", "neutral") or (
        latest_1h["ema10"] < latest_1h["ema20"] or latest_1h["close"] < latest_1h["ema20"]
    )


    strong_4h_bear = (
        trend_4h == "bear"
        and latest_4h["close"] < latest_4h["ema120"]
        and latest_4h["ema10"] < latest_4h["ema20"]
        and latest_4h["ema20"] < latest_4h["ema120"]
    )
    strong_4h_bull = (
        trend_4h == "bull"
        and latest_4h["close"] > latest_4h["ema120"]
        and latest_4h["ema10"] > latest_4h["ema20"]
        and latest_4h["ema20"] > latest_4h["ema120"]
    )

    signals = []
    near_miss_signals = []
    blocked_counter: Counter = Counter()

    a_long_checks = {
        "trend_4h_not_bear": trend_4h != "bear",
        "trend_1h_bull": trend_1h == "bull",
        "bullish_structure": bullish_structure,
        "volume_expanded": vol_ok,
        "breakout_or_gap": bos_15 == "up" or is_bullish_fvg(klines_15m[-10:]),
        "not_near_resistance": not near_resistance,
        "a_not_too_close_high": not a_near_resistance,
        "a_not_overextended_from_ema20": a_long_not_overextended,
        "a_not_late_extension": not a_late_long_extension,
        "not_sideways": not sideways,
    }
    if _evaluate_branch("A_LONG", a_long_checks, near_miss_signals, blocked_counter):
        signals.append(
            {
                "signal": "A_LONG",
                "symbol": symbol,
                "timeframe": "15m",
                "priority": SIGNAL_PRIORITY["A_LONG"],
                "direction": "long",
                "price": latest["close"],
                "trend_1h": trend_1h,
                "status": "active",
            }
        )

    a_short_checks = {
        "trend_4h_not_bull": trend_4h != "bull",
        "trend_1h_bear": trend_1h == "bear",
        "bearish_structure": bearish_structure,
        "volume_expanded": vol_ok,
        "breakdown_or_gap": bos_15 == "down" or is_bearish_fvg(klines_15m[-10:]),
        "not_near_support": not near_support,
        "a_not_too_close_low": not a_near_support,
        "a_not_overextended_from_ema20": a_short_not_overextended,
        "a_not_late_extension": not a_late_short_extension,
        "not_sideways": not sideways,
    }
    if _evaluate_branch("A_SHORT", a_short_checks, near_miss_signals, blocked_counter):
        signals.append(
            {
                "signal": "A_SHORT",
                "symbol": symbol,
                "timeframe": "15m",
                "priority": SIGNAL_PRIORITY["A_SHORT"],
                "direction": "short",
                "price": latest["close"],
                "trend_1h": trend_1h,
                "status": "active",
            }
        )

    b_long_checks = {
        "trend_4h_not_strong_bear": not strong_4h_bear,
        "trend_1h_supportive": trend_1h_soft_bull,
        "volume_ok_relaxed": latest["volume"] >= latest["vol_sma20"] * 0.5,
        "close_above_ema20": latest["close"] > latest["ema20"],
        "not_bearish_structure": not bearish_structure,
        "not_hard_sideways": not hard_sideways,
    }
    if _evaluate_branch("B_PULLBACK_LONG", b_long_checks, near_miss_signals, blocked_counter):
        signals.append(
            {
                "signal": "B_PULLBACK_LONG",
                "symbol": symbol,
                "timeframe": "15m",
                "priority": SIGNAL_PRIORITY["B_PULLBACK_LONG"],
                "direction": "long",
                "price": latest["close"],
                "trend_1h": trend_1h,
                "status": "active",
            }
        )

    b_short_checks = {
        "trend_4h_not_strong_bull": not strong_4h_bull,
        "trend_1h_supportive": trend_1h_soft_bear,
        "volume_ok_relaxed": latest["volume"] >= latest["vol_sma20"] * 0.5,
        "close_below_ema20": latest["close"] < latest["ema20"],
        "not_bullish_structure": not bullish_structure,
        "not_hard_sideways": not hard_sideways,
    }
    if _evaluate_branch("B_PULLBACK_SHORT", b_short_checks, near_miss_signals, blocked_counter):
        signals.append(
            {
                "signal": "B_PULLBACK_SHORT",
                "symbol": symbol,
                "timeframe": "15m",
                "priority": SIGNAL_PRIORITY["B_PULLBACK_SHORT"],
                "direction": "short",
                "price": latest["close"],
                "trend_1h": trend_1h,
                "status": "active",
            }
        )

    macd_seq = [k["macd_hist"] for k in klines_15m[-8:]]
    c_long_checks = {
        "left_warning_up": (
            (len(macd_seq) >= 4 and _is_strictly_monotonic(macd_seq[-4:], "up"))
            or (len(macd_seq) >= 5 and _is_soft_monotonic(macd_seq[-5:], "up", min_progress_steps=3))
        ),
        "mostly_below_zero": len(macd_seq) >= 4 and sum(v <= 0 for v in macd_seq[-4:]) >= 3,
    }
    if _evaluate_branch("C_LEFT_LONG", c_long_checks, near_miss_signals, blocked_counter):
        signals.append(
            {
                "signal": "C_LEFT_LONG",
                "symbol": symbol,
                "timeframe": "15m",
                "priority": SIGNAL_PRIORITY["C_LEFT_LONG"],
                "direction": "long",
                "price": latest["close"],
                "trend_1h": trend_1h,
                "status": "early",
            }
        )

    c_short_checks = {
        "left_warning_down": (
            (len(macd_seq) >= 4 and _is_strictly_monotonic(macd_seq[-4:], "down"))
            or (len(macd_seq) >= 5 and _is_soft_monotonic(macd_seq[-5:], "down", min_progress_steps=3))
        ),
        "mostly_above_zero": len(macd_seq) >= 4 and sum(v >= 0 for v in macd_seq[-4:]) >= 3,
    }
    if _evaluate_branch("C_LEFT_SHORT", c_short_checks, near_miss_signals, blocked_counter):
        signals.append(
            {
                "signal": "C_LEFT_SHORT",
                "symbol": symbol,
                "timeframe": "15m",
                "priority": SIGNAL_PRIORITY["C_LEFT_SHORT"],
                "direction": "short",
                "price": latest["close"],
                "trend_1h": trend_1h,
                "status": "early",
            }
        )

    return {
        "signals": _pick_best_per_direction(signals),
        "near_miss_signals": near_miss_signals,
        "blocked_reasons": dict(blocked_counter),
    }
