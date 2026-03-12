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
            k["close"] >= k["ema20"],
            k["close"] >= k["ema120"],
            k["close"] >= k["ema169"],
            k["ema10"] >= k["ema20"],
            k["ema20"] >= k["ema120"],
            k["ema120"] >= k["ema169"],
            bos == "up" or mss == "up",
            higher_highs_lows(klines, structure_len),
        ]
    )
    bear_score = sum(
        [
            k["close"] <= k["ema20"],
            k["close"] <= k["ema120"],
            k["close"] <= k["ema169"],
            k["ema10"] <= k["ema20"],
            k["ema20"] <= k["ema120"],
            k["ema120"] <= k["ema169"],
            bos == "down" or mss == "down",
            lower_highs_lows(klines, structure_len),
        ]
    )

    if bull_score >= 6:
        return "bull"
    if bear_score >= 6:
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


def _register_candidate_result(
    name: str,
    main_checks: dict[str, bool],
    hard_block_reasons: list[str],
    support_score: int,
    near_miss_signals: list[dict],
    blocked_counter: Counter,
) -> bool:
    failed_main = [check_name for check_name, ok in main_checks.items() if not ok]
    if failed_main:
        detail = {
            "candidate": name,
            "kind": "main_failed",
            "failed_checks": failed_main,
        }
        if len(failed_main) <= 2:
            near_miss_signals.append(detail)
        else:
            for reason in failed_main:
                blocked_counter[f"{name}:{reason}"] += 1
        return False

    if hard_block_reasons:
        near_miss_signals.append(
            {
                "candidate": name,
                "kind": "hard_block",
                "support_score": support_score,
                "failed_checks": hard_block_reasons,
            }
        )
        for reason in hard_block_reasons:
            blocked_counter[f"{name}:{reason}"] += 1
        return False

    return True


