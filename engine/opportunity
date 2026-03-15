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


def _long_components(h4_prev: dict, h4_last: dict, h1_prev: dict, h1_last: dict, m15_prev: dict, m15_last: dict) -> dict:
    rar_thin = h1_last["rar_trend_strong"] or h1_last["rar_spread"] < h1_prev["rar_spread"]
    rar_turn = _cross_up(h1_last["rar_value"], h1_last["rar_trigger"], h1_prev["rar_value"], h1_prev["rar_trigger"])

    eq_cross = _cross_up(
        h1_last["sss_macd_line"], h1_last["sss_signal_line"], h1_prev["sss_macd_line"], h1_prev["sss_signal_line"]
    )
    eq_hist_up = _rising(h1_last["sss_hist"], h1_prev["sss_hist"])
    eq_div = bool(h1_last["sss_bull_div"])
    eq_div_region = bool(h1_last["sss_oversold_warning"]) or h1_last["sss_zscore"] < -1.0

    ult_cross = bool(h1_last["cm_macd_above_signal"] and not h1_prev["cm_macd_above_signal"])
    ult_hist_up = bool(h1_last["cm_hist_up"] or h1_last["cm_hist"] > h1_prev["cm_hist"])

    h1_price_ok = h1_last["close"] >= h1_last["ema20"] and h1_last["close"] >= h1_last["ema120"] * 0.995
    h1_not_bearish = h1_last["close"] >= h1_last["ema120"] * 0.99

    h4_ok = _h4_long_support(h4_last)
    h4_not_opposed = not _h4_short_support(h4_last)

    m15_ok = (
        m15_last["close"] >= m15_last["ema20"]
        or m15_last["sss_hist"] >= m15_prev["sss_hist"]
        or m15_last["cm_hist"] >= m15_prev["cm_hist"]
        or m15_last["close"] >= m15_last["ema120"]
    )

    score = sum(
        [
            1 if rar_thin or rar_turn else 0,
            1 if eq_cross or eq_hist_up else 0,
            1 if ult_cross or ult_hist_up else 0,
            1 if h1_price_ok else 0,
            1 if m15_ok else 0,
        ]
    )

    if h4_ok and h1_price_ok and m15_ok and (eq_div or eq_div_region) and (eq_cross or ult_cross):
        level = 4
    elif h4_ok and score >= 4 and (eq_cross or ult_cross or rar_turn):
        level = 3
    elif h4_ok and h1_not_bearish and score >= 3:
        level = 2
    elif h4_not_opposed and score >= 3:
        level = 1
    else:
        level = 0

    return {
        "level": level,
        "rar_signal": rar_thin or rar_turn,
        "eq_signal": eq_cross or eq_hist_up,
        "ult_signal": ult_cross or ult_hist_up,
        "eq_div": eq_div or eq_div_region,
        "h4_ok": h4_ok,
        "m15_ok": m15_ok,
        "signature": f"L{level}:rar{int(rar_thin or rar_turn)}:eq{int(eq_cross or eq_hist_up)}:ult{int(ult_cross or ult_hist_up)}:div{int(eq_div or eq_div_region)}",
    }


def _short_components(h4_prev: dict, h4_last: dict, h1_prev: dict, h1_last: dict, m15_prev: dict, m15_last: dict) -> dict:
    rar_thin = h1_last["rar_trend_strong"] or h1_last["rar_spread"] < h1_prev["rar_spread"]
    rar_turn = _cross_down(h1_last["rar_value"], h1_last["rar_trigger"], h1_prev["rar_value"], h1_prev["rar_trigger"])

    eq_cross = _cross_down(
        h1_last["sss_macd_line"], h1_last["sss_signal_line"], h1_prev["sss_macd_line"], h1_prev["sss_signal_line"]
    )
    eq_hist_down = _falling(h1_last["sss_hist"], h1_prev["sss_hist"])
    eq_div = bool(h1_last["sss_bear_div"])
    eq_div_region = bool(h1_last["sss_overbought_warning"]) or h1_last["sss_zscore"] > 1.0

    ult_cross = bool((not h1_last["cm_macd_above_signal"]) and h1_prev["cm_macd_above_signal"])
    ult_hist_down = bool(h1_last["cm_hist_down"] or h1_last["cm_hist"] < h1_prev["cm_hist"])

    h1_price_ok = h1_last["close"] <= h1_last["ema20"] and h1_last["close"] <= h1_last["ema120"] * 1.005
    h1_not_bullish = h1_last["close"] <= h1_last["ema120"] * 1.01

    h4_ok = _h4_short_support(h4_last)
    h4_not_opposed = not _h4_long_support(h4_last)

    m15_ok = (
        m15_last["close"] <= m15_last["ema20"]
        or m15_last["sss_hist"] <= m15_prev["sss_hist"]
        or m15_last["cm_hist"] <= m15_prev["cm_hist"]
        or m15_last["close"] <= m15_last["ema120"]
    )

    score = sum(
        [
            1 if rar_thin or rar_turn else 0,
            1 if eq_cross or eq_hist_down else 0,
            1 if ult_cross or ult_hist_down else 0,
            1 if h1_price_ok else 0,
            1 if m15_ok else 0,
        ]
    )

    if h4_ok and h1_price_ok and m15_ok and (eq_div or eq_div_region) and (eq_cross or ult_cross):
        level = 4
    elif h4_ok and score >= 4 and (eq_cross or ult_cross or rar_turn):
        level = 3
    elif h4_ok and h1_not_bullish and score >= 3:
        level = 2
    elif h4_not_opposed and score >= 3:
        level = 1
    else:
        level = 0

    return {
        "level": level,
        "rar_signal": rar_thin or rar_turn,
        "eq_signal": eq_cross or eq_hist_down,
        "ult_signal": ult_cross or ult_hist_down,
        "eq_div": eq_div or eq_div_region,
        "h4_ok": h4_ok,
        "m15_ok": m15_ok,
        "signature": f"L{level}:rar{int(rar_thin or rar_turn)}:eq{int(eq_cross or eq_hist_down)}:ult{int(ult_cross or ult_hist_down)}:div{int(eq_div or eq_div_region)}",
    }


def _build_text(direction: str) -> str:
    title = "🕶开单机会｜做多" if direction == "long" else "🕶开单机会｜做空"
    return f"{title}\n请注意实盘，留意入场机会。"


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

    if long_level == short_level and long_level > 0:
        return []

    if long_level > short_level:
        level = long_level
        direction = "long"
        ctx = long_ctx
    else:
        level = short_level
        direction = "short"
        ctx = short_ctx

    return [
        {
            "signal": f"OPENING_WATCH_{direction.upper()}",
            "symbol": symbol,
            "direction": direction,
            "level": level,
            "signature": ctx["signature"],
            "text": _build_text(direction),
        }
    ]
