from __future__ import annotations

from typing import Any

from engine.trend_config import TREND_ENGINE_CONFIG


def build_liquidity_context(klines_1h: list[dict[str, Any]], lookback: int | None = None) -> dict[str, Any]:
    cfg = TREND_ENGINE_CONFIG["liquidity"]
    lookback = lookback or cfg["sweep_lookback"]
    bars = klines_1h[-lookback:] if len(klines_1h) >= lookback else klines_1h
    highs = [float(k["high"]) for k in bars]
    lows = [float(k["low"]) for k in bars]
    latest = bars[-1]
    close = float(latest["close"])
    high = float(latest["high"])
    low = float(latest["low"])
    atr = float(latest.get("atr", max(close * 0.004, 1.0)))

    prev_high = max(highs[:-1]) if len(highs) > 1 else highs[-1]
    prev_low = min(lows[:-1]) if len(lows) > 1 else lows[-1]
    tol = cfg["eq_tolerance"]
    close_buffer = max(close * cfg["close_buffer_pct"], atr * cfg["close_buffer_atr_mult"])

    buyside_sweep = high > (prev_high + close_buffer) and close < (prev_high - close_buffer)
    sellside_sweep = low < (prev_low - close_buffer) and close > (prev_low + close_buffer)
    breakout_up = close > (prev_high + close_buffer) and not buyside_sweep
    breakout_down = close < (prev_low - close_buffer) and not sellside_sweep

    return {
        "prev_high": prev_high,
        "prev_low": prev_low,
        "eqh": abs(high - prev_high) / max(abs(prev_high), 1e-9) < tol,
        "eql": abs(low - prev_low) / max(abs(prev_low), 1e-9) < tol,
        "buyside_sweep": buyside_sweep,
        "sellside_sweep": sellside_sweep,
        "sweep_type": "buyside" if buyside_sweep else "sellside" if sellside_sweep else "none",
        "sweep_level": prev_high if buyside_sweep else prev_low if sellside_sweep else None,
        "reclaim_up": sellside_sweep,
        "reject_down": buyside_sweep,
        "reclaim_or_reject": "reclaim" if sellside_sweep else "reject" if buyside_sweep else "none",
        "breakout_up": breakout_up,
        "breakout_down": breakout_down,
        "close_buffer": close_buffer,
    }
