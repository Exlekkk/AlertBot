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


def _trend_side(label: str) -> int:
    if label in ("bull", "lean_bull"):
        return 1
    if label in ("bear", "lean_bear"):
        return -1
    return 0


def _trend_strength(label: str) -> int:
    if label == "bull":
        return 2
    if label == "lean_bull":
        return 1
    if label == "lean_bear":
        return -1
    if label == "bear":
        return -2
    return 0


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


def _build_htf_context(trend_1d: str, trend_4h: str, trend_1h: str) -> dict:
    d1_side = _trend_side(trend_1d)
    h4_side = _trend_side(trend_4h)
    h1_side = _trend_side(trend_1h)

    h4_strength = _trend_strength(trend_4h)
    h1_strength = _trend_strength(trend_1h)

    aligned_long = h1_side > 0 and h4_side > 0
    aligned_short = h1_side < 0 and h4_side < 0

    soft_long = (h1_side > 0 and h4_side == 0) or (h4_side > 0 and h1_side == 0)
    soft_short = (h1_side < 0 and h4_side == 0) or (h4_side < 0 and h1_side == 0)

    conflict = h1_side * h4_side == -1
    conflict_resolved_long = conflict and d1_side > 0
    conflict_resolved_short = conflict and d1_side < 0

    if aligned_long:
        long_display = "bull" if h1_strength >= 2 and h4_strength >= 2 else "lean_bull"
    elif soft_long or conflict_resolved_long:
        long_display = "lean_bull"
    else:
        long_display = "neutral"

    if aligned_short:
        short_display = "bear" if h1_strength <= -2 and h4_strength <= -2 else "lean_bear"
    elif soft_short or conflict_resolved_short:
        short_display = "lean_bear"
    else:
        short_display = "neutral"

    return {
        # A类只接受 1h + 4h 明确同向
        "allow_a_long": aligned_long,
        "allow_a_short": aligned_short,
        # B/C 允许：同向、单边中性、冲突但被1d裁决
        "allow_b_long": aligned_long or soft_long or conflict_resolved_long,
        "allow_b_short": aligned_short or soft_short or conflict_resolved_short,
        "allow_c_long": aligned_long or soft_long or conflict_resolved_long,
        "allow_c_short": aligned_short or soft_short or conflict_resolved_short,
        "long_display": long_display,
        "short_display": short_display,
    }


def _tai_hard_ice_block(latest: dict) -> bool:
    tai_value = latest.get("tai_value")
    tai_p20 = latest.get("tai_p20")
    tai_floor = latest.get("tai_floor")
    tai_rising = latest.get("tai_rising", False)

    if tai_value is None or tai_p20 is None or tai_floor is None:
        return bool(latest.get("tai_is_icepoint", False) and not tai_rising)

    if tai_value >= tai_p20:
        return False

    span = tai_p20 - tai_floor
    if span <= 1e-9:
        return not tai_rising

    # 只有 P20 以下区间最底部 30% 且没有抬升，才算真正冰点禁播
    hard_ice_threshold = tai_floor + span * 0.30
    return tai_value <= hard_ice_threshold and not tai_rising


def _tai_supportive(latest: dict) -> bool:
    if _tai_hard_ice_block(latest):
        return False

    tai_value = latest.get("tai_value")
    tai_p20 = latest.get("tai_p20")
    tai_rising = latest.get("tai_rising", False)

    if tai_value is None or tai_p20 is None:
        return not latest.get("tai_is_icepoint", False)

    return tai_value >= tai_p20 or tai_rising


def _pick_best_per_direction(signals: list[dict]) -> list[dict]:
    best_by_direction = {}
    for signal in signals:
        direction = signal["direction"]
        previous = best_by_direction.get(direction)
        if not previous or signal["priority"] < previous["priority"]:
            best_by_direction[direction] = signal
    return sorted(best_by_direction.values(), key=lambda s: s["priority"])


def _push_failed(name: str, failed: list[str], near_miss_signals: list[dict], blocked_counter: Counter):
    if not failed:
        return
    detail = {"candidate": name, "failed_checks": failed}
    if len(failed) <= 2:
        near_miss_signals.append(detail)
    else:
        for reason in failed:
            blocked_counter[f"{name}:{reason}"] += 1


