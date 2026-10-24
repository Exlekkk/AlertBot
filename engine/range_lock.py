"""Range / balance gate.

Maps the candle-approx range detector onto legacy box fields
(`active` / `box_*` / `accepted_breakout` / `cluster`) plus an `auto_range`
payload. Pending breaks are not accepted_breakout.
"""
from __future__ import annotations

import hashlib
from typing import Any

from engine.auto_range import build_auto_range_context
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
    bucket = max(
        float(atr) * float(TREND_ENGINE_CONFIG["range_lock"].get("box_shift_atr_mult", 1.25)),
        abs(float(close)) * 0.006,
        1.0,
    )
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
    ict: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Balance / same-box noise gate.

    Range detection is candle-approx; ICT coexist no longer forces an active box.
    """
    _ = (htf_ctx, liq, msb, matrix, aux, vp)  # keep legacy signature; trial reads new evidence
    ict = ict or {}
    auto_range = build_auto_range_context(klines_1h)

    latest = klines_1h[-1] if klines_1h else {}
    close = _f(latest.get("close"))
    atr = max(_f(auto_range.get("atr"), _f(latest.get("atr"), max(abs(close) * 0.004, 1.0))), 1e-9)

    state = str(auto_range.get("state", "none"))
    box_low = _f(auto_range.get("low"), float("nan"))
    box_high = _f(auto_range.get("high"), float("nan"))
    has_box = state in {"provisional", "live", "broken"} and box_low == box_low and box_high == box_high

    if not has_box and klines_1h:
        # Fallback box when no qualifying range; active still driven by conflict/state
        lookback = max(8, int(TREND_ENGINE_CONFIG["range_lock"].get("lookback_bars", 14)))
        window = klines_1h[-lookback:]
        box_low = min(_f(k.get("low"), close) for k in window)
        box_high = max(_f(k.get("high"), close) for k in window)

    last_event = auto_range.get("last_event")
    pending_break = auto_range.get("pending_break")
    # Only confirmed breakout_* sets accepted_breakout.
    # pending / deviation keep accepted_breakout=none so the same-box gate stays closed.
    if last_event == "breakout_up" and not pending_break:
        directional_breakout = True
        accepted_breakout = "up"
    elif last_event == "breakout_down" and not pending_break:
        directional_breakout = True
        accepted_breakout = "down"
    else:
        directional_breakout = False
        accepted_breakout = "none"

    # ICT coexist box force hard-deleted; range active comes from auto_range only.
    ict_ob_conflict = False
    # live/provisional (incl. pending break) keep the balance gate; confirmed broken opens it
    balance_active = state in {"provisional", "live"} or bool(pending_break)
    # After reclaim, state stays live → keep same-box suppression; event is for weighting
    active = bool(balance_active and not directional_breakout)

    box_width = max(box_high - box_low, 0.0)
    if box_width <= 0:
        box_position = "unknown"
    else:
        box_ratio = (close - box_low) / box_width
        box_position = "lower" if box_ratio <= 0.38 else "upper" if box_ratio >= 0.62 else "middle"

    volumes = [_f(k.get("volume"), 0.0) for k in klines_1h[-14:]] if klines_1h else []

    return {
        "active": active,
        "reason": "auto_range_balance" if balance_active else (
            "range_lock_active" if active else "range_lock_inactive"
        ),
        "box_low": round(box_low, 2),
        "box_high": round(box_high, 2),
        "box_mid": round((box_low + box_high) / 2.0, 2),
        "box_width_pct": round(box_width / max(abs(close), 1e-9), 5),
        "box_width_atr": round(box_width / atr, 3),
        "lower_touches": int(auto_range.get("lower_touches") or 0),
        "upper_touches": int(auto_range.get("upper_touches") or 0),
        "edge_touches": int(auto_range.get("lower_touches") or 0) + int(auto_range.get("upper_touches") or 0),
        "cluster": _cluster_key(box_low, box_high, atr, close) if has_box or active else "",
        "directional_breakout": directional_breakout,
        "accepted_breakout": accepted_breakout,
        "box_position": box_position,
        "value_acceptance": state in {"provisional", "live"},
        "ict_ob_conflict": ict_ob_conflict,
        "ict_ob_source": ict.get("source", "none"),
        "latest_volume_ratio": (volumes[-1] / max(_avg(volumes[:-1]), 1e-9)) if len(volumes) >= 3 else 1.0,
        # full range payload for newer consumers
        "auto_range": auto_range,
        "last_event": last_event,
        "pending_break": pending_break,
        "approx": True,
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
    """Allow rare post-waterfall strong reclaim trials (legacy behavior)."""
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
    # pass through range events for copy/weighting (not a solo trigger)
    auto_range = range_lock.get("auto_range") or {}
    if auto_range:
        out["auto_range_state"] = auto_range.get("state")
        out["auto_range_last_event"] = auto_range.get("last_event")
        out["auto_range_approx"] = True
    return out
