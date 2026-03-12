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


def _last_two_values(klines: list[dict], indexes: list[int], field: str) -> tuple[float | None, float | None]:
    if len(indexes) >= 2:
        return klines[indexes[-2]][field], klines[indexes[-1]][field]
    if len(indexes) == 1:
        return None, klines[indexes[-1]][field]
    return None, None


def detect_last_bos(klines: list[dict], pivot_highs: list[int], pivot_lows: list[int]) -> str:
    if len(klines) < 2:
        return "none"

    close = klines[-1]["close"]
    last_pivot_high = klines[pivot_highs[-1]]["high"] if pivot_highs else None
    last_pivot_low = klines[pivot_lows[-1]]["low"] if pivot_lows else None

    if last_pivot_high is not None and close > last_pivot_high:
        return "up"
    if last_pivot_low is not None and close < last_pivot_low:
        return "down"
    return "none"


def detect_last_mss(klines: list[dict], pivot_highs: list[int], pivot_lows: list[int]) -> str:
    if len(klines) < 10:
        return "none"

    prev_high, last_high = _last_two_values(klines, pivot_highs, "high")
    prev_low, last_low = _last_two_values(klines, pivot_lows, "low")
    close = klines[-1]["close"]

    had_lower_highs = prev_high is not None and last_high is not None and last_high < prev_high
    had_lower_lows = prev_low is not None and last_low is not None and last_low < prev_low
    had_higher_highs = prev_high is not None and last_high is not None and last_high > prev_high
    had_higher_lows = prev_low is not None and last_low is not None and last_low > prev_low

    if had_lower_highs and had_lower_lows and last_high is not None and close > last_high:
        return "up"
    if had_higher_highs and had_higher_lows and last_low is not None and close < last_low:
        return "down"
    return "none"


def higher_highs_lows(klines: list[dict], length: int = 10) -> bool:
    segment = klines[-max(length, 6):]
    pivot_highs, pivot_lows = find_pivots(segment)
    if len(pivot_highs) >= 2 and len(pivot_lows) >= 2:
        return (
            segment[pivot_highs[-1]]["high"] > segment[pivot_highs[-2]]["high"]
            and segment[pivot_lows[-1]]["low"] > segment[pivot_lows[-2]]["low"]
        )
    if len(segment) < 2:
        return False
    return segment[-1]["high"] > segment[0]["high"] and segment[-1]["low"] > segment[0]["low"]


def lower_highs_lows(klines: list[dict], length: int = 10) -> bool:
    segment = klines[-max(length, 6):]
    pivot_highs, pivot_lows = find_pivots(segment)
    if len(pivot_highs) >= 2 and len(pivot_lows) >= 2:
        return (
            segment[pivot_highs[-1]]["high"] < segment[pivot_highs[-2]]["high"]
            and segment[pivot_lows[-1]]["low"] < segment[pivot_lows[-2]]["low"]
        )
    if len(segment) < 2:
        return False
    return segment[-1]["high"] < segment[0]["high"] and segment[-1]["low"] < segment[0]["low"]


def _avg_range(klines: list[dict]) -> float:
    if not klines:
        return 0.0
    return sum(k["high"] - k["low"] for k in klines) / len(klines)


def is_bullish_fvg(klines: list[dict], lookback: int = 5) -> bool:
    if len(klines) < 3:
        return False

    segment = klines[-max(lookback, 3):]
    min_gap = _avg_range(segment) * 0.10

    for i in range(2, len(segment)):
        a = segment[i - 2]
        c = segment[i]
        gap = c["low"] - a["high"]
        if gap > 0 and gap >= min_gap:
            return True
    return False


def is_bearish_fvg(klines: list[dict], lookback: int = 5) -> bool:
    if len(klines) < 3:
        return False

    segment = klines[-max(lookback, 3):]
    min_gap = _avg_range(segment) * 0.10

    for i in range(2, len(segment)):
        a = segment[i - 2]
        c = segment[i]
        gap = a["low"] - c["high"]
        if gap > 0 and gap >= min_gap:
            return True
    return False