def _evaluate_scored_branch(
    name: str,
    primary_checks: dict[str, bool],
    support_checks: dict[str, tuple[bool, int]],
    min_support_score: int,
    near_miss_signals: list[dict],
    blocked_counter: Counter,
) -> bool:
    primary_failed = [check_name for check_name, ok in primary_checks.items() if not ok]
    if primary_failed:
        _push_failed(name, primary_failed, near_miss_signals, blocked_counter)
        return False

    support_score = sum(weight for ok, weight in support_checks.values() if ok)
    support_failed = [check_name for check_name, (ok, _) in support_checks.items() if not ok]

    if support_score < min_support_score:
        # 差一点的归 near miss，差太多才记 blocked
        gap = min_support_score - support_score
        failed = support_failed[: max(1, min(2, len(support_failed)))] or ["support_score"]
        if gap <= 1:
            near_miss_signals.append(
                {
                    "candidate": name,
                    "failed_checks": failed,
                    "support_score": support_score,
                    "required_score": min_support_score,
                }
            )
        else:
            for reason in failed:
                blocked_counter[f"{name}:{reason}"] += 1
        return False

    return True


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

    htf = _build_htf_context(trend_1d, trend_4h, trend_1h)

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

    tai_hard_block = _tai_hard_ice_block(latest)
    tai_supportive = _tai_supportive(latest)

    recent_4 = klines_15m[-4:]
    b_long_pullback_seen = min(k["low"] for k in recent_4) <= latest["ema10"] + atr * 0.25
    b_short_pullback_seen = max(k["high"] for k in recent_4) >= latest["ema10"] - atr * 0.25

    b_long_reclaim = (
        latest["close"] >= latest["ema10"]
        and latest["close"] > latest["open"]
    )
    b_short_reject = (
        latest["close"] <= latest["ema10"]
        and latest["close"] < latest["open"]
    )

    sss_long_improving = latest["sss_hist"] > prev["sss_hist"]
    sss_short_improving = latest["sss_hist"] < prev["sss_hist"]

    cm_long_supportive = latest["cm_macd_above_signal"] and latest["cm_hist_up"]
    cm_short_supportive = (not latest["cm_macd_above_signal"]) and latest["cm_hist_down"]

    a_long_trigger = (
        bos_15 == "up"
        or is_bullish_fvg(klines_15m[-10:])
        or latest["fl_buy_signal"]
    )
    a_short_trigger = (
        bos_15 == "down"
        or is_bearish_fvg(klines_15m[-10:])
        or latest["fl_sell_signal"]
    )

    b_long_premise = bullish_structure or is_bullish_fvg(klines_15m[-8:]) or near_support
    b_short_premise = bearish_structure or is_bearish_fvg(klines_15m[-8:]) or near_resistance

    c_long_eq_core = latest["sss_bull_div"] or (latest["sss_oversold_warning"] and sss_long_improving)
    c_short_eq_core = latest["sss_bear_div"] or (latest["sss_overbought_warning"] and sss_short_improving)

    c_long_premise = near_support or is_bullish_fvg(klines_15m[-6:]) or latest["fl_buy_signal"]
    c_short_premise = near_resistance or is_bearish_fvg(klines_15m[-6:]) or latest["fl_sell_signal"]

    c_long_price_confirm = latest["close"] > prev["close"] or latest["low"] >= prev["low"]
    c_short_price_confirm = latest["close"] < prev["close"] or latest["high"] <= prev["high"]

    hard_counter_long = latest["sss_bear_div"] and latest["cm_hist_down"] and latest["fl_trend"] < 0
    hard_counter_short = latest["sss_bull_div"] and latest["cm_hist_up"] and latest["fl_trend"] > 0

    signals = []
    near_miss_signals = []
    blocked_counter: Counter = Counter()

    # =========================
    # A类：高周期顺势已成立，15m只找顺势突破触发
    # =========================
    a_long_primary = {
        "htf_a_long_allowed": htf["allow_a_long"],
        "not_hard_icepoint": not tai_hard_block,
        "15m_breakout_trigger": a_long_trigger,
    }
    a_long_support = {
        "15m_bullish_structure": (bullish_structure, 1),
        "ema_supportive": (latest["close"] > latest["ema20"] and latest["ema10"] > latest["ema20"], 1),
        "fl_supportive": (latest["fl_trend"] == 1 or latest["fl_buy_signal"], 1),
        "cm_supportive": (cm_long_supportive, 1),
        "rar_trend_not_weak": (latest["rar_trend_strong"], 1),
        "no_sss_bear_div": (not latest["sss_bear_div"], 1),
        "no_sss_overbought_warning": (not latest["sss_overbought_warning"], 1),
        "not_too_far_from_ema20": ((latest["close"] - latest["ema20"]) < atr * 1.4, 1),
        "tai_supportive": (tai_supportive, 1),
        "no_hard_counterflow": (not hard_counter_long, 1),
    }
    if _evaluate_scored_branch("A_LONG", a_long_primary, a_long_support, 4, near_miss_signals, blocked_counter):
        signals.append(
            {
                "signal": "A_LONG",
                "symbol": symbol,
                "timeframe": "15m",
                "priority": SIGNAL_PRIORITY["A_LONG"],
                "direction": "long",
                "price": latest["close"],
                "trend_1h": htf["long_display"],
                "status": "active",
                "atr": atr,
            }
        )

    a_short_primary = {
        "htf_a_short_allowed": htf["allow_a_short"],
        "not_hard_icepoint": not tai_hard_block,
        "15m_breakdown_trigger": a_short_trigger,
    }
    a_short_support = {
        "15m_bearish_structure": (bearish_structure, 1),
        "ema_supportive": (latest["close"] < latest["ema20"] and latest["ema10"] < latest["ema20"], 1),
        "fl_supportive": (latest["fl_trend"] == -1 or latest["fl_sell_signal"], 1),
        "cm_supportive": (cm_short_supportive, 1),
        "rar_trend_not_weak": (latest["rar_trend_strong"], 1),
        "no_sss_bull_div": (not latest["sss_bull_div"], 1),
        "no_sss_oversold_warning": (not latest["sss_oversold_warning"], 1),
        "not_too_far_from_ema20": ((latest["ema20"] - latest["close"]) < atr * 1.4, 1),
        "tai_supportive": (tai_supportive, 1),
        "no_hard_counterflow": (not hard_counter_short, 1),
    }
    if _evaluate_scored_branch("A_SHORT", a_short_primary, a_short_support, 4, near_miss_signals, blocked_counter):
        signals.append(
            {
                "signal": "A_SHORT",
                "symbol": symbol,
                "timeframe": "15m",
                "priority": SIGNAL_PRIORITY["A_SHORT"],
                "direction": "short",
                "price": latest["close"],
                "trend_1h": htf["short_display"],
                "status": "active",
                "atr": atr,
            }
        )

    # =========================
    # B类：高周期方向有效，15m只找回踩/反弹后的更优承接
    # =========================
    b_long_primary = {
        "htf_b_long_allowed": htf["allow_b_long"],
        "not_hard_icepoint": not tai_hard_block,
        "15m_smc_premise_long": b_long_premise,
        "pullback_then_reclaim": b_long_pullback_seen and b_long_reclaim,
    }
    b_long_support = {
        "close_above_ema20": (latest["close"] > latest["ema20"], 1),
        "fl_not_bearish": (latest["fl_trend"] >= 0, 1),
        "cm_supportive": (cm_long_supportive, 1),
        "rar_trend_not_weak": (latest["rar_trend_strong"], 1),
        "not_too_far_from_ema10": ((latest["close"] - latest["ema10"]) < atr * 0.9, 1),
        "tai_supportive": (tai_supportive, 1),
        "no_strong_sss_contradiction": (not (latest["sss_bear_div"] and latest["cm_hist_down"]), 1),
        "near_support": (near_support, 1),
    }
    if _evaluate_scored_branch("B_PULLBACK_LONG", b_long_primary, b_long_support, 2, near_miss_signals, blocked_counter):
        signals.append(
            {
                "signal": "B_PULLBACK_LONG",
                "symbol": symbol,
                "timeframe": "15m",
                "priority": SIGNAL_PRIORITY["B_PULLBACK_LONG"],
                "direction": "long",
                "price": latest["close"],
                "trend_1h": htf["long_display"],
                "status": "active",
                "atr": atr,
            }
        )

    b_short_primary = {
        "htf_b_short_allowed": htf["allow_b_short"],
        "not_hard_icepoint": not tai_hard_block,
        "15m_smc_premise_short": b_short_premise,
        "pullback_then_reject": b_short_pullback_seen and b_short_reject,
    }
    b_short_support = {
        "close_below_ema20": (latest["close"] < latest["ema20"], 1),
        "fl_not_bullish": (latest["fl_trend"] <= 0, 1),
        "cm_supportive": (cm_short_supportive, 1),
        "rar_trend_not_weak": (latest["rar_trend_strong"], 1),
        "not_too_far_from_ema10": ((latest["ema10"] - latest["close"]) < atr * 0.9, 1),
        "tai_supportive": (tai_supportive, 1),
        "no_strong_sss_contradiction": (not (latest["sss_bull_div"] and latest["cm_hist_up"]), 1),
        "near_resistance": (near_resistance, 1),
    }
    if _evaluate_scored_branch("B_PULLBACK_SHORT", b_short_primary, b_short_support, 2, near_miss_signals, blocked_counter):
        signals.append(
            {
                "signal": "B_PULLBACK_SHORT",
                "symbol": symbol,
                "timeframe": "15m",
                "priority": SIGNAL_PRIORITY["B_PULLBACK_SHORT"],
                "direction": "short",
                "price": latest["close"],
                "trend_1h": htf["short_display"],
                "status": "active",
                "atr": atr,
            }
        )

    # =========================
    # C类：高周期允许观察，15m只负责给早期预警
    # =========================
    c_long_primary = {
        "htf_c_long_allowed": htf["allow_c_long"],
        "not_hard_icepoint": not tai_hard_block,
        "15m_strategy_premise_long": c_long_premise,
        "eq_core_long": c_long_eq_core,
    }
    c_long_support = {
        "price_confirm": (c_long_price_confirm, 1),
        "cm_not_weakening": (latest["cm_hist_up"] or latest["cm_macd_above_signal"], 1),
        "fl_not_bearish": (latest["fl_trend"] >= 0 or latest["fl_buy_signal"], 1),
        "rar_trend_not_weak": (latest["rar_trend_strong"], 1),
        "tai_supportive": (tai_supportive, 1),
    }
    if _evaluate_scored_branch("C_LEFT_LONG", c_long_primary, c_long_support, 1, near_miss_signals, blocked_counter):
        signals.append(
            {
                "signal": "C_LEFT_LONG",
                "symbol": symbol,
                "timeframe": "15m",
                "priority": SIGNAL_PRIORITY["C_LEFT_LONG"],
                "direction": "long",
                "price": latest["close"],
                "trend_1h": htf["long_display"],
                "status": "early",
                "atr": atr,
            }
        )

    c_short_primary = {
        "htf_c_short_allowed": htf["allow_c_short"],
        "not_hard_icepoint": not tai_hard_block,
        "15m_strategy_premise_short": c_short_premise,
        "eq_core_short": c_short_eq_core,
    }
    c_short_support = {
        "price_confirm": (c_short_price_confirm, 1),
        "cm_not_weakening": (latest["cm_hist_down"] or (not latest["cm_macd_above_signal"]), 1),
        "fl_not_bullish": (latest["fl_trend"] <= 0 or latest["fl_sell_signal"], 1),
        "rar_trend_not_weak": (latest["rar_trend_strong"], 1),
        "tai_supportive": (tai_supportive, 1),
    }
    if _evaluate_scored_branch("C_LEFT_SHORT", c_short_primary, c_short_support, 1, near_miss_signals, blocked_counter):
        signals.append(
            {
                "signal": "C_LEFT_SHORT",
                "symbol": symbol,
                "timeframe": "15m",
                "priority": SIGNAL_PRIORITY["C_LEFT_SHORT"],
                "direction": "short",
                "price": latest["close"],
                "trend_1h": htf["short_display"],
                "status": "early",
                "atr": atr,
            }
        )

    return {
        "signals": _pick_best_per_direction(signals),
        "near_miss_signals": near_miss_signals,
        "blocked_reasons": dict(blocked_counter),
    }
