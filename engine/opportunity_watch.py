from __future__ import annotations


def _cross_up(curr_a: float, curr_b: float, prev_a: float, prev_b: float) -> bool:
    return curr_a > curr_b and prev_a <= prev_b


def _cross_down(curr_a: float, curr_b: float, prev_a: float, prev_b: float) -> bool:
    return curr_a < curr_b and prev_a >= prev_b


def _rising(curr: float, prev: float) -> bool:
    return curr > prev


def _falling(curr: float, prev: float) -> bool:
    return curr < prev


def _h4_long_support(k: dict) -> bool:
    return (
        k["close"] >= k["ema20"]
        or (k["ema10"] >= k["ema20"] and k["close"] >= k["ema120"] * 0.995)
        or k["close"] >= k["ema169"]
    )


def _h4_short_support(k: dict) -> bool:
    return (
        k["close"] <= k["ema20"]
        or (k["ema10"] <= k["ema20"] and k["close"] <= k["ema120"] * 1.005)
        or k["close"] <= k["ema169"]
    )


def _long_overheat(k: dict, prev_k: dict) -> bool:
    return bool(k.get("sss_bear_div")) or bool(k.get("sss_overbought_warning")) or (
        float(k.get("sss_hist", 0.0)) < float(prev_k.get("sss_hist", 0.0))
        and float(k.get("cm_hist", 0.0)) < float(prev_k.get("cm_hist", 0.0))
    )


def _short_exhausted(k: dict, prev_k: dict) -> bool:
    return bool(k.get("sss_bull_div")) or bool(k.get("sss_oversold_warning")) or (
        float(k.get("sss_hist", 0.0)) > float(prev_k.get("sss_hist", 0.0))
        and float(k.get("cm_hist", 0.0)) > float(prev_k.get("cm_hist", 0.0))
    )


def _build_text(direction: str) -> str:
    title = "🕶开单机会｜做多" if direction == "long" else "🕶开单机会｜做空"
    return f"{title}\n请注意实盘，留意入场机会。"


def _m15_long_veto(m15_prev: dict, m15_last: dict) -> bool:
    eq_cross_down = _cross_down(
        m15_last["sss_macd_line"],
        m15_last["sss_signal_line"],
        m15_prev["sss_macd_line"],
        m15_prev["sss_signal_line"],
    )
    ult_cross_down = (not m15_last["cm_macd_above_signal"]) and m15_prev["cm_macd_above_signal"]
    dual_rollover = (
        float(m15_last.get("sss_hist", 0.0)) < float(m15_prev.get("sss_hist", 0.0))
        and float(m15_last.get("cm_hist", 0.0)) < float(m15_prev.get("cm_hist", 0.0))
    )
    return bool(
        m15_last.get("sss_bear_div")
        or m15_last.get("sss_overbought_warning")
        or eq_cross_down
        or ult_cross_down
        or (dual_rollover and m15_last["close"] < m15_last["ema10"])
    )


def _m15_short_veto(m15_prev: dict, m15_last: dict) -> bool:
    eq_cross_up = _cross_up(
        m15_last["sss_macd_line"],
        m15_last["sss_signal_line"],
        m15_prev["sss_macd_line"],
        m15_prev["sss_signal_line"],
    )
    ult_cross_up = m15_last["cm_macd_above_signal"] and (not m15_prev["cm_macd_above_signal"])
    dual_rebound = (
        float(m15_last.get("sss_hist", 0.0)) > float(m15_prev.get("sss_hist", 0.0))
        and float(m15_last.get("cm_hist", 0.0)) > float(m15_prev.get("cm_hist", 0.0))
    )
    return bool(
        m15_last.get("sss_bull_div")
        or m15_last.get("sss_oversold_warning")
        or eq_cross_up
        or ult_cross_up
        or (dual_rebound and m15_last["close"] > m15_last["ema10"])
    )


