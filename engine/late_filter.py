from __future__ import annotations

from typing import Any


FORMAL_CONFIRM_ALERTS = {
    "BULLISH_STRUCTURE_SHIFT",
    "BEARISH_STRUCTURE_SHIFT",
    "SECONDARY_CONFIRM_LOWER",
    "SECONDARY_CONFIRM_UPPER",
}


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def apply_late_filter(decision: dict[str, Any], klines_1h: list[dict[str, Any]]) -> dict[str, Any]:
    """Suppress 1H formal confirmations that arrive after the useful entry area.

    The 15m layer is for early warnings.  A 1H confirmation is still useful
    only while price remains close to the relevant area and is not already
    reversing against the confirmation direction.  Otherwise it becomes a
    hindsight alert and should stay in logs only.
    """

    if not decision.get("should_alert"):
        return decision

    alert_type = str(decision.get("alert_type", ""))
    if alert_type not in FORMAL_CONFIRM_ALERTS:
        return decision
    if len(klines_1h) < 2:
        return decision

    latest = klines_1h[-1]
    prev = klines_1h[-2]
    close = _f(latest.get("close"))
    open_ = _f(latest.get("open"))
    prev_close = _f(prev.get("close"))
    atr = max(_f(latest.get("atr")), abs(close) * 0.002, 1.0)

    zone = decision.get("zone") or (decision.get("zone_low"), decision.get("zone_high"))
    try:
        zone_low = min(_f(zone[0]), _f(zone[1]))
        zone_high = max(_f(zone[0]), _f(zone[1]))
    except Exception:
        zone_low = _f(decision.get("zone_low"), close)
        zone_high = _f(decision.get("zone_high"), close)

    direction = str(decision.get("direction", "neutral"))
    max_extension = max(atr * 0.85, abs(close) * 0.0035)

    reason = ""
    if direction == "short":
        # If the confirmation candle is already being bought back, do not
        # publish it as an actionable short confirmation.
        if close >= open_ or close > prev_close:
            reason = "late_confirm_rebound_against_short"
        elif close < zone_low - max_extension:
            reason = "late_confirm_too_far_below_zone"
    elif direction == "long":
        if close <= open_ or close < prev_close:
            reason = "late_confirm_rejection_against_long"
        elif close > zone_high + max_extension:
            reason = "late_confirm_too_far_above_zone"

    if not reason:
        return decision

    filtered = dict(decision)
    filtered["should_alert"] = False
    filtered["suppress_reason"] = reason
    filtered.setdefault("score_breakdown", {})
    if isinstance(filtered["score_breakdown"], dict):
        filtered["score_breakdown"]["penalty_reason"] = reason
    filtered["late_filter"] = True
    return filtered
