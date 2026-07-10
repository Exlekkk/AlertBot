from __future__ import annotations

import math
from datetime import datetime, time, timezone
from typing import Any
from zoneinfo import ZoneInfo

from engine.trend_config import TREND_ENGINE_CONFIG


CHART_CONFIG = TREND_ENGINE_CONFIG["chart_framework"]


def _f(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
        if math.isnan(number) or math.isinf(number):
            return default
        return number
    except (TypeError, ValueError):
        return default


def _ordered(low: float, high: float) -> tuple[float, float]:
    return (min(float(low), float(high)), max(float(low), float(high)))


def _distance(price: float, zone: tuple[float, float] | None) -> float | None:
    if zone is None:
        return None
    if zone[0] <= price <= zone[1]:
        return 0.0
    return min(abs(price - zone[0]), abs(price - zone[1]))


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _std(values: list[float]) -> float:
    if not values:
        return 0.0
    mean = _mean(values)
    return math.sqrt(sum((value - mean) ** 2 for value in values) / len(values))


def _sma_at(values: list[float], index: int, length: int) -> float | None:
    if index + 1 < length:
        return None
    return _mean(values[index - length + 1 : index + 1])


def _rma(values: list[float], length: int) -> list[float]:
    """Wilder average used by Pine's ta.atr.

    Early values use the available prefix; after the seed window this follows
    the standard Pine/Wilder recurrence.  Decision code only consumes values
    after the full warm-up.
    """

    if not values:
        return []
    length = max(1, int(length))
    out: list[float] = []
    current = 0.0
    for i, value in enumerate(values):
        value = float(value)
        if i == 0:
            current = value
        elif i < length:
            current = (current * i + value) / (i + 1)
        else:
            current = (current * (length - 1) + value) / length
        out.append(current)
    return out


def atr_series(klines: list[dict[str, Any]], length: int) -> list[float]:
    if not klines:
        return []
    tr: list[float] = []
    for i, bar in enumerate(klines):
        high = _f(bar.get("high"))
        low = _f(bar.get("low"))
        if i == 0:
            tr.append(high - low)
        else:
            prev_close = _f(klines[i - 1].get("close"))
            tr.append(max(high - low, abs(high - prev_close), abs(low - prev_close)))
    return _rma(tr, length)


def _pivot_indices(values: list[float], left: int, right: int, high: bool) -> list[tuple[int, int, float]]:
    """Return (confirmation index, pivot index, value) for closed-bar pivots."""

    out: list[tuple[int, int, float]] = []
    left = max(1, int(left))
    right = max(1, int(right))
    for pivot in range(left, len(values) - right):
        value = values[pivot]
        before = values[pivot - left : pivot]
        after = values[pivot + 1 : pivot + right + 1]
        if high:
            valid = all(value >= item for item in before) and all(value > item for item in after)
        else:
            valid = all(value <= item for item in before) and all(value < item for item in after)
        if valid:
            out.append((pivot + right, pivot, value))
    return out


def build_fibonacci_ote_context(klines: list[dict[str, Any]]) -> dict[str, Any]:
    cfg = CHART_CONFIG["fibonacci_ote"]
    pivot_len = int(cfg["pivot_length"])
    if len(klines) < pivot_len * 2 + 3:
        return {"available": False, "trend": "neutral", "levels": {}, "extension_targets": {}}

    highs = [_f(bar.get("high")) for bar in klines]
    lows = [_f(bar.get("low")) for bar in klines]
    events: list[tuple[int, str, int, float]] = []
    events.extend((confirm, "high", pivot, value) for confirm, pivot, value in _pivot_indices(highs, pivot_len, pivot_len, True))
    events.extend((confirm, "low", pivot, value) for confirm, pivot, value in _pivot_indices(lows, pivot_len, pivot_len, False))
    events.sort(key=lambda item: (item[0], 0 if item[1] == "high" else 1))

    last_high: tuple[float, int] | None = None
    previous_high: tuple[float, int] | None = None
    last_low: tuple[float, int] | None = None
    previous_low: tuple[float, int] | None = None
    trend_state = 0
    anchor_high: tuple[float, int] | None = None
    anchor_low: tuple[float, int] | None = None
    last_shift: tuple[str, int] | None = None

    for confirm, kind, pivot, value in events:
        if kind == "high":
            previous_high = last_high
            last_high = (value, pivot)
            if previous_high and value > previous_high[0] and trend_state <= 0 and last_low:
                trend_state = 1
                anchor_low = last_low
                anchor_high = last_high
                last_shift = ("bullish_shift", confirm)
            elif trend_state == 1 and anchor_high and value > anchor_high[0]:
                anchor_high = last_high
        else:
            previous_low = last_low
            last_low = (value, pivot)
            if previous_low and value < previous_low[0] and trend_state >= 0 and last_high:
                trend_state = -1
                anchor_high = last_high
                anchor_low = last_low
                last_shift = ("bearish_shift", confirm)
            elif trend_state == -1 and anchor_low and value < anchor_low[0]:
                anchor_low = last_low

    if not anchor_high or not anchor_low or anchor_high[0] <= anchor_low[0]:
        return {"available": False, "trend": "neutral", "levels": {}, "extension_targets": {}}

    high_price, high_index = anchor_high
    low_price, low_index = anchor_low
    span = high_price - low_price
    is_bull = trend_state == 1

    def retracement(level: float) -> float:
        return high_price - span * level if is_bull else low_price + span * level

    levels = {str(level): round(retracement(float(level)), 2) for level in cfg["levels"]}
    ote_a = retracement(float(cfg["ote_low"]))
    ote_b = retracement(float(cfg["ote_high"]))
    close = _f(klines[-1].get("close"))
    equilibrium = (high_price + low_price) / 2.0
    extension_targets: dict[str, float] = {}
    for extension in cfg["extensions"]:
        target = low_price + span * float(extension) if is_bull else high_price - span * float(extension)
        extension_targets[str(extension)] = round(target, 2)

    ote_zone = _ordered(ote_a, ote_b)
    shift_name, shift_confirm = last_shift or ("none", -1)
    return {
        "available": True,
        "source": "chartprime_pine_reimplementation",
        "trend": "bull" if is_bull else "bear",
        "trend_state": trend_state,
        "shift_event": shift_name,
        "shift_age_bars": len(klines) - 1 - shift_confirm if shift_confirm >= 0 else None,
        "anchor_high": round(high_price, 2),
        "anchor_low": round(low_price, 2),
        "anchor_high_index": high_index,
        "anchor_low_index": low_index,
        "equilibrium": round(equilibrium, 2),
        "premium_discount": "premium" if close > equilibrium else "discount" if close < equilibrium else "equilibrium",
        "ote_zone": tuple(round(value, 2) for value in ote_zone),
        "in_ote": ote_zone[0] <= close <= ote_zone[1],
        "levels": levels,
        "extension_targets": extension_targets,
    }


def build_log_regression_channel(
    klines: list[dict[str, Any]],
    length: int,
    width: float,
    bins: int,
    extension_bars: int,
) -> dict[str, Any]:
    if len(klines) < length:
        return {"available": False, "length": length, "direction": "neutral"}

    window = klines[-length:]
    reversed_bars = list(reversed(window))
    x_values = [float(i + 1) for i in range(length)]
    y_values = [math.log(max(_f(bar.get("close")), 1e-10)) for bar in reversed_bars]
    sum_x = sum(x_values)
    sum_y = sum(y_values)
    sum_x2 = sum(value * value for value in x_values)
    sum_xy = sum(x * y for x, y in zip(x_values, y_values))
    denominator = length * sum_x2 - sum_x * sum_x
    slope = (length * sum_xy - sum_x * sum_y) / denominator if denominator else 0.0
    intercept = (sum_y - slope * sum_x) / length

    closes = [_f(bar.get("close")) for bar in window]
    deviation = _std(closes)
    reg_start = math.exp(intercept + slope * length)
    reg_end = math.exp(intercept)
    half_width = deviation * float(width)
    upper_end = reg_end + half_width
    lower_end = reg_end - half_width
    close = closes[-1]
    normalized_position = (close - reg_end) / max(half_width, 1e-9)

    buy_volume = sum(_f(bar.get("volume")) for bar in window if _f(bar.get("close")) > _f(bar.get("open")))
    sell_volume = sum(_f(bar.get("volume")) for bar in window if _f(bar.get("close")) < _f(bar.get("open")))
    total_volume = buy_volume + sell_volume
    delta_pct = (buy_volume - sell_volume) / total_volume * 100.0 if total_volume else 0.0

    bin_volumes = [0.0] * max(1, int(bins))
    for offset, bar in enumerate(reversed_bars):
        historical_mid = math.exp(intercept + slope * offset)
        historical_low = historical_mid - half_width
        historical_high = historical_mid + half_width
        bar_close = _f(bar.get("close"))
        if historical_low <= bar_close <= historical_high and historical_high > historical_low:
            step = (historical_high - historical_low) / len(bin_volumes)
            index = int(math.floor((bar_close - historical_low) / step))
            index = min(max(index, 0), len(bin_volumes) - 1)
            bin_volumes[index] += _f(bar.get("volume"))
    poc_index = max(range(len(bin_volumes)), key=bin_volumes.__getitem__) if any(bin_volumes) else None
    poc_current = None
    if poc_index is not None:
        step = (upper_end - lower_end) / len(bin_volumes)
        poc_current = lower_end + (poc_index + 0.5) * step

    forward_mid = math.exp(intercept - slope * int(extension_bars))
    return {
        "available": True,
        "source": "bigbeluga_pine_reimplementation",
        "length": length,
        "direction": "bull" if reg_end > reg_start else "bear" if reg_end < reg_start else "neutral",
        "slope_log": slope,
        "forward_return_pct": (forward_mid / reg_end - 1.0) if reg_end else 0.0,
        "mid": round(reg_end, 2),
        "upper": round(upper_end, 2),
        "lower": round(lower_end, 2),
        "forward_mid": round(forward_mid, 2),
        "normalized_position": round(normalized_position, 4),
        "position": "above" if close > upper_end else "below" if close < lower_end else "inside",
        "buy_volume_proxy": buy_volume,
        "sell_volume_proxy": sell_volume,
        "delta_pct_proxy": round(delta_pct, 3),
        "poc": round(poc_current, 2) if poc_current is not None else None,
    }


def build_dual_log_regression_context(klines: list[dict[str, Any]]) -> dict[str, Any]:
    cfg = CHART_CONFIG["dual_log_regression"]
    macro = build_log_regression_channel(
        klines,
        int(cfg["macro_length"]),
        float(cfg["macro_width"]),
        int(cfg["macro_bins"]),
        int(cfg["macro_extension_bars"]),
    )
    short = build_log_regression_channel(
        klines,
        int(cfg["short_length"]),
        float(cfg["short_width"]),
        int(cfg["short_bins"]),
        int(cfg["short_extension_bars"]),
    )
    directions = [item.get("direction") for item in (macro, short) if item.get("available")]
    if directions and all(direction == "bull" for direction in directions):
        alignment = "bull"
    elif directions and all(direction == "bear" for direction in directions):
        alignment = "bear"
    else:
        alignment = "mixed" if directions else "neutral"
    return {"source": "bigbeluga_pine_reimplementation", "macro": macro, "short": short, "alignment": alignment}


def build_classic_market_context(klines: list[dict[str, Any]]) -> dict[str, Any]:
    """Dow-style swing structure, volume confirmation and market-cycle phase."""

    if len(klines) < 20:
        return {"available": False, "dow_direction": "neutral", "cycle": "unknown"}
    highs = [_f(bar.get("high")) for bar in klines]
    lows = [_f(bar.get("low")) for bar in klines]
    high_points = _pivot_indices(highs, 5, 5, True)
    low_points = _pivot_indices(lows, 5, 5, False)
    last_highs = [item[2] for item in high_points[-2:]]
    last_lows = [item[2] for item in low_points[-2:]]
    if len(last_highs) == 2 and len(last_lows) == 2 and last_highs[-1] > last_highs[-2] and last_lows[-1] > last_lows[-2]:
        dow_direction = "bull"
        structure = "higher_high_higher_low"
    elif len(last_highs) == 2 and len(last_lows) == 2 and last_highs[-1] < last_highs[-2] and last_lows[-1] < last_lows[-2]:
        dow_direction = "bear"
        structure = "lower_high_lower_low"
    else:
        dow_direction = "neutral"
        structure = "mixed_swings"

    regression = build_dual_log_regression_context(klines)
    fibonacci = build_fibonacci_ote_context(klines)
    volume = build_volume_orderflow_proxy(klines)
    alignment = regression.get("alignment", "neutral")
    location = fibonacci.get("premium_discount", "unknown")
    if dow_direction == "bull" and alignment in {"bull", "mixed"}:
        cycle = "reaccumulation" if location == "discount" else "markup"
    elif dow_direction == "bear" and alignment in {"bear", "mixed"}:
        cycle = "distribution" if location == "premium" else "markdown"
    elif alignment == "bull" and volume.get("signed_cvd_proxy", 0.0) >= 0:
        cycle = "early_markup"
    elif alignment == "bear" and volume.get("signed_cvd_proxy", 0.0) <= 0:
        cycle = "early_markdown"
    else:
        cycle = "range_transition"

    return {
        "available": True,
        "source": "dow_volume_price_market_cycle",
        "dow_direction": dow_direction,
        "structure": structure,
        "last_swing_highs": [round(value, 2) for value in last_highs],
        "last_swing_lows": [round(value, 2) for value in last_lows],
        "cycle": cycle,
        "volume_confirmation": bool(
            (dow_direction == "bull" and volume.get("signed_cvd_proxy", 0.0) > 0)
            or (dow_direction == "bear" and volume.get("signed_cvd_proxy", 0.0) < 0)
        ),
    }


def build_high_volume_pivot_context(klines: list[dict[str, Any]]) -> dict[str, Any]:
    cfg = CHART_CONFIG["high_volume_pivots"]
    res_len = int(cfg["resistance_length"])
    sup_len = int(cfg["support_length"])
    vol_len = int(cfg["volume_ma_length"])
    vol_mult = float(cfg["volume_multiplier"])
    atr_values = atr_series(klines, int(cfg["atr_length"]))
    highs = [_f(bar.get("high")) for bar in klines]
    lows = [_f(bar.get("low")) for bar in klines]
    volumes = [_f(bar.get("volume")) for bar in klines]
    signed_volume = [volume if _f(bar.get("close")) >= _f(bar.get("open")) else -volume for bar, volume in zip(klines, volumes)]

    events: list[tuple[int, str, int, float]] = []
    for confirm, pivot, value in _pivot_indices(highs, res_len, res_len, True):
        average = _sma_at(volumes, pivot, vol_len)
        if pivot >= int(cfg["atr_length"]) - 1 and average is not None and volumes[pivot] > average * vol_mult:
            events.append((confirm, "resistance", pivot, value))
    for confirm, pivot, value in _pivot_indices(lows, sup_len, sup_len, False):
        average = _sma_at(volumes, pivot, vol_len)
        if pivot >= int(cfg["atr_length"]) - 1 and average is not None and volumes[pivot] > average * vol_mult:
            events.append((confirm, "support", pivot, value))
    events.sort(key=lambda item: (item[0], item[1]))

    resistance: dict[str, Any] | None = None
    support: dict[str, Any] | None = None
    event_map: dict[int, list[tuple[str, int]]] = {}
    for confirm, kind, pivot, _ in events:
        event_map.setdefault(confirm, []).append((kind, pivot))

    latest_events: list[str] = []
    for i, bar in enumerate(klines):
        created: set[str] = set()
        for kind, pivot in event_map.get(i, []):
            created.add(kind)
            open_ = _f(klines[pivot].get("open"))
            close = _f(klines[pivot].get("close"))
            atr = atr_values[pivot]
            if kind == "resistance":
                bottom = max(open_, close)
                resistance = {
                    "zone": (bottom, bottom + atr),
                    "pivot_index": pivot,
                    "confirmed_index": i,
                    "broken": False,
                    "break_index": None,
                }
            else:
                top = min(open_, close)
                support = {
                    "zone": (top - atr, top),
                    "pivot_index": pivot,
                    "confirmed_index": i,
                    "broken": False,
                    "break_index": None,
                }

        close = _f(bar.get("close"))
        high = _f(bar.get("high"))
        low = _f(bar.get("low"))
        previous = klines[i - 1] if i else bar

        if resistance and "resistance" not in created:
            bottom, top = resistance["zone"]
            changed_now = False
            if close > top and not resistance["broken"]:
                resistance["broken"] = True
                resistance["break_index"] = i
                latest_events.append("resistance_break")
                changed_now = True
            if not resistance["broken"] and _f(previous.get("high")) >= bottom and high < bottom:
                latest_events.append("resistance_hold_retest")
            if resistance["broken"] and not changed_now and _f(previous.get("low")) <= top and low > top:
                latest_events.append("flipped_resistance_retest")

        if support and "support" not in created:
            bottom, top = support["zone"]
            if close < bottom and not support["broken"]:
                support["broken"] = True
                support["break_index"] = i
                latest_events.append("support_break")
            if not support["broken"] and _f(previous.get("low")) <= top and low > top:
                latest_events.append("support_hold_retest")
            if support["broken"] and _f(previous.get("high")) >= bottom and high < bottom:
                latest_events.append("flipped_support_retest")

    def finalize(zone: dict[str, Any] | None) -> dict[str, Any] | None:
        if not zone:
            return None
        pivot = int(zone["pivot_index"])
        current = len(klines) - 1
        output = dict(zone)
        output["zone"] = tuple(round(value, 2) for value in zone["zone"])
        output["age_bars"] = current - pivot
        output["pivot_volume"] = volumes[pivot]
        output["cvd_proxy"] = sum(signed_volume[pivot : current + 1])
        return output

    return {
        "source": "bigbeluga_pine_reimplementation",
        "orderflow_source": "candle_direction_volume_proxy",
        "resistance": finalize(resistance),
        "support": finalize(support),
        "latest_events": latest_events[-6:],
        "current_event": latest_events[-1] if latest_events else "none",
    }


def _lower_bars_for_parent(parent: dict[str, Any], lower_klines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    start = int(parent.get("open_time", 0) or 0)
    end = int(parent.get("close_time", 0) or 0)
    if not start or not end:
        return []
    return [bar for bar in lower_klines if start <= int(bar.get("open_time", 0) or 0) <= end]


def build_fvg_volume_profile_context(
    klines: list[dict[str, Any]],
    lower_klines: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    cfg = CHART_CONFIG["fvg_volume_profile"]
    bins = max(1, int(cfg["bins"]))
    gap_filter = float(cfg["gap_filter"])
    max_active = max(1, int(cfg["max_active"]))
    lower_klines = lower_klines or []
    if len(klines) < 3:
        return {"available": False, "bullish": [], "bearish": [], "profile_source": "none"}

    bearish_raw = [0.0, 0.0]
    bullish_raw = [0.0, 0.0]
    for i in range(2, len(klines)):
        bearish_raw.append(_f(klines[i - 2].get("low")) - _f(klines[i].get("high")))
        bullish_raw.append(_f(klines[i].get("low")) - _f(klines[i - 2].get("high")))

    active: list[dict[str, Any]] = []
    for i in range(199, len(klines)):
        bearish_std = _std(bearish_raw[i - 199 : i + 1])
        bullish_std = _std(bullish_raw[i - 199 : i + 1])
        bearish_size = bearish_raw[i] / bearish_std if bearish_std > 1e-12 else 0.0
        bullish_size = bullish_raw[i] / bullish_std if bullish_std > 1e-12 else 0.0
        bullish = (
            _f(klines[i].get("low")) > _f(klines[i - 2].get("high"))
            and _f(klines[i - 1].get("high")) > _f(klines[i - 2].get("high"))
            and bullish_size > gap_filter
        )
        bearish = (
            _f(klines[i].get("high")) < _f(klines[i - 2].get("low"))
            and _f(klines[i - 1].get("low")) < _f(klines[i - 2].get("low"))
            and bearish_size > gap_filter
        )

        for direction, condition in (("bull", bullish), ("bear", bearish)):
            if not condition:
                continue
            if direction == "bull":
                zone = (_f(klines[i - 2].get("high")), _f(klines[i].get("low")))
            else:
                zone = (_f(klines[i].get("high")), _f(klines[i - 2].get("low")))
            zone = _ordered(*zone)
            profile_bars = _lower_bars_for_parent(klines[i - 1], lower_klines)
            profile_source = "closed_15m_proxy" if profile_bars else "parent_candle_proxy"
            if not profile_bars:
                profile_bars = [klines[i - 1]]
            step = (zone[1] - zone[0]) / bins
            profile = [0.0] * bins
            if step > 0:
                for index in range(bins):
                    midpoint = zone[0] + step * (index + 0.5)
                    for bar in profile_bars:
                        if abs(_f(bar.get("close")) - midpoint) <= step:
                            profile[index] += _f(bar.get("volume"))
            poc_index = max(range(bins), key=profile.__getitem__) if any(profile) else None
            poc = zone[0] + step * (poc_index + 0.5) if poc_index is not None else None
            active.append(
                {
                    "direction": direction,
                    "zone": zone,
                    "detected_index": i,
                    "profile": profile,
                    "poc": poc,
                    "profile_source": profile_source,
                    "gap_zscore": bullish_size if direction == "bull" else bearish_size,
                    "mitigated": False,
                }
            )
            if len(active) > max_active:
                active.pop(0)

        survivors: list[dict[str, Any]] = []
        for item in active:
            if item["detected_index"] == i:
                survivors.append(item)
                continue
            bottom, top = item["zone"]
            if item["direction"] == "bull":
                item["mitigated"] = bool(item["mitigated"] or _f(klines[i].get("low")) < top)
                invalid = _f(klines[i].get("low")) < bottom
            else:
                item["mitigated"] = bool(item["mitigated"] or _f(klines[i].get("high")) > bottom)
                invalid = _f(klines[i].get("high")) > top
            if not invalid:
                survivors.append(item)
        active = survivors

    close = _f(klines[-1].get("close"))
    for item in active:
        item["zone"] = tuple(round(value, 2) for value in item["zone"])
        item["poc"] = round(item["poc"], 2) if item["poc"] is not None else None
        item["age_bars"] = len(klines) - 1 - int(item["detected_index"])
        item["distance"] = _distance(close, item["zone"])
        item.pop("profile", None)

    bullish_items = [item for item in active if item["direction"] == "bull"]
    bearish_items = [item for item in active if item["direction"] == "bear"]
    nearest = min(active, key=lambda item: float(item["distance"] or 0.0)) if active else None
    profile_sources = {item["profile_source"] for item in active}
    return {
        "available": bool(active),
        "source": "chartprime_pine_reimplementation",
        "profile_source": profile_sources.pop() if len(profile_sources) == 1 else "mixed_proxy" if profile_sources else "none",
        "custom_lower_timeframe_input": str(cfg["lower_timeframe_input"]),
        "bullish": bullish_items,
        "bearish": bearish_items,
        "nearest": nearest,
    }


def build_volume_orderflow_proxy(klines: list[dict[str, Any]], lookback: int = 20) -> dict[str, Any]:
    if len(klines) < 3:
        return {"available": False, "source": "candle_volume_proxy"}
    latest = klines[-1]
    history = klines[-lookback - 1 : -1]
    volumes = [_f(bar.get("volume")) for bar in history]
    average_volume = _mean(volumes[-20:]) if volumes else 0.0
    volume = _f(latest.get("volume"))
    volume_ratio = volume / average_volume if average_volume > 0 else 1.0
    previous_high = max(_f(bar.get("high")) for bar in history)
    previous_low = min(_f(bar.get("low")) for bar in history)
    high = _f(latest.get("high"))
    low = _f(latest.get("low"))
    close = _f(latest.get("close"))
    open_ = _f(latest.get("open"))
    candle_range = max(high - low, 1e-9)
    body_ratio = abs(close - open_) / candle_range
    upper_wick = high - max(open_, close)
    lower_wick = min(open_, close) - low
    signed = [
        _f(bar.get("volume")) if _f(bar.get("close")) >= _f(bar.get("open")) else -_f(bar.get("volume"))
        for bar in klines[-lookback:]
    ]

    upside_stop_run = high > previous_high and close < previous_high
    downside_stop_run = low < previous_low and close > previous_low
    accepted_up = close > previous_high and volume_ratio >= 1.2
    accepted_down = close < previous_low and volume_ratio >= 1.2
    absorption = "none"
    if volume_ratio >= 1.2 and body_ratio <= 0.38:
        if lower_wick > upper_wick * 1.2:
            absorption = "sell_absorption_proxy"
        elif upper_wick > lower_wick * 1.2:
            absorption = "buy_absorption_proxy"

    return {
        "available": True,
        "source": "candle_direction_volume_proxy",
        "is_true_orderflow": False,
        "volume_ratio": round(volume_ratio, 3),
        "signed_cvd_proxy": sum(signed),
        "body_ratio": round(body_ratio, 3),
        "upside_stop_run": upside_stop_run,
        "downside_stop_run": downside_stop_run,
        "accepted_breakout_up": accepted_up,
        "accepted_breakout_down": accepted_down,
        "fake_breakout_up": upside_stop_run,
        "fake_breakout_down": downside_stop_run,
        "absorption": absorption,
        "volume_continuation": bool(
            volume_ratio >= 1.2
            and body_ratio >= 0.55
            and ((close > open_ and close > previous_high) or (close < open_ and close < previous_low))
        ),
    }


def _parse_clock(value: str) -> time:
    hour, minute = value.split(":", 1)
    return time(int(hour), int(minute))


def build_killzone_context(bar: dict[str, Any]) -> dict[str, Any]:
    timestamp = int(bar.get("open_time", 0) or 0)
    if not timestamp:
        return {"active": [], "display_enabled": False}
    instant = datetime.fromtimestamp(timestamp / 1000.0, tz=timezone.utc)
    active: list[str] = []
    for name, (timezone_name, start_text, end_text) in CHART_CONFIG["killzones"].items():
        local_clock = instant.astimezone(ZoneInfo(timezone_name)).time().replace(tzinfo=None)
        start = _parse_clock(start_text)
        end = _parse_clock(end_text)
        inside = start <= local_clock < end if start <= end else local_clock >= start or local_clock < end
        if inside:
            active.append(name)
    return {
        "active": active,
        # The screenshot has the visual toggle off.  Session context remains
        # available to the decision layer because Killzone is part of the user's
        # stated ICT framework.
        "display_enabled": bool(CHART_CONFIG["ict"]["show_killzones"]),
    }


def build_chart_context(
    klines: list[dict[str, Any]],
    lower_klines: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if not klines:
        return {"available": False}
    return {
        "available": True,
        "fibonacci": build_fibonacci_ote_context(klines),
        "dual_log_regression": build_dual_log_regression_context(klines),
        "classic_market": build_classic_market_context(klines),
        "high_volume_pivots": build_high_volume_pivot_context(klines),
        "fvg_volume_profile": build_fvg_volume_profile_context(klines, lower_klines),
        "volume_orderflow": build_volume_orderflow_proxy(klines),
        "killzone": build_killzone_context(klines[-1]),
    }
