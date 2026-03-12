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


def _is_bullish_label(label: str) -> bool:
    return label in ("bull", "lean_bull")


def _is_bearish_label(label: str) -> bool:
    return label in ("bear", "lean_bear")


def classify_trend(klines: list[dict], structure_len: int = 10) -> str:
    pivot_highs, pivot_lows = find_pivots(klines)
    bos = detect_last_bos(klines, pivot_highs, pivot_lows)
    mss = detect_last_mss(klines, pivot_highs, pivot_lows)
    k = klines[-1]

    bull_score = sum(
        [
            k["close"] > k["ema20"],
            k["ema10"] > k["ema20"],
            k["ema20"] > k["ema120"],
            bos == "up" or mss == "up",
            higher_highs_lows(klines, structure_len),
        ]
    )
    bear_score = sum(
        [
            k["close"] < k["ema20"],
            k["ema10"] < k["ema20"],
            k["ema20"] < k["ema120"],
            bos == "down" or mss == "down",
            lower_highs_lows(klines, structure_len),
        ]
    )

    if bull_score >= 4:
        return "bull"
    if bear_score >= 4:
        return "bear"
    if bull_score > bear_score:
        return "lean_bull"
    if bear_score > bull_score:
        return "lean_bear"
    return "neutral"


def _regime_allows(direction: str, trend_1d: str, trend_4h: str, trend_1h: str) -> bool:
    if direction == "long":
        h1_bull = _is_bullish_label(trend_1h)
        h4_bull = _is_bullish_label(trend_4h)
        d1_bull = _is_bullish_label(trend_1d)

        h1_bear = _is_bearish_label(trend_1h)
        h4_bear = _is_bearish_label(trend_4h)

        if h1_bull and h4_bull:
            return True
        if h1_bull and trend_4h == "neutral":
            return True
        if h4_bull and trend_1h == "neutral":
            return True
        if (h1_bull and h4_bear) or (h1_bear and h4_bull):
            return d1_bull
        return False

    h1_bear = _is_bearish_label(trend_1h)
    h4_bear = _is_bearish_label(trend_4h)
    d1_bear = _is_bearish_label(trend_1d)

    h1_bull = _is_bullish_label(trend_1h)
    h4_bull = _is_bullish_label(trend_4h)

    if h1_bear and h4_bear:
        return True
    if h1_bear and trend_4h == "neutral":
        return True
    if h4_bear and trend_1h == "neutral":
        return True
    if (h1_bear and h4_bull) or (h1_bull and h4_bear):
        return d1_bear
    return False


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


