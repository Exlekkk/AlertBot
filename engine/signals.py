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


def _count_true(*conds) -> int:
    return sum(bool(c) for c in conds)


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


def _regime_state(direction: str, trend_1d: str, trend_4h: str, trend_1h: str) -> str:
    if direction == "long":
        h1_bull = _is_bullish_label(trend_1h)
        h4_bull = _is_bullish_label(trend_4h)
        d1_bull = _is_bullish_label(trend_1d)

        h1_bear = _is_bearish_label(trend_1h)
        h4_bear = _is_bearish_label(trend_4h)

        if h1_bull and h4_bull:
            return "aligned"
        if h1_bull and trend_4h == "neutral":
            return "aligned"
        if h4_bull and trend_1h == "neutral":
            return "aligned"
        if (h1_bull and h4_bear) or (h1_bear and h4_bull):
            return "conflict_resolved" if d1_bull else "blocked"
        return "blocked"

    h1_bear = _is_bearish_label(trend_1h)
    h4_bear = _is_bearish_label(trend_4h)
    d1_bear = _is_bearish_label(trend_1d)

    h1_bull = _is_bullish_label(trend_1h)
    h4_bull = _is_bullish_label(trend_4h)

    if h1_bear and h4_bear:
        return "aligned"
    if h1_bear and trend_4h == "neutral":
        return "aligned"
    if h4_bear and trend_1h == "neutral":
        return "aligned"
    if (h1_bear and h4_bull) or (h1_bull and h4_bear):
        return "conflict_resolved" if d1_bear else "blocked"
    return "blocked"


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

    regime_long_state = _regime_state("long", trend_1d, trend_4h, trend_1h)
    regime_short_state = _regime_state("short", trend_1d, trend_4h, trend_1h)

    allow_long = regime_long_state != "blocked"
    allow_short = regime_short_state != "blocked"

    trend_display_long = trend_4h if regime_long_state == "aligned" else trend_1d
    trend_display_short = trend_4h if regime_short_state == "aligned" else trend_1d

    latest = klines_15m[-1]
    prev = klines_15m[-2]
    atr = latest["atr"]

    piv_h, piv_l = find_pivots(klines_15m)
    bos_15 = detect_last_bos(klines_15m, piv_h, piv_l)
    mss_15 = detect_last_mss(klines_15m, piv_h, piv_l)

    bullish_structure = bos_15 == "up" or mss_15 == "up"
    bearish_structure = bos_15 == "down" or mss_15 == "down"

    recent_6 = klines_15m[-6:]
    recent_8 = klines_15m[-8:]
    bullish_fvg_recent = is_bullish_fvg(recent_6)
    bearish_fvg_recent = is_bearish_fvg(recent_6)

    near_resistance = bool(
        piv_h and abs(klines_15m[piv_h[-1]]["high"] - latest["close"]) < atr * 0.45
    )
    near_support = bool(
        piv_l and abs(latest["close"] - klines_15m[piv_l[-1]]["low"]) < atr * 0.45
    )

    tai_not_icepoint = not latest["tai_is_icepoint"]

    recent_6_lows = min(k["low"] for k in recent_6)
    recent_6_highs = max(k["high"] for k in recent_6)

    b_long_pullback_seen = recent_6_lows <= latest["ema10"] + atr * 0.35 or near_support
    b_short_pullback_seen = recent_6_highs >= latest["ema10"] - atr * 0.35 or near_resistance

    b_long_reclaim = latest["close"] >= latest["ema10"] and latest["close"] > latest["open"]
    b_short_reject = latest["close"] <= latest["ema10"] and latest["close"] < latest["open"]

    sss_long_improving = latest["sss_hist"] > prev["sss_hist"]
    sss_short_improving = latest["sss_hist"] < prev["sss_hist"]

    cm_long_supportive = latest["cm_macd_above_signal"] and latest["cm_hist_up"]
    cm_short_supportive = (not latest["cm_macd_above_signal"]) and latest["cm_hist_down"]

    cm_long_not_bad = latest["cm_macd_above_signal"] or latest["cm_hist_up"]
    cm_short_not_bad = (not latest["cm_macd_above_signal"]) or latest["cm_hist_down"]

    a_long_breakout = bos_15 == "up" or bullish_fvg_recent or (mss_15 == "up" and latest["close"] > latest["ema10"])
    a_short_breakdown = bos_15 == "down" or bearish_fvg_recent or (mss_15 == "down" and latest["close"] < latest["ema10"])

    c_long_eq_core = latest["sss_bull_div"] or (latest["sss_oversold_warning"] and sss_long_improving)
    c_short_eq_core = latest["sss_bear_div"] or (latest["sss_overbought_warning"] and sss_short_improving)

    c_long_strategy_premise = near_support or bullish_fvg_recent or latest["fl_buy_signal"] or mss_15 == "up"
    c_short_strategy_premise = near_resistance or bearish_fvg_recent or latest["fl_sell_signal"] or mss_15 == "down"

    c_long_price_confirm = latest["close"] > prev["close"] or latest["low"] >= prev["low"]
    c_short_price_confirm = latest["close"] < prev["close"] or latest["high"] <= prev["high"]

    signals = []
    near_miss_signals = []
    blocked_counter: Counter = Counter()

    # A 类：高周期方向为主，15m 只负责突破触发；辅助指标只做组合过滤
    a_long_secondary_ok = _count_true(
        latest["fl_trend"] == 1 or latest["fl_buy_signal"],
        cm_long_supportive,
        not latest["sss_bear_div"],
        latest["rar_trend_strong"],
    ) >= 2
    a_long_strong_contra = _count_true(
        latest["sss_bear_div"],
        latest["sss_overbought_warning"],
        latest["cm_hist_down"],
        latest["fl_trend"] == -1,
    ) >= 2

    a_long_checks = {
        "regime_allows_long": allow_long,
        "tai_not_icepoint": tai_not_icepoint,
        "smc_breakout": a_long_breakout,
        "bullish_structure": bullish_structure,
        "ema_supportive": latest["ema10"] >= latest["ema20"] and latest["close"] >= latest["ema10"],
        "not_too_far_from_ema20": (latest["close"] - latest["ema20"]) <= atr * 1.8,
        "secondary_pack_ok": a_long_secondary_ok,
        "no_strong_secondary_contradiction": not a_long_strong_contra,
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
                "trend_1h": trend_display_long,
                "status": "active",
                "atr": atr,
            }
        )

    a_short_secondary_ok = _count_true(
        latest["fl_trend"] == -1 or latest["fl_sell_signal"],
        cm_short_supportive,
        not latest["sss_bull_div"],
        latest["rar_trend_strong"],
    ) >= 2
    a_short_strong_contra = _count_true(
        latest["sss_bull_div"],
        latest["sss_oversold_warning"],
        latest["cm_hist_up"],
        latest["fl_trend"] == 1,
    ) >= 2

    a_short_checks = {
        "regime_allows_short": allow_short,
        "tai_not_icepoint": tai_not_icepoint,
        "smc_breakdown": a_short_breakdown,
        "bearish_structure": bearish_structure,
        "ema_supportive": latest["ema10"] <= latest["ema20"] and latest["close"] <= latest["ema10"],
        "not_too_far_from_ema20": (latest["ema20"] - latest["close"]) <= atr * 1.8,
        "secondary_pack_ok": a_short_secondary_ok,
        "no_strong_secondary_contradiction": not a_short_strong_contra,
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
                "trend_1h": trend_display_short,
                "status": "active",
                "atr": atr,
            }
        )

    # B 类：高周期先给方向，15m 做回踩/反弹再接，辅助只做不逆风过滤
    b_long_secondary_ok = _count_true(
        latest["fl_trend"] >= 0,
        cm_long_not_bad,
        not latest["sss_bear_div"],
        latest["rar_trend_strong"],
    ) >= 1
    b_long_strong_contra = _count_true(
        latest["sss_bear_div"],
        latest["cm_hist_down"],
        latest["fl_trend"] == -1,
    ) >= 2

    b_long_checks = {
        "regime_allows_long": allow_long,
        "tai_not_icepoint": tai_not_icepoint,
        "smc_premise_long": bullish_structure or is_bullish_fvg(recent_8) or near_support,
        "pullback_seen": b_long_pullback_seen,
        "reclaim_after_pullback": b_long_reclaim,
        "ema_not_lost": latest["close"] >= latest["ema20"] or (latest["ema10"] >= latest["ema20"] and latest["close"] >= latest["ema10"]),
        "not_too_far_from_ema10": abs(latest["close"] - latest["ema10"]) <= atr * 1.25,
        "secondary_pack_ok": b_long_secondary_ok,
        "no_strong_secondary_contradiction": not b_long_strong_contra,
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
                "trend_1h": trend_display_long,
                "status": "active",
                "atr": atr,
            }
        )

    b_short_secondary_ok = _count_true(
        latest["fl_trend"] <= 0,
        cm_short_not_bad,
        not latest["sss_bull_div"],
        latest["rar_trend_strong"],
    ) >= 1
    b_short_strong_contra = _count_true(
        latest["sss_bull_div"],
        latest["cm_hist_up"],
        latest["fl_trend"] == 1,
    ) >= 2

    b_short_checks = {
        "regime_allows_short": allow_short,
        "tai_not_icepoint": tai_not_icepoint,
        "smc_premise_short": bearish_structure or is_bearish_fvg(recent_8) or near_resistance,
        "pullback_seen": b_short_pullback_seen,
        "reject_after_pullback": b_short_reject,
        "ema_not_lost": latest["close"] <= latest["ema20"] or (latest["ema10"] <= latest["ema20"] and latest["close"] <= latest["ema10"]),
        "not_too_far_from_ema10": abs(latest["ema10"] - latest["close"]) <= atr * 1.25,
        "secondary_pack_ok": b_short_secondary_ok,
        "no_strong_secondary_contradiction": not b_short_strong_contra,
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
                "trend_1h": trend_display_short,
                "status": "active",
                "atr": atr,
            }
        )

    # C 类：高周期方向仍然先行，15m 左侧观察；EQ 权重最高，其余只要别明显反着来
    c_long_confirmation_ok = _count_true(
        c_long_price_confirm,
        latest["fl_trend"] >= 0 or latest["fl_buy_signal"],
        latest["cm_hist_up"] or latest["cm_macd_above_signal"],
    ) >= 1

    c_long_checks = {
        "regime_allows_long": allow_long,
        "tai_not_icepoint": tai_not_icepoint,
        "strategy_premise_long": c_long_strategy_premise,
        "eq_core_long": c_long_eq_core,
        "confirmation_pack_ok": c_long_confirmation_ok,
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
                "trend_1h": trend_display_long,
                "status": "early",
                "atr": atr,
            }
        )

    c_short_confirmation_ok = _count_true(
        c_short_price_confirm,
        latest["fl_trend"] <= 0 or latest["fl_sell_signal"],
        latest["cm_hist_down"] or (not latest["cm_macd_above_signal"]),
    ) >= 1

    c_short_checks = {
        "regime_allows_short": allow_short,
        "tai_not_icepoint": tai_not_icepoint,
        "strategy_premise_short": c_short_strategy_premise,
        "eq_core_short": c_short_eq_core,
        "confirmation_pack_ok": c_short_confirmation_ok,
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
                "trend_1h": trend_display_short,
                "status": "early",
                "atr": atr,
            }
        )

    return {
        "signals": _pick_best_per_direction(signals),
        "near_miss_signals": near_miss_signals,
        "blocked_reasons": dict(blocked_counter),
    }
