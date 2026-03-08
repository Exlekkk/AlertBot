def ema(values: list[float], period: int) -> list[float]:
    if not values:
        return []
    k = 2 / (period + 1)
    out = [values[0]]
    for value in values[1:]:
        out.append(value * k + out[-1] * (1 - k))
    return out


def atr(klines: list[dict], period: int = 14) -> list[float]:
    if not klines:
        return []
    tr = [klines[0]["high"] - klines[0]["low"]]
    for i in range(1, len(klines)):
        high = klines[i]["high"]
        low = klines[i]["low"]
        prev_close = klines[i - 1]["close"]
        tr.append(max(high - low, abs(high - prev_close), abs(low - prev_close)))
    return ema(tr, period)


def sma(values: list[float], period: int) -> list[float]:
    out = []
    s = 0.0
    for i, v in enumerate(values):
        s += v
        if i >= period:
            s -= values[i - period]
        out.append(s / min(i + 1, period))
    return out


def macd_hist(values: list[float]) -> list[float]:
    fast = ema(values, 12)
    slow = ema(values, 26)
    macd_line = [f - s for f, s in zip(fast, slow)]
    signal = ema(macd_line, 9)
    return [m - s for m, s in zip(macd_line, signal)]


def enrich_klines(klines: list[dict]) -> list[dict]:
    closes = [k["close"] for k in klines]
    volumes = [k["volume"] for k in klines]

    ema10 = ema(closes, 10)
    ema20 = ema(closes, 20)
    ema120 = ema(closes, 120)
    ema169 = ema(closes, 169)
    atr14 = atr(klines, 14)
    vol20 = sma(volumes, 20)
    macd = macd_hist(closes)

    enriched = []
    for i, k in enumerate(klines):
        item = dict(k)
        item.update(
            {
                "ema10": ema10[i],
                "ema20": ema20[i],
                "ema120": ema120[i],
                "ema169": ema169[i],
                "atr": atr14[i],
                "vol_sma20": vol20[i],
                "macd_hist": macd[i],
            }
        )
        enriched.append(item)
    return enriched