def detect_signals(
    symbol: str,
    klines_1d: list[dict],
    klines_4h: list[dict],
    klines_1h: list[dict],
    klines_15m: list[dict],
) -> dict:
    trend_1d = classify_trend(klines_1d, structure_len=8)
    trend_4h = classify_trend(klines_4h, structure_len=10)
    trend_1h = classify_trend(klines_1h, structure_len=10)

    latest_1d = klines_1d[-1]
    latest_4h = klines_4h[-1]
    latest_1h = klines_1h[-1]
    latest = klines_15m[-1]
    prev = klines_15m[-2]
    atr = latest["atr"]

    piv_h, piv_l = find_pivots(klines_15m)
    bos_15 = detect_last_bos(klines_15m, piv_h, piv_l)
    mss_15 = detect_last_mss(klines_15m, piv_h, piv_l)

    bullish_structure = bos_15 == "up" or mss_15 == "up"
    bearish_structure = bos_15 == "down" or mss_15 == "down"

    near_resistance = bool(
        piv_h and abs(klines_15m[piv_h[-1]]["high"] - latest["close"]) < atr * 0.35
    )
    near_support = bool(
        piv_l and abs(latest["close"] - klines_15m[piv_l[-1]]["low"]) < atr * 0.35
    )

    tai_not_icepoint = not latest["tai_is_icepoint"]

    allow_long = _regime_allows("long", trend_1d, trend_4h, trend_1h)
    allow_short = _regime_allows("short", trend_1d, trend_4h, trend_1h)

    recent_4 = klines_15m[-4:]
    b_long_pullback_seen = min(k["low"] for k in recent_4) <= latest["ema10"] + atr * 0.25
    b_short_pullback_seen = max(k["high"] for k in recent_4) >= latest["ema10"] - atr * 0.25

    b_long_reclaim = (
        latest["close"] >= latest["ema10"]
        and latest["close"] > latest["open"]
        and latest["fl_trend"] >= 0
    )
    b_short_reject = (
        latest["close"] <= latest["ema10"]
        and latest["close"] < latest["open"]
        and latest["fl_trend"] <= 0
    )

    sss_long_improving = latest["sss_hist"] > prev["sss_hist"]
    sss_short_improving = latest["sss_hist"] < prev["sss_hist"]

    cm_long_supportive = latest["cm_macd_above_signal"] and latest["cm_hist_up"]
    cm_short_supportive = (not latest["cm_macd_above_signal"]) and latest["cm_hist_down"]

    a_long_breakout = (
        bos_15 == "up"
        or is_bullish_fvg(klines_15m[-10:])
        or (latest["fl_buy_signal"] and latest["close"] > latest["ema20"])
    )
    a_short_breakdown = (
        bos_15 == "down"
        or is_bearish_fvg(klines_15m[-10:])
        or (latest["fl_sell_signal"] and latest["close"] < latest["ema20"])
    )

    c_long_eq_core = latest["sss_bull_div"] or (latest["sss_oversold_warning"] and sss_long_improving)
    c_short_eq_core = latest["sss_bear_div"] or (latest["sss_overbought_warning"] and sss_short_improving)

    c_long_strategy_premise = near_support or is_bullish_fvg(klines_15m[-6:]) or latest["fl_buy_signal"]
    c_short_strategy_premise = near_resistance or is_bearish_fvg(klines_15m[-6:]) or latest["fl_sell_signal"]

    c_long_price_confirm = latest["close"] > prev["close"] or latest["low"] >= prev["low"]
    c_short_price_confirm = latest["close"] < prev["close"] or latest["high"] <= prev["high"]

    signals = []
    near_miss_signals = []
    blocked_counter: Counter = Counter()

    # A = 确认突破 / 可能突破后顺势，但不追涨杀跌
    a_long_checks = {
        "regime_allows_long": allow_long,
        "tai_not_icepoint": tai_not_icepoint,
        "smc_breakout": a_long_breakout,
        "bullish_structure": bullish_structure,
        "ema_supportive": latest["close"] > latest["ema20"] and latest["ema10"] > latest["ema20"],
        "fl_supportive": latest["fl_trend"] == 1 or latest["fl_buy_signal"],
        "no_sss_bear_div": not latest["sss_bear_div"],
        "no_sss_overbought_warning": not latest["sss_overbought_warning"],
        "cm_supportive": cm_long_supportive,
        "not_too_far_from_ema20": (latest["close"] - latest["ema20"]) < atr * 1.4,
        "rar_trend_not_weak": latest["rar_trend_strong"],
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
                "atr": atr,
            }
        )

    a_short_checks = {
        "regime_allows_short": allow_short,
        "tai_not_icepoint": tai_not_icepoint,
        "smc_breakdown": a_short_breakdown,
        "bearish_structure": bearish_structure,
        "ema_supportive": latest["close"] < latest["ema20"] and latest["ema10"] < latest["ema20"],
        "fl_supportive": latest["fl_trend"] == -1 or latest["fl_sell_signal"],
        "no_sss_bull_div": not latest["sss_bull_div"],
        "no_sss_oversold_warning": not latest["sss_oversold_warning"],
        "cm_supportive": cm_short_supportive,
        "not_too_far_from_ema20": (latest["ema20"] - latest["close"]) < atr * 1.4,
        "rar_trend_not_weak": latest["rar_trend_strong"],
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
                "atr": atr,
            }
        )

    # B = 最遵守 SMC + ICT，其余只参考
    b_long_checks = {
        "regime_allows_long": allow_long,
        "tai_not_icepoint": tai_not_icepoint,
        "smc_premise_long": bullish_structure or is_bullish_fvg(klines_15m[-8:]) or near_support,
        "pullback_seen": b_long_pullback_seen,
        "reclaim_after_pullback": b_long_reclaim,
        "close_above_ema20": latest["close"] > latest["ema20"],
        "fl_not_bearish": latest["fl_trend"] >= 0,
        "no_strong_sss_contradiction": not (latest["sss_bear_div"] and latest["cm_hist_down"]),
        "not_too_far_from_ema10": (latest["close"] - latest["ema10"]) < atr * 0.9,
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
                "atr": atr,
            }
        )

    b_short_checks = {
        "regime_allows_short": allow_short,
        "tai_not_icepoint": tai_not_icepoint,
        "smc_premise_short": bearish_structure or is_bearish_fvg(klines_15m[-8:]) or near_resistance,
        "pullback_seen": b_short_pullback_seen,
        "reject_after_pullback": b_short_reject,
        "close_below_ema20": latest["close"] < latest["ema20"],
        "fl_not_bullish": latest["fl_trend"] <= 0,
        "no_strong_sss_contradiction": not (latest["sss_bull_div"] and latest["cm_hist_up"]),
        "not_too_far_from_ema10": (latest["ema10"] - latest["close"]) < atr * 0.9,
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
                "atr": atr,
            }
        )

    # C = SMC + ICT 后，EQ 权重最高
    c_long_checks = {
        "regime_allows_long": allow_long,
        "tai_not_icepoint": tai_not_icepoint,
        "strategy_premise_long": c_long_strategy_premise,
        "eq_core_long": c_long_eq_core,
        "price_confirm": c_long_price_confirm,
        "cm_not_weakening": latest["cm_hist_up"] or latest["cm_macd_above_signal"],
        "fl_not_bearish": latest["fl_trend"] >= 0 or latest["fl_buy_signal"],
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
                "atr": atr,
            }
        )

    c_short_checks = {
        "regime_allows_short": allow_short,
        "tai_not_icepoint": tai_not_icepoint,
        "strategy_premise_short": c_short_strategy_premise,
        "eq_core_short": c_short_eq_core,
        "price_confirm": c_short_price_confirm,
        "cm_not_weakening": latest["cm_hist_down"] or (not latest["cm_macd_above_signal"]),
        "fl_not_bullish": latest["fl_trend"] <= 0 or latest["fl_sell_signal"],
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
                "atr": atr,
            }
        )

    return {
        "signals": _pick_best_per_direction(signals),
        "near_miss_signals": near_miss_signals,
        "blocked_reasons": dict(blocked_counter),
    }
