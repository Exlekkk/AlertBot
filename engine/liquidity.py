from __future__ import annotations

from typing import Any

from engine.trend_config import TREND_ENGINE_CONFIG


def _bar_sweep(
    bar: dict[str, Any],
    prev_high: float,
    prev_low: float,
    close_buffer: float,
) -> tuple[str, str, float | None]:
    high = float(bar["high"])
    low = float(bar["low"])
    close = float(bar["close"])

    if low < (prev_low - close_buffer) and close > (prev_low + close_buffer):
        return "sellside", "reclaim", prev_low
    if high > (prev_high + close_buffer) and close < (prev_high - close_buffer):
        return "buyside", "reject", prev_high
    return "none", "none", None


def build_liquidity_context(klines_1h: list[dict[str, Any]], lookback: int | None = None) -> dict[str, Any]:
    cfg = TREND_ENGINE_CONFIG["liquidity"]
    lookback = lookback or cfg["sweep_lookback"]
    bars = klines_1h[-max(lookback + cfg["recent_sweep_window"], lookback):]

    latest = bars[-1]
    close = float(latest["close"])
    atr = float(latest.get("atr", max(close * 0.004, 1.0)))
    close_buffer = max(close * cfg["close_buffer_pct"], atr * cfg["close_buffer_atr_mult"])

    latest_ref = bars[-(lookback + 1):-1] if len(bars) > lookback else bars[:-1]
    highs = [float(k["high"]) for k in latest_ref] or [float(latest["high"])]
    lows = [float(k["low"]) for k in latest_ref] or [float(latest["low"])]
    prev_high = max(highs)
    prev_low = min(lows)

    sweep_type, reclaim_or_reject, sweep_level = _bar_sweep(latest, prev_high, prev_low, close_buffer)
    bars_since_sweep = 0 if sweep_type != "none" else None

    if sweep_type == "none":
        max_back = min(cfg["recent_sweep_window"], len(bars) - 1)
        for i in range(1, max_back + 1):
            idx = len(bars) - 1 - i
            hist = bars[max(0, idx - lookback):idx]
            if not hist:
                continue
            hist_prev_high = max(float(k["high"]) for k in hist)
            hist_prev_low = min(float(k["low"]) for k in hist)

            b_type, b_rr, b_lvl = _bar_sweep(bars[idx], hist_prev_high, hist_prev_low, close_buffer)
            if b_type != "none":
                sweep_type, reclaim_or_reject, sweep_level = b_type, b_rr, b_lvl
                bars_since_sweep = i
                break

    return {
        "prev_high": prev_high,
        "prev_low": prev_low,
        "sweep_type": sweep_type,
        "sweep_level": sweep_level,
        "reclaim_or_reject": reclaim_or_reject,
        "bars_since_sweep": bars_since_sweep,
        "recent_sweep_valid": (
            sweep_type != "none"
            and bars_since_sweep is not None
            and bars_since_sweep <= cfg["recent_sweep_window"]
        ),
        "close_buffer": close_buffer,
    }