def _build_signal(signal: str, symbol: str, direction: str, price: float, trend_display: str, atr: float, status: str) -> dict:
    return {
        "signal": signal,
        "symbol": symbol,
        "timeframe": "15m",
        "priority": SIGNAL_PRIORITY[signal],
        "direction": direction,
        "price": price,
        "trend_1h": trend_display,
        "status": status,
        "atr": atr,
    }


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

    bullish_fvg_recent = is_bullish_fvg(recent_6)
    bearish_fvg_recent = is_bearish_fvg(recent_6)

    near_resistance = bool(
        piv_h and abs(klines_15m[piv_h[-1]]["high"] - latest["close"]) <= atr * 0.55
    )
    near_support = bool(
        piv_l and abs(latest["close"] - klines_15m[piv_l[-1]]["low"]) <= atr * 0.55
    )

    tai_ok = not latest["tai_is_icepoint"]

    recent_6_lows = min(k["low"] for k in recent_6)
    recent_6_highs = max(k["high"] for k in recent_6)

    b_long_pullback_seen = near_support or recent_6_lows <= latest["ema20"] + atr * 0.45
    b_short_pullback_seen = near_resistance or recent_6_highs >= latest["ema20"] - atr * 0.45

    b_long_reaccept = (
        latest["close"] >= latest["ema10"]
        or latest["close"] > prev["high"]
        or bullish_structure
        or latest["fl_buy_signal"]
    )
    b_short_reaccept = (
        latest["close"] <= latest["ema10"]
        or latest["close"] < prev["low"]
        or bearish_structure
        or latest["fl_sell_signal"]
    )

    sss_long_improving = latest["sss_hist"] > prev["sss_hist"]
    sss_short_improving = latest["sss_hist"] < prev["sss_hist"]

    cm_long_supportive = latest["cm_macd_above_signal"] and latest["cm_hist_up"]
    cm_short_supportive = (not latest["cm_macd_above_signal"]) and latest["cm_hist_down"]

    a_long_trigger = (
        bos_15 == "up"
        or bullish_fvg_recent
        or (mss_15 == "up" and latest["close"] >= prev["high"])
    )
    a_short_trigger = (
        bos_15 == "down"
        or bearish_fvg_recent
        or (mss_15 == "down" and latest["close"] <= prev["low"])
    )

    c_long_eq_core = latest["sss_bull_div"] or (latest["sss_oversold_warning"] and sss_long_improving)
    c_short_eq_core = latest["sss_bear_div"] or (latest["sss_overbought_warning"] and sss_short_improving)

    c_long_left_setup = near_support or bullish_fvg_recent or mss_15 == "up"
    c_short_left_setup = near_resistance or bearish_fvg_recent or mss_15 == "down"

    c_long_price_stabilizing = latest["close"] > prev["close"] or latest["low"] >= prev["low"]
    c_short_price_stabilizing = latest["close"] < prev["close"] or latest["high"] <= prev["high"]

    signals = []
    near_miss_signals = []
    blocked_counter: Counter = Counter()

    # A类：高周期顺势已成立，15m 只负责突破/延续触发
    a_long_support_score = _count_true(
        latest["fl_trend"] == 1 or latest["fl_buy_signal"],
        cm_long_supportive,
        latest["rar_trend_strong"],
        latest["close"] >= latest["ema20"],
    )
    a_long_hard_block = [
        reason
        for reason, cond in [
            ("deep_tai_freeze", latest["tai_is_icepoint"]),
            ("eq_bear_div", latest["sss_bear_div"]),
            ("eq_overbought", latest["sss_overbought_warning"]),
            ("cm_downshift", latest["cm_hist_down"] and not latest["cm_macd_above_signal"]),
            ("fl_reverse", latest["fl_trend"] == -1),
            ("lost_ema20", latest["close"] < latest["ema20"]),
        ]
        if cond
    ]
    if a_long_support_score >= 2 and "lost_ema20" in a_long_hard_block:
        a_long_hard_block.remove("lost_ema20")
    if len(a_long_hard_block) < 3:
        a_long_hard_block = []

    a_long_main = {
        "regime_allows_long": allow_long,
        "tai_ok": tai_ok,
        "high_tf_bullish": _is_bullish_label(trend_display_long),
        "smc_trigger_long": a_long_trigger,
        "structure_long": bullish_structure or higher_highs_lows(klines_15m, 8),
    }
    if _register_candidate_result("A_LONG", a_long_main, a_long_hard_block, a_long_support_score, near_miss_signals, blocked_counter):
        signals.append(_build_signal("A_LONG", symbol, "long", latest["close"], trend_display_long, atr, "active"))

    a_short_support_score = _count_true(
        latest["fl_trend"] == -1 or latest["fl_sell_signal"],
        cm_short_supportive,
        latest["rar_trend_strong"],
        latest["close"] <= latest["ema20"],
    )
    a_short_hard_block = [
        reason
        for reason, cond in [
            ("deep_tai_freeze", latest["tai_is_icepoint"]),
            ("eq_bull_div", latest["sss_bull_div"]),
            ("eq_oversold", latest["sss_oversold_warning"]),
            ("cm_upshift", latest["cm_hist_up"] and latest["cm_macd_above_signal"]),
            ("fl_reverse", latest["fl_trend"] == 1),
            ("lost_ema20", latest["close"] > latest["ema20"]),
        ]
        if cond
    ]
    if a_short_support_score >= 2 and "lost_ema20" in a_short_hard_block:
        a_short_hard_block.remove("lost_ema20")
    if len(a_short_hard_block) < 3:
        a_short_hard_block = []

    a_short_main = {
        "regime_allows_short": allow_short,
        "tai_ok": tai_ok,
        "high_tf_bearish": _is_bearish_label(trend_display_short),
        "smc_trigger_short": a_short_trigger,
        "structure_short": bearish_structure or lower_highs_lows(klines_15m, 8),
    }
    if _register_candidate_result("A_SHORT", a_short_main, a_short_hard_block, a_short_support_score, near_miss_signals, blocked_counter):
        signals.append(_build_signal("A_SHORT", symbol, "short", latest["close"], trend_display_short, atr, "active"))

    # B类：高周期先给方向，15m 负责回踩/反弹后的重新接回
    b_long_support_score = _count_true(
        latest["fl_trend"] >= 0,
        latest["cm_hist_up"] or latest["cm_macd_above_signal"],
        latest["rar_trend_strong"],
        latest["close"] >= latest["ema20"],
    )
    b_long_hard_block = [
        reason
        for reason, cond in [
            ("deep_tai_freeze", latest["tai_is_icepoint"]),
            ("eq_bear_div", latest["sss_bear_div"]),
            ("cm_reject_down", latest["cm_hist_down"] and not latest["cm_macd_above_signal"]),
            ("fl_reverse", latest["fl_trend"] == -1 and latest["fl_sell_signal"]),
            ("full_bear_structure", bearish_structure and latest["close"] < latest["ema20"]),
        ]
        if cond
    ]
    if len(b_long_hard_block) < 3:
        b_long_hard_block = []

    b_long_main = {
        "regime_allows_long": allow_long,
        "tai_ok": tai_ok,
        "high_tf_bullish": _is_bullish_label(trend_display_long),
        "smc_context_long": bullish_structure or is_bullish_fvg(recent_8) or near_support,
        "pullback_seen": b_long_pullback_seen,
        "reaccept_after_pullback": b_long_reaccept,
    }
    if _register_candidate_result("B_PULLBACK_LONG", b_long_main, b_long_hard_block, b_long_support_score, near_miss_signals, blocked_counter):
        signals.append(_build_signal("B_PULLBACK_LONG", symbol, "long", latest["close"], trend_display_long, atr, "active"))

    b_short_support_score = _count_true(
        latest["fl_trend"] <= 0,
        latest["cm_hist_down"] or (not latest["cm_macd_above_signal"]),
        latest["rar_trend_strong"],
        latest["close"] <= latest["ema20"],
    )
    b_short_hard_block = [
        reason
        for reason, cond in [
            ("deep_tai_freeze", latest["tai_is_icepoint"]),
            ("eq_bull_div", latest["sss_bull_div"]),
            ("cm_reject_up", latest["cm_hist_up"] and latest["cm_macd_above_signal"]),
            ("fl_reverse", latest["fl_trend"] == 1 and latest["fl_buy_signal"]),
            ("full_bull_structure", bullish_structure and latest["close"] > latest["ema20"]),
        ]
        if cond
    ]
    if len(b_short_hard_block) < 3:
        b_short_hard_block = []

    b_short_main = {
        "regime_allows_short": allow_short,
        "tai_ok": tai_ok,
        "high_tf_bearish": _is_bearish_label(trend_display_short),
        "smc_context_short": bearish_structure or is_bearish_fvg(recent_8) or near_resistance,
        "pullback_seen": b_short_pullback_seen,
        "reaccept_after_pullback": b_short_reaccept,
    }
    if _register_candidate_result("B_PULLBACK_SHORT", b_short_main, b_short_hard_block, b_short_support_score, near_miss_signals, blocked_counter):
        signals.append(_build_signal("B_PULLBACK_SHORT", symbol, "short", latest["close"], trend_display_short, atr, "active"))

    # C类：高周期允许观察，15m 出左侧预警，EQ 为核心
    c_long_support_score = _count_true(
        latest["fl_trend"] >= 0 or latest["fl_buy_signal"],
        latest["cm_hist_up"] or latest["cm_macd_above_signal"],
        latest["close"] >= latest["ema120"],
        latest["tai_rising"],
    )
    c_long_hard_block = [
        reason
        for reason, cond in [
            ("deep_tai_freeze", latest["tai_is_icepoint"]),
            ("bearish_structure_pressure", bearish_structure and not near_support),
            ("cm_downshift", latest["cm_hist_down"] and not latest["cm_macd_above_signal"]),
            ("fl_reverse", latest["fl_trend"] == -1 and latest["fl_sell_signal"]),
        ]
        if cond
    ]
    if len(c_long_hard_block) < 2:
        c_long_hard_block = []

    c_long_main = {
        "regime_allows_long": allow_long,
        "tai_ok": tai_ok,
        "left_setup_long": c_long_left_setup,
        "eq_core_long": c_long_eq_core,
        "price_stabilizing": c_long_price_stabilizing,
    }
    if _register_candidate_result("C_LEFT_LONG", c_long_main, c_long_hard_block, c_long_support_score, near_miss_signals, blocked_counter):
        signals.append(_build_signal("C_LEFT_LONG", symbol, "long", latest["close"], trend_display_long, atr, "early"))

    c_short_support_score = _count_true(
        latest["fl_trend"] <= 0 or latest["fl_sell_signal"],
        latest["cm_hist_down"] or (not latest["cm_macd_above_signal"]),
        latest["close"] <= latest["ema120"],
        latest["tai_rising"],
    )
    c_short_hard_block = [
        reason
        for reason, cond in [
            ("deep_tai_freeze", latest["tai_is_icepoint"]),
            ("bullish_structure_pressure", bullish_structure and not near_resistance),
            ("cm_upshift", latest["cm_hist_up"] and latest["cm_macd_above_signal"]),
            ("fl_reverse", latest["fl_trend"] == 1 and latest["fl_buy_signal"]),
        ]
        if cond
    ]
    if len(c_short_hard_block) < 2:
        c_short_hard_block = []

    c_short_main = {
        "regime_allows_short": allow_short,
        "tai_ok": tai_ok,
        "left_setup_short": c_short_left_setup,
        "eq_core_short": c_short_eq_core,
        "price_stabilizing": c_short_price_stabilizing,
    }
    if _register_candidate_result("C_LEFT_SHORT", c_short_main, c_short_hard_block, c_short_support_score, near_miss_signals, blocked_counter):
        signals.append(_build_signal("C_LEFT_SHORT", symbol, "short", latest["close"], trend_display_short, atr, "early"))

    return {
        "signals": _pick_best_per_direction(signals),
        "near_miss_signals": near_miss_signals,
        "blocked_reasons": dict(blocked_counter),
    }
