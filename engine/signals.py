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


def _count_true(*conds) -> int:
    return sum(bool(c) for c in conds)


def _momentum_up(k: dict) -> bool:
    return bool(k.get("cm_macd_above_signal")) and (
        bool(k.get("cm_hist_up")) or float(k.get("sss_hist", 0.0)) >= 0
    )


def _momentum_down(k: dict) -> bool:
    return (not bool(k.get("cm_macd_above_signal"))) and (
        bool(k.get("cm_hist_down")) or float(k.get("sss_hist", 0.0)) <= 0
    )


def _down_pressure(k: dict) -> bool:
    return k["close"] < k["ema20"] and k["ema10"] < k["ema20"] and _momentum_down(k)


def _up_pressure(k: dict) -> bool:
    return k["close"] > k["ema20"] and k["ema10"] > k["ema20"] and _momentum_up(k)


def _long_overheat(k: dict, prev_k: dict | None = None) -> bool:
    sss_rollover = prev_k is not None and float(k.get("sss_hist", 0.0)) < float(prev_k.get("sss_hist", 0.0))
    cm_rollover = prev_k is not None and float(k.get("cm_hist", 0.0)) < float(prev_k.get("cm_hist", 0.0))
    return bool(k.get("sss_bear_div")) or bool(k.get("sss_overbought_warning")) or (sss_rollover and cm_rollover)


def _short_exhausted(k: dict, prev_k: dict | None = None) -> bool:
    sss_rebound = prev_k is not None and float(k.get("sss_hist", 0.0)) > float(prev_k.get("sss_hist", 0.0))
    cm_rebound = prev_k is not None and float(k.get("cm_hist", 0.0)) > float(prev_k.get("cm_hist", 0.0))
    return bool(k.get("sss_bull_div")) or bool(k.get("sss_oversold_warning")) or (sss_rebound and cm_rebound)


def _cross_up(curr_a: float, curr_b: float, prev_a: float, prev_b: float) -> bool:
    return curr_a > curr_b and prev_a <= prev_b


def _cross_down(curr_a: float, curr_b: float, prev_a: float, prev_b: float) -> bool:
    return curr_a < curr_b and prev_a >= prev_b


def _trend_value(label: str, direction: str) -> int:
    table = {
        "bull": 2,
        "lean_bull": 1,
        "neutral": 0,
        "lean_bear": -1,
        "bear": -2,
    }
    value = table.get(label, 0)
    return value if direction == "long" else -value


def _candle_close_position(k: dict) -> float:
    rng = max(float(k["high"]) - float(k["low"]), 1e-9)
    return (float(k["close"]) - float(k["low"])) / rng


def _candle_expansion(k: dict, prev_k: dict, atr: float) -> bool:
    current_range = float(k["high"]) - float(k["low"])
    prev_range = float(prev_k["high"]) - float(prev_k["low"])
    return current_range >= max(atr * 0.65, prev_range * 1.10)


def _recent_high(klines: list[dict], count: int) -> float:
    window = klines[-count:]
    return max(float(k["high"]) for k in window)


def _recent_low(klines: list[dict], count: int) -> float:
    window = klines[-count:]
    return min(float(k["low"]) for k in window)


def classify_trend(klines: list[dict], structure_len: int = 10) -> str:
    pivot_highs, pivot_lows = find_pivots(klines)
    bos = detect_last_bos(klines, pivot_highs, pivot_lows)
    mss = detect_last_mss(klines, pivot_highs, pivot_lows)
    k = klines[-1]

    bullish_structure = bos == "up" or mss == "up" or higher_highs_lows(klines, structure_len)
    bearish_structure = bos == "down" or mss == "down" or lower_highs_lows(klines, structure_len)

    strong_bull_setup = (
        k["close"] > k["ema20"]
        and k["ema10"] > k["ema20"]
        and bullish_structure
        and _momentum_up(k)
    )
    strong_bear_setup = (
        k["close"] < k["ema20"]
        and k["ema10"] < k["ema20"]
        and bearish_structure
        and _momentum_down(k)
    )

    long_term_bull = k["close"] > k["ema120"] and k["close"] > k["ema169"] and k["ema20"] >= k["ema120"]
    long_term_bear = k["close"] < k["ema120"] and k["close"] < k["ema169"] and k["ema20"] <= k["ema120"]

    if strong_bull_setup and long_term_bull and k["ema120"] >= k["ema169"]:
        return "bull"
    if strong_bear_setup and long_term_bear and k["ema120"] <= k["ema169"]:
        return "bear"
    if strong_bull_setup:
        return "lean_bull"
    if strong_bear_setup:
        return "lean_bear"
    if long_term_bull and not _momentum_down(k) and not bearish_structure:
        return "lean_bull"
    if long_term_bear and not _momentum_up(k) and not bullish_structure:
        return "lean_bear"
    return "neutral"