def _long_components(h4_prev: dict, h4_last: dict, h1_prev: dict, h1_last: dict, m15_prev: dict, m15_last: dict) -> dict:
    rar_signal = h1_last["rar_trend_strong"] or h1_last["rar_spread"] < h1_prev["rar_spread"] or _cross_up(
        h1_last["rar_value"], h1_last["rar_trigger"], h1_prev["rar_value"], h1_prev["rar_trigger"]
    )

    eq_cross = _cross_up(
        h1_last["sss_macd_line"], h1_last["sss_signal_line"], h1_prev["sss_macd_line"], h1_prev["sss_signal_line"]
    )
    eq_hist_turn = _rising(h1_last["sss_hist"], h1_prev["sss_hist"]) and float(h1_prev.get("sss_hist", 0.0)) <= 0
    eq_div = bool(h1_last.get("sss_bull_div")) or bool(h1_last.get("sss_oversold_warning"))
    eq_signal = eq_cross or (eq_div and eq_hist_turn)

    ult_cross = bool(h1_last["cm_macd_above_signal"] and not h1_prev["cm_macd_above_signal"])
    ult_hist_turn = bool(h1_last["cm_hist_up"]) and float(h1_prev.get("cm_hist", 0.0)) <= 0
    ult_signal = ult_cross or ult_hist_turn

    h4_ok = _h4_long_support(h4_last) and not _long_overheat(h4_last, h4_prev)
    h1_ok = h1_last["close"] >= h1_last["ema20"] and h1_last["ema10"] >= h1_last["ema20"]
    h1_overheat = _long_overheat(h1_last, h1_prev)
    m15_veto = _m15_long_veto(m15_prev, m15_last)

    level = 0
    if h4_ok and h1_ok and not h1_overheat and not m15_veto and (eq_signal or ult_signal or eq_div):
        if eq_div and eq_cross:
            level = 4
        elif eq_signal and ult_signal:
            level = 3
        elif (eq_signal or ult_signal) and rar_signal:
            level = 2

    return {
        "level": level,
        "signature": f"L{level}:rar{int(rar_signal)}:eq{int(eq_signal)}:ult{int(ult_signal)}:div{int(eq_div)}:veto{int(m15_veto or h1_overheat)}",
    }


def _short_components(h4_prev: dict, h4_last: dict, h1_prev: dict, h1_last: dict, m15_prev: dict, m15_last: dict) -> dict:
    rar_signal = h1_last["rar_trend_strong"] or h1_last["rar_spread"] < h1_prev["rar_spread"] or _cross_down(
        h1_last["rar_value"], h1_last["rar_trigger"], h1_prev["rar_value"], h1_prev["rar_trigger"]
    )

    eq_cross = _cross_down(
        h1_last["sss_macd_line"], h1_last["sss_signal_line"], h1_prev["sss_macd_line"], h1_prev["sss_signal_line"]
    )
    eq_hist_turn = _falling(h1_last["sss_hist"], h1_prev["sss_hist"]) and float(h1_prev.get("sss_hist", 0.0)) >= 0
    eq_div = bool(h1_last.get("sss_bear_div")) or bool(h1_last.get("sss_overbought_warning"))
    eq_signal = eq_cross or (eq_div and eq_hist_turn)

    ult_cross = bool((not h1_last["cm_macd_above_signal"]) and h1_prev["cm_macd_above_signal"])
    ult_hist_turn = bool(h1_last["cm_hist_down"]) and float(h1_prev.get("cm_hist", 0.0)) >= 0
    ult_signal = ult_cross or ult_hist_turn

    h4_ok = _h4_short_support(h4_last) and not _short_exhausted(h4_last, h4_prev)
    h1_ok = h1_last["close"] <= h1_last["ema20"] and h1_last["ema10"] <= h1_last["ema20"]
    h1_exhausted = _short_exhausted(h1_last, h1_prev)
    m15_veto = _m15_short_veto(m15_prev, m15_last)

    level = 0
    if h4_ok and h1_ok and not h1_exhausted and not m15_veto and (eq_signal or ult_signal or eq_div):
        if eq_div and eq_cross:
            level = 4
        elif eq_signal and ult_signal:
            level = 3
        elif (eq_signal or ult_signal) and rar_signal:
            level = 2

    return {
        "level": level,
        "signature": f"L{level}:rar{int(rar_signal)}:eq{int(eq_signal)}:ult{int(ult_signal)}:div{int(eq_div)}:veto{int(m15_veto or h1_exhausted)}",
    }


def detect_opening_watch(symbol: str, klines_4h: list[dict], klines_1h: list[dict], klines_15m: list[dict]) -> list[dict]:
    if len(klines_4h) < 2 or len(klines_1h) < 2 or len(klines_15m) < 2:
        return []

    h4_prev, h4_last = klines_4h[-2], klines_4h[-1]
    h1_prev, h1_last = klines_1h[-2], klines_1h[-1]
    m15_prev, m15_last = klines_15m[-2], klines_15m[-1]

    long_ctx = _long_components(h4_prev, h4_last, h1_prev, h1_last, m15_prev, m15_last)
    short_ctx = _short_components(h4_prev, h4_last, h1_prev, h1_last, m15_prev, m15_last)

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
            "text": _build_text(direction),
        }
    ]
