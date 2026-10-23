"""Core-levels oscillator filter (1H+ only).

Candle approx of RSI mid-line reclaim/loss and a small set of active
oscillator pivots. Filter / soft weight only — never a solo alert trigger.
"""
from __future__ import annotations

from typing import Any

from engine.indicators import rsi_series
from engine.trend_config import TREND_ENGINE_CONFIG


def _f(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if number != number or number in (float("inf"), float("-inf")):
        return default
    return number


def _sma(values: list[float], length: int) -> list[float]:
    length = max(1, int(length))
    out: list[float] = []
    running = 0.0
    for i, value in enumerate(values):
        running += value
        if i >= length:
            running -= values[i - length]
        denom = length if i + 1 >= length else (i + 1)
        out.append(running / float(denom))
    return out


def build_core_levels_filter(
    klines: list[dict[str, Any]],
    *,
    timeframe: str = "1h",
) -> dict[str, Any]:
    """Build 1H+ core-levels filter context.

    Allowed timeframes come from config (default 1h/4h). Lower frames return
    an inert payload so callers cannot accidentally promote this to a trigger.
    """

    cfg = TREND_ENGINE_CONFIG.get("core_levels_filter") or TREND_ENGINE_CONFIG.get("rsi_heatmap") or {}
    allowed = {str(t).lower() for t in cfg.get("timeframes", ["1h", "4h"])}
    tf = str(timeframe).lower()
    base = {
        "approx": True,
        "candle_proxy": True,
        "timeframe": tf,
        "allowed": tf in allowed,
        "filter_only": True,
        "should_alert": False,
        "lean": "neutral",
        "midline_event": "none",
        "squeeze": False,
        "levels": [],
        "rsi": None,
        "signal": None,
        "reason": "timeframe_not_allowed" if tf not in allowed else "ok",
    }
    if tf not in allowed or len(klines) < 20:
        if len(klines) < 20:
            base["reason"] = "insufficient_bars"
        return base

    closes = [_f(k.get("close")) for k in klines]
    rsi_len = int(cfg.get("rsi_length", 14))
    sig_len = int(cfg.get("signal_length", 14))
    max_levels = max(1, int(cfg.get("max_levels", 5)))
    use_squeeze = bool(cfg.get("midline_squeeze", True))

    rsi = rsi_series(closes, rsi_len)
    signal = _sma(rsi, sig_len)
    rsi_now = rsi[-1]
    sig_now = signal[-1]
    rsi_prev = rsi[-2] if len(rsi) >= 2 else rsi_now

    midline_event = "none"
    if rsi_prev < 50.0 <= rsi_now:
        midline_event = "reclaim_above_50"
    elif rsi_prev > 50.0 >= rsi_now:
        midline_event = "loss_below_50"

    # Active oscillator pivots (local RSI extremes), newest first, capped.
    levels: list[dict[str, Any]] = []
    for i in range(2, len(rsi) - 1):
        left, mid, right = rsi[i - 1], rsi[i], rsi[i + 1]
        kind = None
        if mid >= left and mid > right and mid >= 55.0:
            kind = "resistance"
        elif mid <= left and mid < right and mid <= 45.0:
            kind = "support"
        if kind is None:
            continue
        levels.append(
            {
                "bar": i,
                "rsi": round(mid, 3),
                "kind": kind,
                "price": _f(klines[i].get("close")),
            }
        )
    levels = list(reversed(levels))[:max_levels]

    squeeze = False
    if use_squeeze:
        window = rsi[-min(len(rsi), 8) :]
        rsi_range = max(window) - min(window) if window else 0.0
        squeeze = abs(rsi_now - 50.0) <= 6.0 and abs(sig_now - 50.0) <= 6.0 and rsi_range <= 10.0

    lean = "neutral"
    if midline_event == "reclaim_above_50" or (rsi_now >= 55.0 and rsi_now >= sig_now):
        lean = "bull"
    elif midline_event == "loss_below_50" or (rsi_now <= 45.0 and rsi_now <= sig_now):
        lean = "bear"

    base.update(
        {
            "lean": lean,
            "midline_event": midline_event,
            "squeeze": squeeze,
            "levels": levels,
            "rsi": round(rsi_now, 3),
            "signal": round(sig_now, 3),
            "dashboard": bool(cfg.get("dashboard", False)),
            "reason": "ok",
        }
    )
    return base


__all__ = ["build_core_levels_filter"]