def _direction_regime_score(
    direction: str,
    trend_1d: str,
    trend_4h: str,
    trend_1h: str,
    k_4h: dict,
    p_4h: dict,
    k_1h: dict,
    p_1h: dict,
) -> int:
    score = 0
    score += _trend_value(trend_4h, direction) * 2
    score += _trend_value(trend_1h, direction) * 2
    score += _trend_value(trend_1d, direction)

    if direction == "long":
        if k_4h["close"] >= k_4h["ema20"] and k_4h["ema10"] >= k_4h["ema20"]:
            score += 1
        if k_1h["close"] >= k_1h["ema20"] and k_1h["ema10"] >= k_1h["ema20"]:
            score += 1
        if _momentum_up(k_4h):
            score += 1
        if _momentum_up(k_1h):
            score += 1
        if _long_overheat(k_4h, p_4h):
            score -= 2
        if _long_overheat(k_1h, p_1h):
            score -= 2
    else:
        if k_4h["close"] <= k_4h["ema20"] and k_4h["ema10"] <= k_4h["ema20"]:
            score += 1
        if k_1h["close"] <= k_1h["ema20"] and k_1h["ema10"] <= k_1h["ema20"]:
            score += 1
        if _momentum_down(k_4h):
            score += 1
        if _momentum_down(k_1h):
            score += 1
        if _short_exhausted(k_4h, p_4h):
            score -= 2
        if _short_exhausted(k_1h, p_1h):
            score -= 2

    return score


def _trend_display(direction: str, score: int) -> str:
    if direction == "long":
        if score >= 6:
            return "bull"
        if score >= 2:
            return "lean_bull"
        return "neutral"
    if score >= 6:
        return "bear"
    if score >= 2:
        return "lean_bear"
    return "neutral"


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


