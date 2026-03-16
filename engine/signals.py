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


def _is_bullish_bias(label: str) -> bool:
    return label in ("bull", "lean_bull")


def _is_bearish_bias(label: str) -> bool:
    return label in ("bear", "lean_bear")


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
    return bool(k.get("sss_bear_div")) or (bool(k.get("sss_overbought_warning")) and sss_rollover and cm_rollover)


def _short_exhausted(k: dict, prev_k: dict | None = None) -> bool:
    sss_rebound = prev_k is not None and float(k.get("sss_hist", 0.0)) > float(prev_k.get("sss_hist", 0.0))
    cm_rebound = prev_k is not None and float(k.get("cm_hist", 0.0)) > float(prev_k.get("cm_hist", 0.0))
    return bool(k.get("sss_bull_div")) or (bool(k.get("sss_oversold_warning")) and sss_rebound and cm_rebound)


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


def _long_regime_state(trend_1d: str, trend_4h: str, trend_1h: str, k_4h: dict, k_1h: dict, prev_1h: dict) -> str:
    if _down_pressure(k_1h):
        return "blocked"
    if _long_overheat(k_1h, prev_1h):
        return "weak" if trend_4h in ("bull", "lean_bull") else "blocked"

    if trend_4h == "bull" and trend_1h in ("bull", "lean_bull"):
        return "strong"
    if trend_4h == "lean_bull" and trend_1h == "bull":
        return "strong"

    if (
        trend_4h in ("bull", "lean_bull")
        and trend_1h in ("bull", "lean_bull")
        and trend_1d in ("bull", "lean_bull", "neutral")
        and not _down_pressure(k_4h)
    ):
        return "weak"
    if (
        trend_4h in ("bull", "lean_bull")
        and trend_1h == "neutral"
        and trend_1d in ("bull", "lean_bull")
        and not _down_pressure(k_4h)
    ):
        return "weak"

    return "blocked"


def _short_regime_state(trend_1d: str, trend_4h: str, trend_1h: str, k_4h: dict, k_1h: dict, prev_1h: dict) -> str:
    if _up_pressure(k_1h):
        return "blocked"
    if _short_exhausted(k_1h, prev_1h):
        return "weak" if trend_4h in ("bear", "lean_bear") else "blocked"

    if trend_4h == "bear" and trend_1h in ("bear", "lean_bear"):
        return "strong"
    if trend_4h == "lean_bear" and trend_1h == "bear":
        return "strong"

    if trend_4h in ("bear", "lean_bear") and trend_1h == "neutral" and trend_1d in ("bear", "lean_bear") and not _up_pressure(k_4h):
        return "weak"
    if trend_4h in ("neutral", "lean_bull", "lean_bear") and trend_1h in ("bear", "lean_bear") and _down_pressure(k_1h):
        return "weak"
    if trend_4h == "bull" and trend_1h == "bear" and trend_1d != "bull" and _down_pressure(k_1h):
        return "weak"

    return "blocked"


def _tai_heat_state(k: dict) -> str:
    value = float(k.get("tai_value", 0.0))
    p20 = float(k.get("tai_p20", 0.0))
    floor = float(k.get("tai_floor", 0.0))
    extreme_cutoff = floor + (p20 - floor) * 0.30
    if value <= extreme_cutoff:
        return "extreme_cold"
    if value <= p20:
        return "cold"
    return "normal"


def _b_long_htf_allowed(regime_long_state: str, trend_1d: str, trend_4h: str, trend_1h: str, k_4h: dict, k_1h: dict, prev_1h: dict) -> bool:
    if regime_long_state == "strong":
        return True
    if regime_long_state != "weak":
        return False

    return (
        trend_4h in ("bull", "lean_bull")
        and trend_1h in ("bull", "lean_bull", "neutral")
        and trend_1d in ("bull", "lean_bull", "neutral")
        and not _down_pressure(k_1h)
        and not _long_overheat(k_1h, prev_1h)
        and (
            k_1h["close"] >= k_1h["ema20"]
            or (k_1h["close"] >= k_1h["ema120"] and k_1h["ema20"] >= k_1h["ema120"])
        )
    )


