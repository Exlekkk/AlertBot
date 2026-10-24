"""Formation / participation shadow (15m only).

Candle approx of a dollar-volume formation oscillator with percentile bands.
Shadow / observe / soft participation filter only — never a formal 1H trigger.
"""
from __future__ import annotations

import math
from typing import Any

from engine.trend_config import TREND_ENGINE_CONFIG


def _f(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if number != number or number in (float("inf"), float("-inf")):
        return default
    return number


def _linear_percentile(sorted_vals: list[float], pct: float) -> float:
    """Linear-interpolated percentile; pct in 0..100."""
    if not sorted_vals:
        return 0.0
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    rank = (pct / 100.0) * (len(sorted_vals) - 1)
    lo = int(math.floor(rank))
    hi = int(math.ceil(rank))
    if lo == hi:
        return sorted_vals[lo]
    weight = rank - lo
    return sorted_vals[lo] * (1.0 - weight) + sorted_vals[hi] * weight


def _cfg() -> dict[str, Any]:
    top = TREND_ENGINE_CONFIG.get("formation_shadow") or TREND_ENGINE_CONFIG.get("tai") or {}
    chart = (TREND_ENGINE_CONFIG.get("chart_framework") or {}).get("tai") or {}
    return {
        "formation": int(top.get("formation", chart.get("formation_length", 30))),
        "history": int(top.get("history", chart.get("history_length", 350))),
        "timeframes": [str(t).lower() for t in top.get("timeframes", ["15m"])],
    }


def build_formation_shadow(
    klines: list[dict[str, Any]],
    *,
    timeframe: str = "15m",
) -> dict[str, Any]:
    """Build 15m formation-shadow context from closed candles."""

    cfg = _cfg()
    tf = str(timeframe).lower()
    allowed = set(cfg["timeframes"])
    empty = {
        "approx": True,
        "candle_proxy": True,
        "timeframe": tf,
        "allowed": tf in allowed,
        "shadow_only": True,
        "should_alert": False,
        "regime": "neutral",
        "value": None,
        "p20": None,
        "p40": None,
        "p60": None,
        "p80": None,
        "rank01": None,
        "reason": "timeframe_not_allowed" if tf not in allowed else "insufficient_bars",
    }
    if tf not in allowed:
        return empty

    # Prefer explicit fields on the latest bar when present (enrich path).
    latest = klines[-1] if klines else {}
    explicit = {
        "value": latest.get("tai_value", latest.get("formation_value")),
        "p20": latest.get("tai_p20", latest.get("formation_p20")),
        "p40": latest.get("tai_p40", latest.get("formation_p40")),
        "p60": latest.get("tai_p60", latest.get("formation_p60")),
        "p80": latest.get("tai_p80", latest.get("formation_p80")),
    }
    if explicit["value"] is not None and all(explicit[k] is not None for k in ("p20", "p40", "p60", "p80")):
        bands = {k: _f(explicit[k]) for k in explicit}
    else:
        len_form = max(2, int(cfg["formation"]))
        len_hist = max(len_form + 1, int(cfg["history"]))
        if len(klines) < len_form + 5:
            return empty
        dollar = [_f(k.get("close")) * _f(k.get("volume")) for k in klines]
        vscale: list[float] = []
        window_sum = 0.0
        for i, value in enumerate(dollar):
            window_sum += value
            if i >= len_form:
                window_sum -= dollar[i - len_form]
            if i + 1 >= len_form:
                avg = window_sum / float(len_form)
                vscale.append(math.log(max(avg, 1e-12)))
            else:
                vscale.append(float("nan"))
        valid = [v for v in vscale if v == v]
        if len(valid) < min(50, len_hist):
            return empty
        hist = sorted(valid[-len_hist:])
        bands = {
            "value": valid[-1],
            "p20": _linear_percentile(hist, 20),
            "p40": _linear_percentile(hist, 40),
            "p60": _linear_percentile(hist, 60),
            "p80": _linear_percentile(hist, 80),
        }

    value, p20, p40, p60, p80 = bands["value"], bands["p20"], bands["p40"], bands["p60"], bands["p80"]
    if not (p20 < p40 < p60 < p80):
        regime = "neutral"
        rank01 = 0.5
    elif value < p20:
        regime = "very_cold"
        rank01 = 0.1
    elif value < p40:
        regime = "cold"
        rank01 = 0.3
    elif value < p60:
        regime = "neutral"
        rank01 = 0.5
    elif value < p80:
        regime = "warm"
        rank01 = 0.7
    else:
        regime = "very_warm"
        rank01 = 0.9

    return {
        "approx": True,
        "candle_proxy": True,
        "timeframe": tf,
        "allowed": True,
        "shadow_only": True,
        "should_alert": False,
        "regime": regime,
        "value": round(value, 6),
        "p20": round(p20, 6),
        "p40": round(p40, 6),
        "p60": round(p60, 6),
        "p80": round(p80, 6),
        "rank01": rank01,
        "reason": "ok",
        # Legacy field aliases for 15m paths still reading tai_* keys
        "tai_value": round(value, 6),
        "tai_p20": round(p20, 6),
        "tai_p40": round(p40, 6),
        "tai_p60": round(p60, 6),
        "tai_p80": round(p80, 6),
    }


__all__ = ["build_formation_shadow"]
