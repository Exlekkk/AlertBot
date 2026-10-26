"""Imbalance-zone approx — closed candles.

Detects three-candle gaps, optional inversion after opposing close-through,
and nearest active zone for weighting. Not a solo direction or trigger.
"""
from __future__ import annotations

from typing import Any

from engine.trend_config import TREND_ENGINE_CONFIG


def _f(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def build_ifvg_context(
    klines: list[dict[str, Any]],
    *,
    timeframe: str = "1h",
) -> dict[str, Any]:
    cfg = TREND_ENGINE_CONFIG.get("ifvg", {})
    tf = timeframe.lower()
    min_size = float(
        cfg.get("min_size_1h", 0.2)
        if tf in {"1h", "1H", "60", "60m"}
        else cfg.get("min_size_15m", 0.15)
    )
    longevity = int(cfg.get("longevity", 500))
    calc_bars = int(cfg.get("calc_bars", 2000))
    display_mode = str(cfg.get("display_mode", "Both"))

    empty = {
        "zones": [],
        "nearest_active": None,
        "approx": True,
        "candle_proxy": True,
        "reason": "insufficient_history",
        "timeframe": timeframe,
        "min_size_pct": min_size,
        "params": {
            "display_mode": display_mode,
            "longevity": longevity,
            "calc_bars": calc_bars,
        },
    }
    if len(klines) < 30:
        return empty

    window = klines[-min(len(klines), calc_bars):]
    highs = [_f(k.get("high")) for k in window]
    lows = [_f(k.get("low")) for k in window]
    closes = [_f(k.get("close")) for k in window]
    n = len(window)
    min_frac = min_size / 100.0

    raw: list[dict[str, Any]] = []
    for i in range(2, n):
        # Process creation and lifecycle chronologically. A replaced zone must
        # not be available to invert later in the replay.
        threshold = abs(closes[i - 1]) * min_frac
        new_zone = None
        if lows[i] - highs[i - 2] > threshold:
            new_zone = {"top": lows[i], "bottom": highs[i - 2], "direction": 1}
        elif lows[i - 2] - highs[i] > threshold:
            new_zone = {"top": lows[i - 2], "bottom": highs[i], "direction": -1}
        if new_zone is not None:
            for old in raw:
                if old["invalidated"] or old["mitigated"]:
                    continue
                if (old["bottom"] <= new_zone["top"] <= old["top"]
                        or old["bottom"] <= new_zone["bottom"] <= old["top"]):
                    old["mitigated"] = True
                    old["invalidated"] = True
            raw.append({**new_zone, "inverted": False, "mitigated": False,
                        "invalidated": False, "start_bar": i, "invert_bar": None})

        c = closes[i]
        for z in raw:
            age = i - z["start_bar"]
            if age <= 0 or z["invalidated"]:
                continue
            if age > longevity:
                z["invalidated"] = True
                continue
            top, bot = z["top"], z["bottom"]
            if not z["inverted"]:
                if (z["direction"] == 1 and c < bot) or (z["direction"] == -1 and c > top):
                    z["inverted"] = True
                    z["invert_bar"] = i
            elif (z["direction"] == 1 and c > top) or (z["direction"] == -1 and c < bot):
                z["invalidated"] = True
                z["mitigated"] = True
            # A wick touch is a reaction, not retirement of a classic gap.

    if display_mode.lower().startswith("inv"):
        visible = [z for z in raw if z["inverted"]]
    else:
        visible = raw

    zones = []
    for z in visible[-40:]:
        zones.append({
            "top": round(z["top"], 2),
            "bottom": round(z["bottom"], 2),
            "direction": int(z["direction"]),
            "inverted": bool(z["inverted"]),
            "mitigated": bool(z["mitigated"]),
            "invalidated": bool(z["invalidated"]),
            "start_bar": int(z["start_bar"]),
        })

    # nearest_active priority:
    # 1) active inverted (not invalidated) — touch/mitigated ignored
    # 2) classic unfilled gaps (not mitigated, not inverted)
    nearest = None
    close = closes[-1]
    candidates = [z for z in visible if z["inverted"] and not z["invalidated"]]
    if not candidates:
        candidates = [z for z in visible if (not z["inverted"]) and (not z["mitigated"]) and (not z["invalidated"])]
    if candidates:
        def _dist(z: dict[str, Any]) -> float:
            mid = (z["top"] + z["bottom"]) / 2.0
            return abs(close - mid)

        best = min(candidates, key=_dist)
        nearest = {
            "top": round(best["top"], 2),
            "bottom": round(best["bottom"], 2),
            "direction": int(best["direction"]),
            "inverted": bool(best["inverted"]),
            "mitigated": bool(best["mitigated"]),
            "invalidated": bool(best["invalidated"]),
            "start_bar": int(best["start_bar"]),
        }

    return {
        "zones": zones,
        "nearest_active": nearest,
        "approx": True,
        "candle_proxy": True,
        "reason": "imbalance_approx" if zones else "no_gap",
        "timeframe": timeframe,
        "min_size_pct": min_size,
        "params": empty["params"],
    }


__all__ = ["build_ifvg_context"]
