from __future__ import annotations

from typing import Any

from engine.trend_config import TREND_ENGINE_CONFIG


def _bar_sweep(bar: dict[str, Any], prev_high: float, prev_low: float, close_buffer: float) -> tuple[str, str, float | None]:
    high, low, close = float(bar["high"]), float(bar["low"]), float(bar["close"])
    if low < (prev_low - close_buffer) and close > (prev_low + close_buffer):
        return "sellside", "reclaim", prev_low
    if high > (prev_high + close_buffer) and close < (prev_high - close_buffer):
        return "buyside", "reject", prev_high
    return "none", "none", None


def build_liquidity_context(klines_1h: list[dict[str, Any]], lookback: int | None = None) -> dict[str, Any]:
    cfg = TREND_ENGINE_CONFIG["liquidity"]
    lookback = lookback or cfg["sweep_lookback"]
    bars = klines_1h[-lookback:] if len(klines_1h) >= lookback else klines_1h
    latest = bars[-1]
    close = float(latest["close"])
    high = float(latest["high"])
    low = float(latest["low"])
    atr = float(latest.get("atr", max(close * 0.004, 1.0)))
    highs = [float(k["high"]) for k in bars]
    lows = [float(k["low"]) for k in bars]
    prev_high = max(highs[:-1]) if len(highs) > 1 else highs[-1]
    prev_low = min(lows[:-1]) if len(lows) > 1 else lows[-1]
    tol = cfg["eq_tolerance"]
    close_buffer = max(close * cfg["close_buffer_pct"], atr * cfg["close_buffer_atr_mult"])

    sweep_type, reclaim_or_reject, sweep_level = _bar_sweep(latest, prev_high, prev_low, close_buffer)
    bars_since_sweep = None
    if sweep_type == "none":
        recent_n = min(cfg["recent_sweep_window"], len(bars) - 1)
        for i in range(1, recent_n + 1):
            b = bars[-1 - i]
            b_type, b_rr, b_lvl = _bar_sweep(b, prev_high, prev_low, close_buffer)
            if b_type != "none":
                sweep_type, reclaim_or_reject, sweep_level = b_type, b_rr, b_lvl
                bars_since_sweep = i
                break
    else:
        bars_since_sweep = 0

    return {
        "prev_high": prev_high,
        "prev_low": prev_low,
        "eqh": abs(high - prev_high) / max(abs(prev_high), 1e-9) < tol,
        "eql": abs(low - prev_low) / max(abs(prev_low), 1e-9) < tol,
        "sweep_type": sweep_type,
        "sweep_level": sweep_level,
        "reclaim_or_reject": reclaim_or_reject,
        "bars_since_sweep": bars_since_sweep,
        "recent_sweep_valid": sweep_type != "none" and (bars_since_sweep is not None and bars_since_sweep <= cfg["recent_sweep_window"]),
        "close_buffer": close_buffer,
    }
