def find_pivots(klines: list[dict], left: int = 2, right: int = 2) -> tuple[list[int], list[int]]:
    pivot_highs = []
    pivot_lows = []
    for i in range(left, len(klines) - right):
        high = klines[i]["high"]
        low = klines[i]["low"]

        if all(high > klines[j]["high"] for j in range(i - left, i)) and all(
            high > klines[j]["high"] for j in range(i + 1, i + right + 1)
        ):
            pivot_highs.append(i)

        if all(low < klines[j]["low"] for j in range(i - left, i)) and all(
            low < klines[j]["low"] for j in range(i + 1, i + right + 1)
        ):
            pivot_lows.append(i)
    return pivot_highs, pivot_lows


def detect_last_bos(klines: list[dict], pivot_highs: list[int], pivot_lows: list[int]) -> str:
    if len(klines) < 2:
        return "none"

    recent_closes = [k["close"] for k in klines[-3:]]
    last_pivot_high = klines[pivot_highs[-1]]["high"] if pivot_highs else None
    last_pivot_low = klines[pivot_lows[-1]]["low"] if pivot_lows else None

    if last_pivot_high is not None and max(recent_closes) > last_pivot_high:
        return "up"
    if last_pivot_low is not None and min(recent_closes) < last_pivot_low:
        return "down"
    return "none"


def detect_last_mss(klines: list[dict], pivot_highs: list[int], pivot_lows: list[int]) -> str:
    bos = detect_last_bos(klines, pivot_highs, pivot_lows)

    if len(pivot_highs) >= 2 and len(pivot_lows) >= 2:
        prev_high = klines[pivot_highs[-2]]["high"]
        last_high = klines[pivot_highs[-1]]["high"]
        prev_low = klines[pivot_lows[-2]]["low"]
        last_low = klines[pivot_lows[-1]]["low"]

        had_lower_high_low = last_high < prev_high and last_low < prev_low
        had_higher_high_low = last_high > prev_high and last_low > prev_low

        if had_lower_high_low and bos == "up":
            return "up"
        if had_higher_high_low and bos == "down":
            return "down"

    if len(klines) < 20:
        return "none"

    early_close = klines[-20]["close"]
    latest_close = klines[-1]["close"]
    trend_before = "up" if latest_close > early_close else "down"

    if trend_before == "down" and bos == "up":
        return "up"
    if trend_before == "up" and bos == "down":
        return "down"
    return "none"


def higher_highs_lows(klines: list[dict], length: int = 10) -> bool:
    if len(klines) < length:
        return False
    segment = klines[-length:]
    return segment[-1]["high"] > segment[0]["high"] and segment[-1]["low"] > segment[0]["low"]


def lower_highs_lows(klines: list[dict], length: int = 10) -> bool:
    if len(klines) < length:
        return False
    segment = klines[-length:]
    return segment[-1]["high"] < segment[0]["high"] and segment[-1]["low"] < segment[0]["low"]


def is_bullish_fvg(klines: list[dict]) -> bool:
    if len(klines) < 3:
        return False
    a, _, c = klines[-3], klines[-2], klines[-1]
    return c["low"] > a["high"]


def is_bearish_fvg(klines: list[dict]) -> bool:
    if len(klines) < 3:
        return False
    a, _, c = klines[-3], klines[-2], klines[-1]
    return c["high"] < a["low"]
