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


def _long_components(h4_prev: dict, h4_last: dict, h1_prev: dict, h1_last: dict, m15_prev: dict, m15_last: dict) -> dict:
    rar_signal = h1_last["rar_trend_strong"] or h1_last["rar_spread"] < h1_prev["rar_spread"] or _cross_up(
        h1_last["rar_value"], h1_last["rar_trigger"], h1_prev["rar_value"], h1_prev["rar_trigger"]
    )
    eq_signal = _cross_up(
        h1_last["sss_macd_line"], h1_last["sss_signal_line"], h1_prev["sss_macd_line"], h1_prev["sss_signal_line"]
    ) or _rising(h1_last["sss_hist"], h1_prev["sss_hist"])
    ult_signal = bool(
        (h1_last["cm_macd_above_signal"] and not h1_prev["cm_macd_above_signal"])
        or h1_last["cm_hist_up"]
        or h1_last["cm_hist"] > h1_prev["cm_hist"]
    )

    h4_ok = _h4_long_support(h4_last)
    h1_ok = h1_last["close"] >= h1_last["ema20"] and h1_last["ema10"] >= h1_last["ema20"]
    h1_overheat = _long_overheat(h1_last, h1_prev)
    m15_overheat = _long_overheat(m15_last, m15_prev)

    # 15m 这里只做否决，不再让它反客为主。
    m15_veto = m15_overheat or (
        float(m15_last.get("sss_hist", 0.0)) < float(m15_prev.get("sss_hist", 0.0))
        and float(m15_last.get("cm_hist", 0.0)) < float(m15_prev.get("cm_hist", 0.0))
        and m15_last["close"] < m15_last["ema10"]
    )

    score = sum([rar_signal, eq_signal, ult_signal, h4_ok, h1_ok])
    if h4_ok and h1_ok and not h1_overheat and not m15_veto and score >= 4:
        level = 3 if (eq_signal and ult_signal) else 2
    else:
        level = 0

    return {
        "level": level,
        "signature": f"L{level}:rar{int(rar_signal)}:eq{int(eq_signal)}:ult{int(ult_signal)}:veto{int(m15_veto or h1_overheat)}",
    }


def _short_components(h4_prev: dict, h4_last: dict, h1_prev: dict, h1_last: dict, m15_prev: dict, m15_last: dict) -> dict:
    rar_signal = h1_last["rar_trend_strong"] or h1_last["rar_spread"] < h1_prev["rar_spread"] or _cross_down(
        h1_last["rar_value"], h1_last["rar_trigger"], h1_prev["rar_value"], h1_prev["rar_trigger"]
    )
    eq_signal = _cross_down(
        h1_last["sss_macd_line"], h1_last["sss_signal_line"], h1_prev["sss_macd_line"], h1_prev["sss_signal_line"]
    ) or _falling(h1_last["sss_hist"], h1_prev["sss_hist"])
    ult_signal = bool(
        ((not h1_last["cm_macd_above_signal"]) and h1_prev["cm_macd_above_signal"])
        or h1_last["cm_hist_down"]
        or h1_last["cm_hist"] < h1_prev["cm_hist"]
    )

    h4_ok = _h4_short_support(h4_last)
    h1_ok = h1_last["close"] <= h1_last["ema20"] and h1_last["ema10"] <= h1_last["ema20"]
    h1_exhausted = _short_exhausted(h1_last, h1_prev)
    m15_exhausted = _short_exhausted(m15_last, m15_prev)

    m15_veto = m15_exhausted or (
        float(m15_last.get("sss_hist", 0.0)) > float(m15_prev.get("sss_hist", 0.0))
        and float(m15_last.get("cm_hist", 0.0)) > float(m15_prev.get("cm_hist", 0.0))
        and m15_last["close"] > m15_last["ema10"]
    )

    score = sum([rar_signal, eq_signal, ult_signal, h4_ok, h1_ok])
    if h4_ok and h1_ok and not h1_exhausted and not m15_veto and score >= 4:
        level = 3 if (eq_signal and ult_signal) else 2
    else:
        level = 0

    return {
        "level": level,
        "signature": f"L{level}:rar{int(rar_signal)}:eq{int(eq_signal)}:ult{int(ult_signal)}:veto{int(m15_veto or h1_exhausted)}",
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