def _b_short_htf_allowed(regime_short_state: str, trend_1d: str, trend_4h: str, trend_1h: str, k_4h: dict, k_1h: dict, prev_1h: dict) -> bool:
    if regime_short_state == "strong":
        return True
    if regime_short_state != "weak":
        return False

    return (
        trend_1h in ("bear", "lean_bear")
        and _down_pressure(k_1h)
        and not _short_exhausted(k_1h, prev_1h)
        and trend_4h not in ("bull",)
    ) or (
        trend_4h in ("bear", "lean_bear")
        and trend_1d in ("bear", "lean_bear", "neutral")
        and k_1h["close"] <= k_1h["ema20"]
        and not _up_pressure(k_4h)
    )


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

    k_4h = klines_4h[-1]
    p_4h = klines_4h[-2]
    k_1h = klines_1h[-1]
    p_1h = klines_1h[-2]

    regime_long_state = _long_regime_state(trend_1d, trend_4h, trend_1h, k_4h, k_1h, p_1h)
    regime_short_state = _short_regime_state(trend_1d, trend_4h, trend_1h, k_4h, k_1h, p_1h)

    allow_long_strong = regime_long_state == "strong"
    allow_long_weak = regime_long_state in ("strong", "weak")
    allow_short_strong = regime_short_state == "strong"
    allow_short_weak = regime_short_state in ("strong", "weak")

    trend_display_long = "bull" if regime_long_state == "strong" else "lean_bull" if regime_long_state == "weak" else "neutral"
    trend_display_short = "bear" if regime_short_state == "strong" else "lean_bear" if regime_short_state == "weak" else "neutral"

    latest = klines_15m[-1]
    prev = klines_15m[-2]
    atr = latest["atr"]
    tai_heat = _tai_heat_state(latest)
    tai_extreme_cold = tai_heat == "extreme_cold" and not latest["tai_rising"]

    piv_h, piv_l = find_pivots(klines_15m)
    bos_15 = detect_last_bos(klines_15m, piv_h, piv_l)
    mss_15 = detect_last_mss(klines_15m, piv_h, piv_l)

    bullish_structure = bos_15 == "up" or mss_15 == "up"
    bearish_structure = bos_15 == "down" or mss_15 == "down"

    recent_6 = klines_15m[-6:]
    recent_8 = klines_15m[-8:]
    recent_12 = klines_15m[-12:]
    bullish_fvg_recent = is_bullish_fvg(recent_6)
    bearish_fvg_recent = is_bearish_fvg(recent_6)

    near_resistance = bool(piv_h and abs(klines_15m[piv_h[-1]]["high"] - latest["close"]) < atr * 0.45)
    near_support = bool(piv_l and abs(latest["close"] - klines_15m[piv_l[-1]]["low"]) < atr * 0.45)

    recent_6_lows = min(k["low"] for k in recent_6)
    recent_6_highs = max(k["high"] for k in recent_6)
    prior_break_high = max(k["high"] for k in recent_12[:-1]) if len(recent_12) > 1 else prev["high"]
    prior_break_low = min(k["low"] for k in recent_12[:-1]) if len(recent_12) > 1 else prev["low"]

    b_long_pullback_seen = recent_6_lows <= latest["ema10"] + atr * 0.35 or near_support
    b_short_pullback_seen = recent_6_highs >= latest["ema10"] - atr * 0.35 or near_resistance

    b_long_reclaim = (
        latest["close"] >= latest["ema10"] - atr * 0.12
        and latest["low"] >= latest["ema20"] - atr * 0.20
        and (
            latest["close"] > latest["open"]
            or latest["close"] >= prev["close"]
            or latest["close"] >= prior_break_high - atr * 0.20
        )
    )
    b_short_reject = (
        latest["close"] <= latest["ema10"] + atr * 0.12
        and latest["high"] <= latest["ema20"] + atr * 0.20
        and (
            latest["close"] < latest["open"]
            or latest["close"] <= prev["close"]
            or latest["close"] <= prior_break_low + atr * 0.20
        )
    )

    sss_long_improving = latest["sss_hist"] > prev["sss_hist"]
    sss_short_improving = latest["sss_hist"] < prev["sss_hist"]

    cm_long_supportive = latest["cm_macd_above_signal"] and latest["cm_hist_up"]
    cm_short_supportive = (not latest["cm_macd_above_signal"]) and latest["cm_hist_down"]

    cm_long_not_bad = latest["cm_macd_above_signal"] or latest["cm_hist_up"]
    cm_short_not_bad = (not latest["cm_macd_above_signal"]) or latest["cm_hist_down"]

    a_long_breakout = (
        (bos_15 == "up" or mss_15 == "up")
        and latest["close"] > prev["close"]
        and latest["high"] >= prior_break_high - atr * 0.10
        and latest["close"] >= latest["ema10"]
    )
    a_short_breakdown = (
        (bos_15 == "down" or mss_15 == "down")
        and latest["close"] < prev["close"]
        and latest["low"] <= prior_break_low + atr * 0.10
        and latest["close"] <= latest["ema10"]
    )

    c_long_eq_core = latest["sss_bull_div"] or (latest["sss_oversold_warning"] and sss_long_improving)
    c_short_eq_core = latest["sss_bear_div"] or (latest["sss_overbought_warning"] and sss_short_improving)

    c_long_strategy_premise = near_support or bullish_fvg_recent or latest["fl_buy_signal"] or mss_15 == "up"
    c_short_strategy_premise = near_resistance or bearish_fvg_recent or latest["fl_sell_signal"] or mss_15 == "down"

    c_long_price_confirm = latest["close"] > prev["close"] or latest["low"] >= prev["low"]
    c_short_price_confirm = latest["close"] < prev["close"] or latest["high"] <= prev["high"]

    b_long_htf_allowed = _b_long_htf_allowed(regime_long_state, trend_1d, trend_4h, trend_1h, k_4h, k_1h, p_1h)
    b_short_htf_allowed = _b_short_htf_allowed(regime_short_state, trend_1d, trend_4h, trend_1h, k_4h, k_1h, p_1h)

    long_m15_overheat = _long_overheat(latest, prev)
    short_m15_exhausted = _short_exhausted(latest, prev)
    long_h1_overheat = _long_overheat(k_1h, p_1h)
    short_h1_exhausted = _short_exhausted(k_1h, p_1h)
    long_h4_overheat = _long_overheat(k_4h, p_4h)
    short_h4_exhausted = _short_exhausted(k_4h, p_4h)

    b_long_eq_soft_block = (
        bool(latest.get("sss_bear_div"))
        or bool(k_1h.get("sss_bear_div"))
        or (
            bool(latest.get("sss_overbought_warning"))
            and bool(k_1h.get("sss_overbought_warning"))
            and float(latest.get("sss_hist", 0.0)) < float(prev.get("sss_hist", 0.0))
            and float(k_1h.get("sss_hist", 0.0)) < float(p_1h.get("sss_hist", 0.0))
        )
    )
    b_short_eq_soft_block = (
        bool(latest.get("sss_bull_div"))
        or bool(k_1h.get("sss_bull_div"))
        or (
            bool(latest.get("sss_oversold_warning"))
            and bool(k_1h.get("sss_oversold_warning"))
            and float(latest.get("sss_hist", 0.0)) > float(prev.get("sss_hist", 0.0))
            and float(k_1h.get("sss_hist", 0.0)) > float(p_1h.get("sss_hist", 0.0))
        )
    )

    signals = []
    near_miss_signals = []
    blocked_counter: Counter = Counter()

    # A 类：只保留真正的强顺势突破，不能再让 FVG/BOS 一碰就报 A。
    a_long_secondary_ok = (
        cm_long_supportive
        and latest["rar_trend_strong"]
        and not latest["sss_bear_div"]
        and not latest["sss_overbought_warning"]
        and (latest["fl_trend"] >= 0 or latest["fl_buy_signal"])
    )
    a_long_strong_contra = _count_true(
        latest["sss_bear_div"],
        latest["sss_overbought_warning"],
        latest["cm_hist_down"],
        latest["fl_trend"] == -1,
        long_h1_overheat,
        long_h4_overheat,
    ) >= 2

    a_long_checks = {
        "htf_a_long_allowed": allow_long_strong,
        "15m_breakout_trigger": a_long_breakout,
        "bullish_structure": bullish_structure,
        "ema_supportive": latest["ema10"] >= latest["ema20"] and latest["close"] >= latest["ema10"],
        "h1_momentum_supportive": k_1h["close"] >= k_1h["ema20"] and k_1h["ema10"] >= k_1h["ema20"] and _momentum_up(k_1h),
        "h4_not_overheat": not long_h4_overheat,
        "not_eq_overheat_long": not long_m15_overheat and not long_h1_overheat,
        "not_too_far_from_ema20": (latest["close"] - latest["ema20"]) <= atr * 0.95,
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

    a_short_secondary_ok = (
        cm_short_supportive
        and latest["rar_trend_strong"]
        and not latest["sss_bull_div"]
        and not latest["sss_oversold_warning"]
        and (latest["fl_trend"] <= 0 or latest["fl_sell_signal"])
    )
    a_short_strong_contra = _count_true(
        latest["sss_bull_div"],
        latest["sss_oversold_warning"],
        latest["cm_hist_up"],
        latest["fl_trend"] == 1,
        short_h1_exhausted,
        short_h4_exhausted,
    ) >= 2

    a_short_checks = {
        "htf_a_short_allowed": allow_short_strong,
        "15m_breakdown_trigger": a_short_breakdown,
        "bearish_structure": bearish_structure,
        "ema_supportive": latest["ema10"] <= latest["ema20"] and latest["close"] <= latest["ema10"],
        "h1_momentum_supportive": k_1h["close"] <= k_1h["ema20"] and k_1h["ema10"] <= k_1h["ema20"] and _momentum_down(k_1h),
        "h4_not_exhausted": not short_h4_exhausted,
        "not_eq_exhausted_short": not short_m15_exhausted and not short_h1_exhausted,
        "not_too_far_from_ema20": (latest["ema20"] - latest["close"]) <= atr * 0.95,
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

    # B 类：仍允许顺大级别回踩/反弹，但必须保留 15m 结构与 1h 健康度。
    b_long_secondary_ok = _count_true(
        latest["fl_trend"] >= 0,
        cm_long_not_bad,
        not latest["sss_bear_div"],
        latest["rar_trend_strong"],
    ) >= 2
    b_long_strong_contra = (
        _count_true(
            latest["sss_bear_div"],
            k_1h["sss_bear_div"],
            latest["cm_hist_down"] and (not latest["cm_macd_above_signal"]),
            latest["fl_trend"] == -1,
            k_1h["close"] < k_1h["ema20"],
        ) >= 2
    )

    b_long_checks = {
        "htf_b_long_allowed": b_long_htf_allowed,
        "15m_smc_premise_long": bullish_structure or is_bullish_fvg(recent_8) or near_support,
        "pullback_seen": b_long_pullback_seen,
        "pullback_then_reclaim": b_long_reclaim,
        "ema_not_lost": latest["close"] >= latest["ema20"] or (latest["ema10"] >= latest["ema20"] and latest["close"] >= latest["ema10"]),
        "not_eq_overheat_long": not b_long_eq_soft_block,
        "not_too_far_from_ema10": abs(latest["close"] - latest["ema10"]) <= atr * 1.35,
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
    ) >= 2
    b_short_strong_contra = (
        _count_true(
            latest["sss_bull_div"],
            k_1h["sss_bull_div"],
            latest["cm_hist_up"] and latest["cm_macd_above_signal"],
            latest["fl_trend"] == 1,
            k_1h["close"] > k_1h["ema20"],
        ) >= 2
    )

    b_short_checks = {
        "htf_b_short_allowed": b_short_htf_allowed,
        "15m_smc_premise_short": bearish_structure or is_bearish_fvg(recent_8) or near_resistance,
        "pullback_seen": b_short_pullback_seen,
        "pullback_then_reject": b_short_reject,
        "ema_not_lost": latest["close"] <= latest["ema20"] or (latest["ema10"] <= latest["ema20"] and latest["close"] <= latest["ema10"]),
        "not_eq_exhausted_short": not b_short_eq_soft_block,
        "not_too_far_from_ema10": abs(latest["ema10"] - latest["close"]) <= atr * 1.35,
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

    # C 类：必须真有左侧 EQ 核心，且 15m/1h 不能已经进入明显反向衰减。
    c_long_confirmation_ok = _count_true(
        c_long_price_confirm,
        latest["fl_trend"] >= 0 or latest["fl_buy_signal"],
        latest["cm_hist_up"] or latest["cm_macd_above_signal"],
    ) >= 2
    c_long_early_signal_ok = _count_true(
        c_long_eq_core,
        c_long_price_confirm,
        latest["fl_trend"] >= 0 or latest["fl_buy_signal"],
        latest["cm_hist_up"] or latest["cm_macd_above_signal"],
        bullish_structure or bullish_fvg_recent or mss_15 == "up",
    ) >= 4

    c_long_checks = {
        "htf_c_long_allowed": allow_long_weak,
        "tai_not_extreme_cold": not tai_extreme_cold,
        "15m_strategy_premise_long": c_long_strategy_premise,
        "eq_core_long": c_long_eq_core,
        "not_eq_overheat_long": not long_m15_overheat and not long_h1_overheat,
        "not_h4_overheat_long": not long_h4_overheat,
        "no_opposite_eq_short": not latest["sss_bear_div"] and not latest["sss_overbought_warning"],
        "no_opposite_cm_short": not (latest["cm_hist_down"] and not latest["cm_macd_above_signal"]),
        "early_signal_long": c_long_early_signal_ok,
        "early_confirmation_long": c_long_confirmation_ok,
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
    ) >= 2
    c_short_early_signal_ok = _count_true(
        c_short_eq_core,
        c_short_price_confirm,
        latest["fl_trend"] <= 0 or latest["fl_sell_signal"],
        latest["cm_hist_down"] or (not latest["cm_macd_above_signal"]),
        bearish_structure or bearish_fvg_recent or mss_15 == "down",
    ) >= 4

    c_short_checks = {
        "htf_c_short_allowed": allow_short_weak,
        "tai_not_extreme_cold": not tai_extreme_cold,
        "15m_strategy_premise_short": c_short_strategy_premise,
        "eq_core_short": c_short_eq_core,
        "not_eq_exhausted_short": not short_m15_exhausted and not short_h1_exhausted,
        "not_h4_exhausted_short": not short_h4_exhausted,
        "no_opposite_eq_long": not latest["sss_bull_div"] and not latest["sss_oversold_warning"],
        "no_opposite_cm_long": not (latest["cm_hist_up"] and latest["cm_macd_above_signal"]),
        "early_signal_short": c_short_early_signal_ok,
        "early_confirmation_short": c_short_confirmation_ok,
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
