from __future__ import annotations

import hashlib
from typing import Any

from engine.trend_config import TREND_ENGINE_CONFIG


def _f(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _avg(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _cluster_key(low: float, high: float, atr: float, close: float) -> str:
    center = (float(low) + float(high)) / 2.0
    width = max(float(high) - float(low), 1.0)
    bucket = max(float(atr) * float(TREND_ENGINE_CONFIG["range_lock"].get("box_shift_atr_mult", 1.25)), abs(float(close)) * 0.006, 1.0)
    center_bucket = round(center / bucket)
    width_bucket = round(width / max(bucket, 1.0))
    return hashlib.md5(f"range-lock:{center_bucket}:{width_bucket}".encode()).hexdigest()[:10]


def build_range_lock_context(
    klines_1h: list[dict[str, Any]],
    htf_ctx: dict[str, Any],
    liq: dict[str, Any],
    msb: dict[str, Any],
    matrix: dict[str, Any],
    aux: dict[str, Any],
    vp: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Detect sideways / accumulation conditions for 1H alert throttling.

    This is not a trade signal.  It is a noise gate: when price keeps rotating
    inside the same accepted value area, AlertBot should not keep creating fresh
    key-zone alerts from every upper/lower touch.
    """

    cfg = TREND_ENGINE_CONFIG["range_lock"]
    lookback = max(8, int(cfg.get("lookback_bars", 14)))
    if len(klines_1h) < lookback + 3:
        return {"active": False, "reason": "insufficient_history"}

    window = klines_1h[-lookback:]
    latest = window[-1]
    close = _f(latest.get("close"))
    atr = max(_f(latest.get("atr"), max(abs(close) * 0.004, 1.0)), 1e-9)

    lows = [_f(k.get("low"), close) for k in window]
    highs = [_f(k.get("high"), close) for k in window]
    closes = [_f(k.get("close"), close) for k in window]
    volumes = [_f(k.get("volume"), 0.0) for k in window]

    box_low = min(lows)
    box_high = max(highs)
    box_width = box_high - box_low
    range_atr = box_width / atr
    range_pct = box_width / max(abs(close), 1e-9)

    lower_band = box_low + box_width * 0.28
    upper_band = box_high - box_width * 0.28
    lower_touches = sum(1 for k in window if _f(k.get("low"), close) <= lower_band)
    upper_touches = sum(1 for k in window if _f(k.get("high"), close) >= upper_band)
    edge_touches = lower_touches + upper_touches

    msb_dir = str(msb.get("direction", "neutral"))
    leg_type = str(msb.get("leg_type", "SHORT"))
    msb_quality = int(msb.get("quality", 0) or 0)
    matrix_dir = str(matrix.get("matrix_direction", "neutral"))

    directional_breakout = False
    if len(closes) >= 3:
        prev_high = max(highs[:-1])
        prev_low = min(lows[:-1])
        breakout_pad = atr * float(cfg.get("breakout_accept_atr_mult", 0.35))
        directional_breakout = closes[-1] > prev_high + breakout_pad or closes[-1] < prev_low - breakout_pad

    vp = vp or {}
    value_acceptance = bool(vp.get("inside_value_area")) or bool(vp.get("near_hvn_or_poc")) or bool(vp.get("current_bin_is_hvn"))

    htf_text = str(htf_ctx.get("text", ""))
    htf_range_or_mixed = "震荡" in htf_text or str(htf_ctx.get("relation", "neutral")) == "neutral"

    short_structure = leg_type == "SHORT" or msb_dir == "neutral" or msb_quality < 18
    no_matrix_trend = matrix_dir == "neutral" or matrix_dir == msb_dir or leg_type == "SHORT"

    tight_enough = range_atr <= float(cfg.get("max_range_atr", 3.4)) or range_pct <= float(cfg.get("max_range_pct", 0.024))
    enough_edges = edge_touches >= int(cfg.get("min_edge_touches", 3))

    # Active when the market is rotating in the same box / accepted value area
    # without a real 1H expansion.  In a strong trend, this stays inactive.
    active = bool(
        tight_enough
        and enough_edges
        and not directional_breakout
        and (value_acceptance or htf_range_or_mixed or short_structure)
        and (short_structure or no_matrix_trend)
    )

    return {
        "active": active,
        "reason": "range_lock_active" if active else "range_lock_inactive",
        "box_low": round(box_low, 2),
        "box_high": round(box_high, 2),
        "box_mid": round((box_low + box_high) / 2.0, 2),
        "box_width_pct": round(range_pct, 5),
        "box_width_atr": round(range_atr, 3),
        "lower_touches": lower_touches,
        "upper_touches": upper_touches,
        "edge_touches": edge_touches,
        "cluster": _cluster_key(box_low, box_high, atr, close),
        "directional_breakout": directional_breakout,
        "value_acceptance": value_acceptance,
        "latest_volume_ratio": (volumes[-1] / max(_avg(volumes[:-1]), 1e-9)) if len(volumes) >= 3 else 1.0,
    }


def is_strong_sweep_reversal(
    side: str,
    latest: dict[str, Any],
    prev2_close: float,
    zone: tuple[float, float],
    atr: float,
    aux: dict[str, Any],
    range_lock: dict[str, Any] | None = None,
) -> bool:
    """Allow rare formal trial alerts after a true sweep + sharp reclaim/reject.

    This preserves the user's "after a waterfall, watch the bounce" use case
    without reopening hourly trial spam inside a pure range.
    """

    range_lock = range_lock or {}
    cfg = TREND_ENGINE_CONFIG["range_lock"]
    open_ = _f(latest.get("open"))
    close = _f(latest.get("close"))
    high = _f(latest.get("high"))
    low = _f(latest.get("low"))
    z_low, z_high = zone
    impulse = (close - float(prev2_close)) / max(float(atr), 1e-9)
    volume_ratio = float(aux.get("volume_ratio", 1.0) or 1.0)

    strong_reversal_atr = float(cfg.get("strong_reversal_atr", 1.35))
    min_vol = float(cfg.get("strong_reversal_volume_ratio", 1.15))
    box_low = _f(range_lock.get("box_low"), z_low)
    box_high = _f(range_lock.get("box_high"), z_high)

    if side == "lower":
        swept_low = low <= min(z_low, box_low) - atr * 0.10
        reclaimed = close >= z_high and close > open_
        return swept_low and reclaimed and impulse >= strong_reversal_atr and volume_ratio >= min_vol

    if side == "upper":
        swept_high = high >= max(z_high, box_high) + atr * 0.10
        rejected = close <= z_low and close < open_
        return swept_high and rejected and impulse <= -strong_reversal_atr and volume_ratio >= min_vol

    return False


def attach_range_lock_fields(decision: dict[str, Any], range_lock: dict[str, Any] | None) -> dict[str, Any]:
    if not range_lock:
        return decision
    out = dict(decision)
    out["range_lock_active"] = bool(range_lock.get("active", False))
    if range_lock.get("active", False):
        out["range_lock_cluster"] = range_lock.get("cluster", "")
        out["range_lock_box_low"] = range_lock.get("box_low")
        out["range_lock_box_high"] = range_lock.get("box_high")
        out["range_lock_width_atr"] = range_lock.get("box_width_atr")
    return out
