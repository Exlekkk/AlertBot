"""Quarantined classic swing / market-cycle builder.

Peeled from live HTF bias and trial scoring. Kept for tests / manual replay.
"""
from __future__ import annotations

from typing import Any

from engine.chart_indicators import (
    _f,
    _pivot_indices,
    build_fibonacci_ote_context,
    build_volume_orderflow_proxy,
)
from engine.legacy_quarantine.dual_log import build_dual_log_regression_context


def build_classic_market_context(klines: list[dict[str, Any]]) -> dict[str, Any]:
    """Classic swing structure, volume confirmation and market-cycle phase."""

    if len(klines) < 20:
        return {"available": False, "dow_direction": "neutral", "cycle": "unknown", "quarantined": True}
    highs = [_f(bar.get("high")) for bar in klines]
    lows = [_f(bar.get("low")) for bar in klines]
    high_points = _pivot_indices(highs, 5, 5, True)
    low_points = _pivot_indices(lows, 5, 5, False)
    last_highs = [item[2] for item in high_points[-2:]]
    last_lows = [item[2] for item in low_points[-2:]]
    if len(last_highs) == 2 and len(last_lows) == 2 and last_highs[-1] > last_highs[-2] and last_lows[-1] > last_lows[-2]:
        swing_direction = "bull"
        structure = "higher_high_higher_low"
    elif len(last_highs) == 2 and len(last_lows) == 2 and last_highs[-1] < last_highs[-2] and last_lows[-1] < last_lows[-2]:
        swing_direction = "bear"
        structure = "lower_high_lower_low"
    else:
        swing_direction = "neutral"
        structure = "mixed_swings"

    regression = build_dual_log_regression_context(klines)
    fibonacci = build_fibonacci_ote_context(klines)
    volume = build_volume_orderflow_proxy(klines)
    alignment = regression.get("alignment", "neutral")
    location = fibonacci.get("premium_discount", "unknown")
    if swing_direction == "bull" and alignment in {"bull", "mixed"}:
        cycle = "reaccumulation" if location == "discount" else "markup"
    elif swing_direction == "bear" and alignment in {"bear", "mixed"}:
        cycle = "distribution" if location == "premium" else "markdown"
    elif alignment == "bull" and volume.get("signed_cvd_proxy", 0.0) >= 0:
        cycle = "early_markup"
    elif alignment == "bear" and volume.get("signed_cvd_proxy", 0.0) <= 0:
        cycle = "early_markdown"
    else:
        cycle = "range_transition"

    return {
        "available": True,
        "source": "legacy_classic_swing",
        "quarantined": True,
        # Keep legacy key name for older readers of this payload shape.
        "dow_direction": swing_direction,
        "structure": structure,
        "last_swing_highs": [round(value, 2) for value in last_highs],
        "last_swing_lows": [round(value, 2) for value in last_lows],
        "cycle": cycle,
        "volume_confirmation": bool(
            (swing_direction == "bull" and volume.get("signed_cvd_proxy", 0.0) > 0)
            or (swing_direction == "bear" and volume.get("signed_cvd_proxy", 0.0) < 0)
        ),
    }


__all__ = ["build_classic_market_context"]
