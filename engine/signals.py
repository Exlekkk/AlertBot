from engine.structure import (
    detect_last_bos,
    detect_last_mss,
    find_pivots,
    higher_highs_lows,
    is_bearish_fvg,
    is_bullish_fvg,
    lower_highs_lows,
)


def classify_4h_trend(klines_4h: list[dict]) -> str:
    pivot_highs, pivot_lows = find_pivots(klines_4h)
    bos = detect_last_bos(klines_4h, pivot_highs, pivot_lows)
    k = klines_4h[-1]

    bull_score = sum(
        [
            k["close"] > k["ema120"],
            k["ema10"] > k["ema20"],
            k["ema20"] > k["ema120"],
            bos == "up",
        ]
    )
    bear_score = sum(
        [
            k["close"] < k["ema120"],
            k["ema10"] < k["ema20"],
            k["ema20"] < k["ema120"],
            bos == "down",
        ]
    )
    if bull_score >= 2:
        return "bull"
    if bear_score >= 2:
        return "bear"
    return "neutral"


def classify_1h_trend(klines_1h: list[dict]) -> str:
    pivot_highs, pivot_lows = find_pivots(klines_1h)
    bos = detect_last_bos(klines_1h, pivot_highs, pivot_lows)
    mss = detect_last_mss(klines_1h, pivot_highs, pivot_lows)
    k = klines_1h[-1]

    bull_score = sum(
        [
            k["close"] > k["ema20"],
            k["ema10"] > k["ema20"],
            k["ema20"] > k["ema120"],
            (bos == "up" or mss == "up"),
            higher_highs_lows(klines_1h, 10),
        ]
    )
    bear_score = sum(
        [
            k["close"] < k["ema20"],
            k["ema10"] < k["ema20"],
            k["ema20"] < k["ema120"],
            (bos == "down" or mss == "down"),
            lower_highs_lows(klines_1h, 10),
        ]
    )

    if bull_score >= 3:
        return "bull"
    if bear_score >= 3:
        return "bear"
    if bull_score > bear_score:
        return "lean_bull"
    if bear_score > bull_score:
        return "lean_bear"
    return "neutral"


def _volume_expanded(last_two_15m: list[dict]) -> bool:
    return any(k["volume"] > k["vol_sma20"] * 1.3 for k in last_two_15m)


def _sideways_filter(klines_15m: list[dict]) -> bool:
    recent = klines_15m[-12:]
    if len(recent) < 12:
        return False
    highs = max(k["high"] for k in recent)
    lows = min(k["low"] for k in recent)
    range_pct = (highs - lows) / max(lows, 1e-9)
    ema_tight = abs(recent[-1]["ema10"] - recent[-1]["ema20"]) < recent[-1]["atr"] * 0.15
    weak_volume = sum(k["volume"] < k["vol_sma20"] * 0.9 for k in recent) >= 8
    return range_pct < 0.01 and ema_tight and weak_volume


def detect_signals(symbol: str, klines_4h: list[dict], klines_1h: list[dict], klines_15m: list[dict]) -> list[dict]:
    trend_4h = classify_4h_trend(klines_4h)
    trend_1h = classify_1h_trend(klines_1h)
    piv_h, piv_l = find_pivots(klines_15m)
    bos_15 = detect_last_bos(klines_15m, piv_h, piv_l)
    mss_15 = detect_last_mss(klines_15m, piv_h, piv_l)
    latest = klines_15m[-1]
    last2 = klines_15m[-2:]
    atr = latest["atr"]
    sideways = _sideways_filter(klines_15m)

    bullish_structure = bos_15 == "up" or mss_15 == "up"
    bearish_structure = bos_15 == "down" or mss_15 == "down"
    vol_ok = _volume_expanded(last2)

    near_resistance = piv_h and abs(klines_15m[piv_h[-1]]["high"] - latest["close"]) < atr * 0.4
    near_support = piv_l and abs(latest["close"] - klines_15m[piv_l[-1]]["low"]) < atr * 0.4

    signals = []

    if (
        trend_4h != "bear"
        and trend_1h == "bull"
        and bullish_structure
        and vol_ok
        and (bos_15 == "up" or is_bullish_fvg(klines_15m[-10:]))
        and not near_resistance
        and not sideways
    ):
        signals.append(
            {
                "signal": "A_LONG",
                "symbol": symbol,
                "timeframe": "15m",
                "context": "1h偏多 / 4h不空",
                "trigger": "MSS上破 + 放量确认" if mss_15 == "up" else "BOS上破 + 放量确认",
                "priority": 1,
            }
        )

    if (
        trend_4h != "bull"
        and trend_1h == "bear"
        and bearish_structure
        and vol_ok
        and (bos_15 == "down" or is_bearish_fvg(klines_15m[-10:]))
        and not near_support
        and not sideways
    ):
        signals.append(
            {
                "signal": "A_SHORT",
                "symbol": symbol,
                "timeframe": "15m",
                "context": "1h偏空 / 4h不多",
                "trigger": "MSS下破 + 放量确认" if mss_15 == "down" else "BOS下破 + 放量确认",
                "priority": 1,
            }
        )

    # v1 近似实现: B 类
    if trend_4h != "bear" and trend_1h in ("bull", "lean_bull") and latest["volume"] >= latest["vol_sma20"] * 0.8:
        if latest["close"] > latest["ema20"] and not bearish_structure and not sideways:
            signals.append(
                {
                    "signal": "B_PULLBACK_LONG",
                    "symbol": symbol,
                    "timeframe": "15m",
                    "context": "1h偏多(或中性偏多) / 4h不空",
                    "trigger": "回踩后站回EMA20",
                    "priority": 2,
                }
            )

    if trend_4h != "bull" and trend_1h in ("bear", "lean_bear") and latest["volume"] >= latest["vol_sma20"] * 0.8:
        if latest["close"] < latest["ema20"] and not bullish_structure and not sideways:
            signals.append(
                {
                    "signal": "B_PULLBACK_SHORT",
                    "symbol": symbol,
                    "timeframe": "15m",
                    "context": "1h偏空(或中性偏空) / 4h不多",
                    "trigger": "反抽后跌回EMA20下方",
                    "priority": 2,
                }
            )

    # v1 近似实现: C 类
    macd_seq = [k["macd_hist"] for k in klines_15m[-6:]]
    if len(macd_seq) >= 4 and macd_seq[-4] < macd_seq[-3] < macd_seq[-2] < macd_seq[-1] and trend_1h != "bear":
        signals.append(
            {
                "signal": "C_LEFT_LONG",
                "symbol": symbol,
                "timeframe": "15m",
                "context": "左侧预警 / 动能衰减",
                "trigger": "MACD柱体连续收敛",
                "priority": 3,
            }
        )

    if len(macd_seq) >= 4 and macd_seq[-4] > macd_seq[-3] > macd_seq[-2] > macd_seq[-1] and trend_1h != "bull":
        signals.append(
            {
                "signal": "C_LEFT_SHORT",
                "symbol": symbol,
                "timeframe": "15m",
                "context": "左侧预警 / 动能衰减",
                "trigger": "MACD柱体连续收敛",
                "priority": 3,
            }
        )

    signals.sort(key=lambda s: s["priority"])
    return signals
