from __future__ import annotations

from engine.structure import detect_last_bos, detect_last_mss, find_pivots, is_bearish_fvg, is_bullish_fvg


def _cross_up(curr_a: float, curr_b: float, prev_a: float, prev_b: float) -> bool:
    return curr_a > curr_b and prev_a <= prev_b


def _cross_down(curr_a: float, curr_b: float, prev_a: float, prev_b: float) -> bool:
    return curr_a < curr_b and prev_a >= prev_b


def _momentum_up(k: dict) -> bool:
    return bool(k.get("cm_macd_above_signal")) and (
        bool(k.get("cm_hist_up")) or float(k.get("sss_hist", 0.0)) >= 0
    )


def _momentum_down(k: dict) -> bool:
    return (not bool(k.get("cm_macd_above_signal"))) and (
        bool(k.get("cm_hist_down")) or float(k.get("sss_hist", 0.0)) <= 0
    )


def _long_overheat(k: dict, prev_k: dict | None = None) -> bool:
    sss_rollover = prev_k is not None and float(k.get("sss_hist", 0.0)) < float(prev_k.get("sss_hist", 0.0))
    cm_rollover = prev_k is not None and float(k.get("cm_hist", 0.0)) < float(prev_k.get("cm_hist", 0.0))
    return bool(k.get("sss_bear_div")) or bool(k.get("sss_overbought_warning")) or (sss_rollover and cm_rollover)


def _short_exhausted(k: dict, prev_k: dict | None = None) -> bool:
    sss_rebound = prev_k is not None and float(k.get("sss_hist", 0.0)) > float(prev_k.get("sss_hist", 0.0))
    cm_rebound = prev_k is not None and float(k.get("cm_hist", 0.0)) > float(prev_k.get("cm_hist", 0.0))
    return bool(k.get("sss_bull_div")) or bool(k.get("sss_oversold_warning")) or (sss_rebound and cm_rebound)


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


def _classify_trend(klines: list[dict]) -> str:
    if len(klines) < 3:
        return "neutral"
    k = klines[-1]
    if k["close"] > k["ema20"] and k["ema10"] > k["ema20"] and _momentum_up(k):
        if k["close"] > k["ema120"] and k["close"] > k["ema169"]:
            return "bull"
        return "lean_bull"
    if k["close"] < k["ema20"] and k["ema10"] < k["ema20"] and _momentum_down(k):
        if k["close"] < k["ema120"] and k["close"] < k["ema169"]:
            return "bear"
        return "lean_bear"
    return "neutral"


def _direction_regime_score(direction: str, trend_1d: str, trend_4h: str, trend_1h: str, k_4h: dict, p_4h: dict, k_1h: dict, p_1h: dict) -> int:
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


def _build_text(direction: str, level: int) -> str:
    title = "🚨 开单机会｜做多" if direction == "long" else "🚨 开单机会｜做空"
    return f"{title}\n机会等级：L{level}\n请注意实盘，留意入场机会。"


def _recent_high(klines: list[dict], count: int) -> float:
    return max(float(k["high"]) for k in klines[-count:])


def _recent_low(klines: list[dict], count: int) -> float:
    return min(float(k["low"]) for k in klines[-count:])


def _long_components(trend_1d: str, klines_4h: list[dict], klines_1h: list[dict], klines_15m: list[dict]) -> dict:
    h4_prev, h4_last = klines_4h[-2], klines_4h[-1]
    h1_prev, h1_last = klines_1h[-2], klines_1h[-1]
    m15_prev, m15_last = klines_15m[-2], klines_15m[-1]
    trend_4h = _classify_trend(klines_4h)
    trend_1h = _classify_trend(klines_1h)
    regime_score = _direction_regime_score("long", trend_1d, trend_4h, trend_1h, h4_last, h4_prev, h1_last, h1_prev)

    piv_h, piv_l = find_pivots(klines_15m)
    bos_15 = detect_last_bos(klines_15m, piv_h, piv_l)
    mss_15 = detect_last_mss(klines_15m, piv_h, piv_l)
    recent_6 = klines_15m[-6:]
    atr = max(float(m15_last.get("atr", 0.0)), float(m15_last["close"]) * 0.0012)
    near_support = bool(piv_l and abs(float(m15_last["close"]) - float(klines_15m[piv_l[-1]]["low"])) < atr * 0.50) or abs(float(m15_last["close"]) - _recent_low(klines_15m, 8)) < atr * 0.45
    structure = bos_15 == "up" or mss_15 == "up" or is_bullish_fvg(recent_6) or near_support

    eq_div = bool(m15_last.get("sss_bull_div")) or bool(m15_last.get("sss_oversold_warning")) or bool(h1_last.get("sss_bull_div")) or bool(h1_last.get("sss_oversold_warning"))
    eq_cross = _cross_up(
        float(m15_last.get("sss_macd_line", 0.0)),
        float(m15_last.get("sss_signal_line", 0.0)),
        float(m15_prev.get("sss_macd_line", 0.0)),
        float(m15_prev.get("sss_signal_line", 0.0)),
    )
    ult_support = bool(m15_last.get("cm_macd_above_signal")) or bool(m15_last.get("cm_hist_up")) or bool(h1_last.get("cm_macd_above_signal"))
    rar_support = bool(h1_last.get("rar_trend_strong")) or float(h1_last.get("rar_spread", 0.0)) <= float(h1_prev.get("rar_spread", 0.0))
    price_confirm = float(m15_last["close"]) > float(m15_prev["close"]) and float(m15_last["close"]) >= float(m15_last["ema10"])
    veto = _long_overheat(m15_last, m15_prev) or _long_overheat(h1_last, h1_prev) or bool(m15_last.get("sss_bear_div")) or bool(h1_last.get("sss_bear_div"))

    level = 0
    if regime_score >= 5 and structure and price_confirm and not veto and eq_div and eq_cross and ult_support:
        level = 4
    elif regime_score >= 3 and structure and price_confirm and not veto and (eq_div or eq_cross) and (ult_support or rar_support):
        level = 3
    elif regime_score >= 2 and structure and price_confirm and not veto and (eq_div or eq_cross or ult_support or rar_support):
        level = 2
    elif regime_score >= 1 and structure and not veto and (eq_div or eq_cross or ult_support):
        level = 1

    return {
        "level": level,
        "signature": f"L{level}:eq{int(eq_div or eq_cross)}:ult{int(ult_support)}:rar{int(rar_support)}:struct{int(structure)}:veto{int(veto)}",
    }