def _pick_best_per_direction(signals: list[dict]) -> list[dict]:
    best_by_direction = {}
    for signal in signals:
        direction = signal["direction"]
        previous = best_by_direction.get(direction)
        if not previous or signal["priority"] < previous["priority"]:
            best_by_direction[direction] = signal
    return sorted(best_by_direction.values(), key=lambda s: s["priority"])


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

    k_4h, p_4h = klines_4h[-1], klines_4h[-2]
    k_1h, p_1h = klines_1h[-1], klines_1h[-2]
    latest, prev = klines_15m[-1], klines_15m[-2]
    atr = float(latest["atr"])

    long_regime_score = _direction_regime_score("long", trend_1d, trend_4h, trend_1h, k_4h, p_4h, k_1h, p_1h)
    short_regime_score = _direction_regime_score("short", trend_1d, trend_4h, trend_1h, k_4h, p_4h, k_1h, p_1h)
    trend_display_long = _trend_display("long", long_regime_score)
    trend_display_short = _trend_display("short", short_regime_score)

    piv_h, piv_l = find_pivots(klines_15m)
    bos_15 = detect_last_bos(klines_15m, piv_h, piv_l)
    mss_15 = detect_last_mss(klines_15m, piv_h, piv_l)

    bullish_structure = bos_15 == "up" or mss_15 == "up"
    bearish_structure = bos_15 == "down" or mss_15 == "down"

    recent_6 = klines_15m[-6:]
    recent_8 = klines_15m[-8:]
    recent_12 = klines_15m[-12:]
    recent_support = _recent_low(klines_15m, 8)
    recent_resistance = _recent_high(klines_15m, 8)
    prior_break_high = max(float(k["high"]) for k in recent_12[:-1]) if len(recent_12) > 1 else float(prev["high"])
    prior_break_low = min(float(k["low"]) for k in recent_12[:-1]) if len(recent_12) > 1 else float(prev["low"])

    bullish_fvg_recent = is_bullish_fvg(recent_6) or is_bullish_fvg(recent_8)
    bearish_fvg_recent = is_bearish_fvg(recent_6) or is_bearish_fvg(recent_8)
    near_support = bool(piv_l and abs(float(latest["close"]) - float(klines_15m[piv_l[-1]]["low"])) < atr * 0.50) or abs(float(latest["close"]) - recent_support) < atr * 0.45
    near_resistance = bool(piv_h and abs(float(klines_15m[piv_h[-1]]["high"]) - float(latest["close"])) < atr * 0.50) or abs(recent_resistance - float(latest["close"])) < atr * 0.45

    cm_long_supportive = bool(latest.get("cm_macd_above_signal")) and bool(latest.get("cm_hist_up"))
    cm_short_supportive = (not bool(latest.get("cm_macd_above_signal"))) and bool(latest.get("cm_hist_down"))
    cm_long_not_bad = bool(latest.get("cm_macd_above_signal")) or bool(latest.get("cm_hist_up"))
    cm_short_not_bad = (not bool(latest.get("cm_macd_above_signal"))) or bool(latest.get("cm_hist_down"))

    rar_long_supportive = bool(latest.get("rar_trend_strong")) or float(latest.get("rar_spread", 0.0)) <= float(prev.get("rar_spread", 0.0))
    rar_short_supportive = bool(latest.get("rar_trend_strong")) or float(latest.get("rar_spread", 0.0)) <= float(prev.get("rar_spread", 0.0))

    long_m15_overheat = _long_overheat(latest, prev)
    short_m15_exhausted = _short_exhausted(latest, prev)
    long_h1_overheat = _long_overheat(k_1h, p_1h)
    short_h1_exhausted = _short_exhausted(k_1h, p_1h)
    long_h4_overheat = _long_overheat(k_4h, p_4h)
    short_h4_exhausted = _short_exhausted(k_4h, p_4h)

    close_pos = _candle_close_position(latest)
    expand_ok = _candle_expansion(latest, prev, atr)

    a_long_breakout = (
        float(latest["close"]) > float(prev["close"])
        and float(latest["high"]) >= prior_break_high - atr * 0.08
        and float(latest["close"]) >= prior_break_high - atr * 0.15
        and float(latest["close"]) >= float(latest["ema10"])
    )
    a_short_breakdown = (
        float(latest["close"]) < float(prev["close"])
        and float(latest["low"]) <= prior_break_low + atr * 0.08
        and float(latest["close"]) <= prior_break_low + atr * 0.15
        and float(latest["close"]) <= float(latest["ema10"])
    )

    a_long_impulse_ok = close_pos >= 0.62 and expand_ok and _count_true(cm_long_supportive, rar_long_supportive, bool(latest.get("fl_buy_signal")) or int(latest.get("fl_trend", 0)) >= 0) >= 2
    a_short_impulse_ok = close_pos <= 0.38 and expand_ok and _count_true(cm_short_supportive, rar_short_supportive, bool(latest.get("fl_sell_signal")) or int(latest.get("fl_trend", 0)) <= 0) >= 2

    b_long_pullback_seen = min(float(k["low"]) for k in recent_6) <= float(latest["ema10"]) + atr * 0.45 or near_support or bullish_fvg_recent
    b_short_pullback_seen = max(float(k["high"]) for k in recent_6) >= float(latest["ema10"]) - atr * 0.45 or near_resistance or bearish_fvg_recent
    b_long_reclaim = float(latest["close"]) >= float(latest["ema10"]) and float(latest["close"]) > float(prev["close"]) and close_pos >= 0.52
    b_short_reject = float(latest["close"]) <= float(latest["ema10"]) and float(latest["close"]) < float(prev["close"]) and close_pos <= 0.48

    eq_long_15m = bool(latest.get("sss_bull_div")) or bool(latest.get("sss_oversold_warning"))
    eq_short_15m = bool(latest.get("sss_bear_div")) or bool(latest.get("sss_overbought_warning"))
    eq_long_1h = bool(k_1h.get("sss_bull_div")) or bool(k_1h.get("sss_oversold_warning"))
    eq_short_1h = bool(k_1h.get("sss_bear_div")) or bool(k_1h.get("sss_overbought_warning"))

    c_long_eq_core = eq_long_15m or eq_long_1h or _cross_up(
        float(latest.get("sss_macd_line", 0.0)),
        float(latest.get("sss_signal_line", 0.0)),
        float(prev.get("sss_macd_line", 0.0)),
        float(prev.get("sss_signal_line", 0.0)),
    )
    c_short_eq_core = eq_short_15m or eq_short_1h or _cross_down(
        float(latest.get("sss_macd_line", 0.0)),
        float(latest.get("sss_signal_line", 0.0)),
        float(prev.get("sss_macd_line", 0.0)),
        float(prev.get("sss_signal_line", 0.0)),
    )

    c_long_strategy_premise = bullish_fvg_recent or near_support or bool(latest.get("fl_buy_signal")) or mss_15 == "up"
    c_short_strategy_premise = bearish_fvg_recent or near_resistance or bool(latest.get("fl_sell_signal")) or mss_15 == "down"

    c_long_confirmation_ok = _count_true(
        c_long_strategy_premise,
        float(latest["close"]) > float(prev["close"]) or float(latest["low"]) >= float(prev["low"]),
        cm_long_not_bad,
        float(latest["close"]) >= float(latest["ema20"]) or float(k_1h["close"]) >= float(k_1h["ema20"]),
    ) >= 2
    c_short_confirmation_ok = _count_true(
        c_short_strategy_premise,
        float(latest["close"]) < float(prev["close"]) or float(latest["high"]) <= float(prev["high"]),
        cm_short_not_bad,
        float(latest["close"]) <= float(latest["ema20"]) or float(k_1h["close"]) <= float(k_1h["ema20"]),
    ) >= 2

    signals = []
    near_miss_signals = []
    blocked_counter: Counter = Counter()

    a_long_checks = {
        "htf_a_long_allowed": long_regime_score >= 5 and short_regime_score < 6,
        "15m_breakout_trigger": a_long_breakout,
        "structure_backing": bullish_structure or bullish_fvg_recent or trend_1h in ("bull", "lean_bull"),
        "impulse_ok": a_long_impulse_ok,
        "no_opposite_eq_short": not eq_short_15m and not eq_short_1h,
        "not_higher_tf_overheat": not long_h1_overheat and not long_h4_overheat,
        "not_too_far_from_ema20": (float(latest["close"]) - float(latest["ema20"])) <= atr * 1.25,
        "no_strong_secondary_contradiction": not (_count_true(eq_short_15m, bool(latest.get("cm_hist_down")), int(latest.get("fl_trend", 0)) == -1) >= 2),
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

    a_short_checks = {
        "htf_a_short_allowed": short_regime_score >= 5 and long_regime_score < 6,
        "15m_breakdown_trigger": a_short_breakdown,
        "structure_backing": bearish_structure or bearish_fvg_recent or trend_1h in ("bear", "lean_bear"),
        "impulse_ok": a_short_impulse_ok,
        "no_opposite_eq_long": not eq_long_15m and not eq_long_1h,
        "not_higher_tf_exhausted": not short_h1_exhausted and not short_h4_exhausted,
        "not_too_far_from_ema20": (float(latest["ema20"]) - float(latest["close"])) <= atr * 1.25,
        "no_strong_secondary_contradiction": not (_count_true(eq_long_15m, bool(latest.get("cm_hist_up")), int(latest.get("fl_trend", 0)) == 1) >= 2),
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

    b_long_checks = {
        "htf_b_long_allowed": long_regime_score >= 3 and short_regime_score < 7,
        "15m_smc_premise_long": bullish_structure or bullish_fvg_recent or near_support or trend_1h in ("bull", "lean_bull"),
        "pullback_seen": b_long_pullback_seen,
        "pullback_then_reclaim": b_long_reclaim,
        "ema_not_lost": float(latest["close"]) >= float(latest["ema20"]) or (float(latest["ema10"]) >= float(latest["ema20"]) and float(latest["close"]) >= float(latest["ema10"])),
        "not_eq_overheat_long": not long_m15_overheat and not long_h1_overheat,
        "not_too_far_from_ema10": abs(float(latest["close"]) - float(latest["ema10"])) <= atr * 1.05,
        "no_strong_secondary_contradiction": not (_count_true(eq_short_15m, bool(latest.get("cm_hist_down")), int(latest.get("fl_trend", 0)) == -1) >= 2),
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

    b_short_checks = {
        "htf_b_short_allowed": short_regime_score >= 3 and long_regime_score < 7,
        "15m_smc_premise_short": bearish_structure or bearish_fvg_recent or near_resistance or trend_1h in ("bear", "lean_bear"),
        "pullback_seen": b_short_pullback_seen,
        "pullback_then_reject": b_short_reject,
        "ema_not_lost": float(latest["close"]) <= float(latest["ema20"]) or (float(latest["ema10"]) <= float(latest["ema20"]) and float(latest["close"]) <= float(latest["ema10"])),
        "not_eq_exhausted_short": not short_m15_exhausted and not short_h1_exhausted,
        "not_too_far_from_ema10": abs(float(latest["ema10"]) - float(latest["close"])) <= atr * 1.05,
        "no_strong_secondary_contradiction": not (_count_true(eq_long_15m, bool(latest.get("cm_hist_up")), int(latest.get("fl_trend", 0)) == 1) >= 2),
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

    c_long_checks = {
        "htf_c_long_allowed": long_regime_score >= 1 and not (trend_4h == "bear" and trend_1h == "bear"),
        "15m_strategy_premise_long": c_long_strategy_premise,
        "eq_core_long": c_long_eq_core,
        "early_confirmation_long": c_long_confirmation_ok,
        "no_opposite_eq_short": not eq_short_15m and not eq_short_1h,
        "not_higher_tf_overheat": not long_h1_overheat and not long_h4_overheat,
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

    c_short_checks = {
        "htf_c_short_allowed": short_regime_score >= 1 and not (trend_4h == "bull" and trend_1h == "bull"),
        "15m_strategy_premise_short": c_short_strategy_premise,
        "eq_core_short": c_short_eq_core,
        "early_confirmation_short": c_short_confirmation_ok,
        "no_opposite_eq_long": not eq_long_15m and not eq_long_1h,
        "not_higher_tf_exhausted": not short_h1_exhausted and not short_h4_exhausted,
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
