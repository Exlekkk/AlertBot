"""Quarantined dual-log regression channel builders.

Peeled from live HTF bias and trial scoring. Kept for tests / manual replay.
"""
from __future__ import annotations

import math
from typing import Any

from engine.chart_indicators import CHART_CONFIG, _f, _std


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
        "source": "legacy_log_regression",
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
    return {
        "source": "legacy_dual_log",
        "macro": macro,
        "short": short,
        "alignment": alignment,
        "quarantined": True,
    }


__all__ = ["build_log_regression_channel", "build_dual_log_regression_context"]