def _short_components(trend_1d: str, klines_4h: list[dict], klines_1h: list[dict], klines_15m: list[dict]) -> dict:
    h4_prev, h4_last = klines_4h[-2], klines_4h[-1]
    h1_prev, h1_last = klines_1h[-2], klines_1h[-1]
    m15_prev, m15_last = klines_15m[-2], klines_15m[-1]
    trend_4h = _classify_trend(klines_4h)
    trend_1h = _classify_trend(klines_1h)
    regime_score = _direction_regime_score("short", trend_1d, trend_4h, trend_1h, h4_last, h4_prev, h1_last, h1_prev)

    piv_h, piv_l = find_pivots(klines_15m)
    bos_15 = detect_last_bos(klines_15m, piv_h, piv_l)
    mss_15 = detect_last_mss(klines_15m, piv_h, piv_l)
    recent_6 = klines_15m[-6:]
    atr = max(float(m15_last.get("atr", 0.0)), float(m15_last["close"]) * 0.0012)
    near_resistance = bool(piv_h and abs(float(klines_15m[piv_h[-1]]["high"]) - float(m15_last["close"])) < atr * 0.50) or abs(_recent_high(klines_15m, 8) - float(m15_last["close"])) < atr * 0.45
    structure = bos_15 == "down" or mss_15 == "down" or is_bearish_fvg(recent_6) or near_resistance

    eq_div = bool(m15_last.get("sss_bear_div")) or bool(m15_last.get("sss_overbought_warning")) or bool(h1_last.get("sss_bear_div")) or bool(h1_last.get("sss_overbought_warning"))
    eq_cross = _cross_down(
        float(m15_last.get("sss_macd_line", 0.0)),
        float(m15_last.get("sss_signal_line", 0.0)),
        float(m15_prev.get("sss_macd_line", 0.0)),
        float(m15_prev.get("sss_signal_line", 0.0)),
    )
    ult_support = (not bool(m15_last.get("cm_macd_above_signal"))) or bool(m15_last.get("cm_hist_down")) or (not bool(h1_last.get("cm_macd_above_signal")))
    rar_support = bool(h1_last.get("rar_trend_strong")) or float(h1_last.get("rar_spread", 0.0)) <= float(h1_prev.get("rar_spread", 0.0))
    price_confirm = float(m15_last["close"]) < float(m15_prev["close"]) and float(m15_last["close"]) <= float(m15_last["ema10"])
    veto = _short_exhausted(m15_last, m15_prev) or _short_exhausted(h1_last, h1_prev) or bool(m15_last.get("sss_bull_div")) or bool(h1_last.get("sss_bull_div"))

    level = 0
    if regime_score >= 5 and structure and price_confirm and not veto and eq_div and eq_cross and ult_support:
        level = 4
    elif regime_score >= 3 and structure and price_confirm and not veto and (eq_div or eq_cross) and (ult_support or rar_support):
        level = 3
    elif regime_score >= 2 and structure and price_confirm and not veto and (eq_div or eq_cross or ult_support or rar_support):
        level = 2
    elif regime_score >= 1 and structure and not veto and (eq_div or eq_cross or ult_support):
        level = 1

    return {
        "level": level,
        "signature": f"L{level}:eq{int(eq_div or eq_cross)}:ult{int(ult_support)}:rar{int(rar_support)}:struct{int(structure)}:veto{int(veto)}",
    }


def detect_opening_watch(symbol: str, klines_1d: list[dict], klines_4h: list[dict], klines_1h: list[dict], klines_15m: list[dict]) -> list[dict]:
    if len(klines_1d) < 3 or len(klines_4h) < 3 or len(klines_1h) < 3 or len(klines_15m) < 3:
        return []

    trend_1d = _classify_trend(klines_1d)
    long_ctx = _long_components(trend_1d, klines_4h, klines_1h, klines_15m)
    short_ctx = _short_components(trend_1d, klines_4h, klines_1h, klines_15m)

    long_level = long_ctx["level"]
    short_level = short_ctx["level"]

    if long_level <= 0 and short_level <= 0:
        return []
    if long_level == short_level:
        return []

    if long_level > short_level:
        direction = "long"
        level = long_level
        signature = long_ctx["signature"]
    else:
        direction = "short"
        level = short_level
        signature = short_ctx["signature"]

    return [
        {
            "signal": f"OPENING_WATCH_{direction.upper()}",
            "symbol": symbol,
            "direction": direction,
            "level": level,
            "signature": signature,
            "text": _build_text(direction, level),
        }
    ]
