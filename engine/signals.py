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
            k["ema120"] >= k["ema169"],
            bos == "up" or mss == "up",
            higher_highs_lows(klines, structure_len),
        ]
    )
    bear_score = sum(
        [
            k["close"] < k["ema20"],
            k["ema10"] < k["ema20"],
            k["ema20"] < k["ema120"],
            k["ema120"] <= k["ema169"],
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


def _evaluate_branch(
    name: str,
    required_checks: dict[str, bool],
    support_checks: dict[str, bool],
    min_support: int,
    contradiction_checks: dict[str, bool],
    contradiction_limit: int,
    near_miss_signals: list[dict],
    blocked_counter: Counter,
):
    failed = [check_name for check_name, ok in required_checks.items() if not ok]

    support_score = _count_true(*support_checks.values())
    if support_score < min_support:
        failed.append(f"support_score_lt_{min_support}")

    contradiction_score = _count_true(*contradiction_checks.values())
    if contradiction_score >= contradiction_limit:
        failed.append("strong_secondary_contradiction")

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
    atr = max(latest["atr"], 1e-9)

    piv_h, piv_l = find_pivots(klines_15m)
    bos_15 = detect_last_bos(klines_15m, piv_h, piv_l)
    mss_15 = detect_last_mss(klines_15m, piv_h, piv_l)

    bullish_structure = bos_15 == "up" or mss_15 == "up"
    bearish_structure = bos_15 == "down" or mss_15 == "down"

    recent_6 = klines_15m[-6:]
    recent_8 = klines_15m[-8:]
    prior_6 = klines_15m[-7:-1] if len(klines_15m) >= 7 else recent_6[:-1]

    bullish_fvg_recent = is_bullish_fvg(recent_6)
    bearish_fvg_recent = is_bearish_fvg(recent_6)

    near_resistance = bool(
        piv_h and abs(klines_15m[piv_h[-1]]["high"] - latest["close"]) < atr * 0.55
    )
    near_support = bool(
        piv_l and abs(latest["close"] - klines_15m[piv_l[-1]]["low"]) < atr * 0.55
    )

    tai_not_icepoint = not latest["tai_is_icepoint"]

    recent_6_lows = min(k["low"] for k in recent_6)
    recent_6_highs = max(k["high"] for k in recent_6)
    prior_6_high = max((k["high"] for k in prior_6), default=recent_6_highs)
    prior_6_low = min((k["low"] for k in prior_6), default=recent_6_lows)

    b_long_pullback_seen = recent_6_lows <= latest["ema10"] + atr * 0.45 or near_support
    b_short_pullback_seen = recent_6_highs >= latest["ema10"] - atr * 0.45 or near_resistance

    b_long_reclaim = _count_true(
        latest["close"] >= latest["ema10"],
        latest["close"] > prev["close"],
        latest["close"] > latest["open"],
        latest["low"] >= prev["low"],
    ) >= 2
    b_short_reject = _count_true(
        latest["close"] <= latest["ema10"],
        latest["close"] < prev["close"],
        latest["close"] < latest["open"],
        latest["high"] <= prev["high"],
    ) >= 2

    sss_long_improving = latest["sss_hist"] > prev["sss_hist"]
    sss_short_improving = latest["sss_hist"] < prev["sss_hist"]

    cm_long_supportive = latest["cm_macd_above_signal"] and latest["cm_hist_up"]
    cm_short_supportive = (not latest["cm_macd_above_signal"]) and latest["cm_hist_down"]

    cm_long_not_bad = latest["cm_macd_above_signal"] or latest["cm_hist_up"]
    cm_short_not_bad = (not latest["cm_macd_above_signal"]) or latest["cm_hist_down"]

    htf_a_long_allowed = allow_long or (_is_bullish_label(trend_4h) and trend_1d != "bear")
    htf_a_short_allowed = allow_short or (_is_bearish_label(trend_4h) and trend_1d != "bull")

    htf_b_long_allowed = allow_long or ((_is_bullish_label(trend_1h) or _is_bullish_label(trend_4h)) and trend_1d != "bear")
    htf_b_short_allowed = allow_short or ((_is_bearish_label(trend_1h) or _is_bearish_label(trend_4h)) and trend_1d != "bull")

    htf_c_long_allowed = not _is_bearish_label(trend_4h) and trend_1d != "bear"
    htf_c_short_allowed = not _is_bullish_label(trend_4h) and trend_1d != "bull"

    a_long_breakout = _count_true(
        bos_15 == "up",
        mss_15 == "up",
        bullish_fvg_recent,
        latest["close"] >= prior_6_high - atr * 0.18,
        latest["close"] > latest["ema10"] and latest["close"] > prev["high"],
    ) >= 2
    a_short_breakdown = _count_true(
        bos_15 == "down",
        mss_15 == "down",
        bearish_fvg_recent,
        latest["close"] <= prior_6_low + atr * 0.18,
        latest["close"] < latest["ema10"] and latest["close"] < prev["low"],
    ) >= 2

    c_long_eq_core = latest["sss_bull_div"] or (latest["sss_oversold_warning"] and sss_long_improving)
    c_short_eq_core = latest["sss_bear_div"] or (latest["sss_overbought_warning"] and sss_short_improving)

    c_long_strategy_premise = near_support or bullish_fvg_recent or latest["fl_buy_signal"] or mss_15 == "up"
    c_short_strategy_premise = near_resistance or bearish_fvg_recent or latest["fl_sell_signal"] or mss_15 == "down"

    c_long_price_confirm = latest["close"] > prev["close"] or latest["low"] >= prev["low"]
    c_short_price_confirm = latest["close"] < prev["close"] or latest["high"] <= prev["high"]

    signals = []
    near_miss_signals = []
    blocked_counter: Counter = Counter()

    a_long_required = {
        "htf_a_long_allowed": htf_a_long_allowed,
        "tai_not_icepoint": tai_not_icepoint,
        "15m_breakout_trigger": a_long_breakout,
    }
    a_long_support = {
        "bullish_structure": bullish_structure,
        "ema_supportive": latest["ema10"] >= latest["ema20"] and latest["close"] >= latest["ema10"],
        "not_too_far_from_ema20": (latest["close"] - latest["ema20"]) <= atr * 2.2,
        "cm_supportive": cm_long_supportive,
        "fl_supportive": latest["fl_trend"] == 1 or latest["fl_buy_signal"],
        "rar_trend_not_weak": latest["rar_trend_strong"],
    }
    a_long_contra = {
        "eq_core_short": latest["sss_bear_div"],
        "overbought_warning": latest["sss_overbought_warning"],
        "cm_hist_down": latest["cm_hist_down"],
        "fl_trend_down": latest["fl_trend"] == -1,
    }
    if _evaluate_branch("A_LONG", a_long_required, a_long_support, 2, a_long_contra, 3, near_miss_signals, blocked_counter):
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

    a_short_required = {
        "htf_a_short_allowed": htf_a_short_allowed,
        "tai_not_icepoint": tai_not_icepoint,
        "15m_breakdown_trigger": a_short_breakdown,
    }
    a_short_support = {
        "bearish_structure": bearish_structure,
        "ema_supportive": latest["ema10"] <= latest["ema20"] and latest["close"] <= latest["ema10"],
        "not_too_far_from_ema20": (latest["ema20"] - latest["close"]) <= atr * 2.2,
        "cm_supportive": cm_short_supportive,
        "fl_supportive": latest["fl_trend"] == -1 or latest["fl_sell_signal"],
        "rar_trend_not_weak": latest["rar_trend_strong"],
    }
    a_short_contra = {
        "eq_core_long": latest["sss_bull_div"],
        "oversold_warning": latest["sss_oversold_warning"],
        "cm_hist_up": latest["cm_hist_up"],
        "fl_trend_up": latest["fl_trend"] == 1,
    }
    if _evaluate_branch("A_SHORT", a_short_required, a_short_support, 2, a_short_contra, 3, near_miss_signals, blocked_counter):
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

    b_long_required = {
        "htf_b_long_allowed": htf_b_long_allowed,
        "tai_not_icepoint": tai_not_icepoint,
        "15m_smc_premise_long": bullish_structure or is_bullish_fvg(recent_8) or near_support or mss_15 == "up",
        "pullback_then_reclaim": b_long_pullback_seen and b_long_reclaim,
    }
    b_long_support = {
        "ema_not_lost": latest["close"] >= latest["ema20"] or latest["close"] >= latest["ema10"],
        "cm_not_bad": cm_long_not_bad,
        "fl_not_bearish": latest["fl_trend"] >= 0,
        "rar_trend_not_weak": latest["rar_trend_strong"],
        "price_recovering": latest["close"] >= prev["close"] or latest["low"] >= prev["low"],
    }
    b_long_contra = {
        "eq_core_short": latest["sss_bear_div"],
        "cm_hist_down": latest["cm_hist_down"],
        "fl_trend_down": latest["fl_trend"] == -1,
        "price_below_ema20_far": latest["close"] < latest["ema20"] - atr * 0.8,
    }
    if _evaluate_branch("B_PULLBACK_LONG", b_long_required, b_long_support, 1, b_long_contra, 3, near_miss_signals, blocked_counter):
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

    b_short_required = {
        "htf_b_short_allowed": htf_b_short_allowed,
        "tai_not_icepoint": tai_not_icepoint,
        "15m_smc_premise_short": bearish_structure or is_bearish_fvg(recent_8) or near_resistance or mss_15 == "down",
        "pullback_then_reject": b_short_pullback_seen and b_short_reject,
    }
    b_short_support = {
        "ema_not_lost": latest["close"] <= latest["ema20"] or latest["close"] <= latest["ema10"],
        "cm_not_bad": cm_short_not_bad,
        "fl_not_bullish": latest["fl_trend"] <= 0,
        "rar_trend_not_weak": latest["rar_trend_strong"],
        "price_weakening": latest["close"] <= prev["close"] or latest["high"] <= prev["high"],
    }
    b_short_contra = {
        "eq_core_long": latest["sss_bull_div"],
        "cm_hist_up": latest["cm_hist_up"],
        "fl_trend_up": latest["fl_trend"] == 1,
        "price_above_ema20_far": latest["close"] > latest["ema20"] + atr * 0.8,
    }
    if _evaluate_branch("B_PULLBACK_SHORT", b_short_required, b_short_support, 1, b_short_contra, 3, near_miss_signals, blocked_counter):
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

    c_long_required = {
        "htf_c_long_allowed": htf_c_long_allowed,
        "tai_not_icepoint": tai_not_icepoint,
        "15m_strategy_premise_long": c_long_strategy_premise,
        "early_confirmation_long": c_long_eq_core or c_long_price_confirm,
    }
    c_long_support = {
        "eq_core_long": c_long_eq_core,
        "price_confirm": c_long_price_confirm,
        "fl_not_bearish": latest["fl_trend"] >= 0 or latest["fl_buy_signal"],
        "cm_not_weakening": latest["cm_hist_up"] or latest["cm_macd_above_signal"],
        "sss_hist_improving": sss_long_improving,
    }
    c_long_contra = {
        "eq_core_short": latest["sss_bear_div"],
        "cm_hist_down": latest["cm_hist_down"],
        "fl_trend_down": latest["fl_trend"] == -1,
        "overbought_warning": latest["sss_overbought_warning"],
    }
    if _evaluate_branch("C_LEFT_LONG", c_long_required, c_long_support, 1, c_long_contra, 3, near_miss_signals, blocked_counter):
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

    c_short_required = {
        "htf_c_short_allowed": htf_c_short_allowed,
        "tai_not_icepoint": tai_not_icepoint,
        "15m_strategy_premise_short": c_short_strategy_premise,
        "early_confirmation_short": c_short_eq_core or c_short_price_confirm,
    }
    c_short_support = {
        "eq_core_short": c_short_eq_core,
        "price_confirm": c_short_price_confirm,
        "fl_not_bullish": latest["fl_trend"] <= 0 or latest["fl_sell_signal"],
        "cm_not_weakening": latest["cm_hist_down"] or (not latest["cm_macd_above_signal"]),
        "sss_hist_weakening": sss_short_improving,
    }
    c_short_contra = {
        "eq_core_long": latest["sss_bull_div"],
        "cm_hist_up": latest["cm_hist_up"],
        "fl_trend_up": latest["fl_trend"] == 1,
        "oversold_warning": latest["sss_oversold_warning"],
    }
    if _evaluate_branch("C_LEFT_SHORT", c_short_required, c_short_support, 1, c_short_contra, 3, near_miss_signals, blocked_counter):
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
