from __future__ import annotations

import math
from typing import Any


def _f(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        f = float(value)
        if math.isnan(f) or math.isinf(f):
            return default
        return f
    except (TypeError, ValueError):
        return default


def _percentile(values: list[float], pct: float) -> float:
    clean = sorted(v for v in values if v >= 0 and not math.isnan(v) and not math.isinf(v))
    if not clean:
        return 0.0
    if len(clean) == 1:
        return clean[0]
    rank = (pct / 100.0) * (len(clean) - 1)
    lo = int(math.floor(rank))
    hi = int(math.ceil(rank))
    if lo == hi:
        return clean[lo]
    weight = rank - lo
    return clean[lo] * (1.0 - weight) + clean[hi] * weight


def _bar_price(k: dict[str, Any]) -> float:
    high = _f(k.get("high"))
    low = _f(k.get("low"))
    close = _f(k.get("close"))
    if high > 0 and low > 0:
        return (high + low + close) / 3.0
    return close


def build_volume_profile_context(
    klines_1h: list[dict[str, Any]],
    lookback: int = 120,
    bins: int = 30,
    value_area_pct: float = 0.70,
) -> dict[str, Any]:
    """Approximate a Visible/Fixed Range Volume Profile from exchange candles.

    TradingView's exact Volume Profile values are not available from Binance
    candles.  This proxy is intentionally used only as a *filter* for AlertBot:
    - HVN/POC acts like accepted value / magnet context;
    - LVN/Volume Gap acts like a thin-air path where price can travel fast;
    - VAL/VAH decides whether a reclaim/rejection is actually accepted.
    It must not produce standalone trade alerts.
    """

    if len(klines_1h) < 20:
        close = _f(klines_1h[-1].get("close")) if klines_1h else 0.0
        return {
            "available": False,
            "price": close,
            "poc": close,
            "vah": close,
            "val": close,
            "position": "unknown",
            "current_bin_is_lvn": False,
            "current_bin_is_hvn": False,
            "near_hvn_or_poc": False,
            "reclaimed_val": False,
            "rejected_vah": False,
            "accepted_below_value": False,
            "accepted_above_value": False,
            "profile_note": "insufficient_history",
        }

    window = klines_1h[-lookback:]
    prices = [_bar_price(k) for k in window]
    lows = [_f(k.get("low"), p) for k, p in zip(window, prices)]
    highs = [_f(k.get("high"), p) for k, p in zip(window, prices)]
    min_price = min(lows)
    max_price = max(highs)
    close = _f(window[-1].get("close"), prices[-1])
    prev_close = _f(window[-2].get("close"), close)

    if max_price <= min_price:
        return {
            "available": False,
            "price": close,
            "poc": close,
            "vah": close,
            "val": close,
            "position": "unknown",
            "current_bin_is_lvn": False,
            "current_bin_is_hvn": False,
            "near_hvn_or_poc": False,
            "reclaimed_val": False,
            "rejected_vah": False,
            "accepted_below_value": False,
            "accepted_above_value": False,
            "profile_note": "flat_range",
        }

    bins = max(12, int(bins))
    step = (max_price - min_price) / float(bins)
    volumes = [0.0 for _ in range(bins)]

    for k in window:
        price = _bar_price(k)
        idx = int((price - min_price) / step)
        idx = max(0, min(bins - 1, idx))
        volumes[idx] += max(_f(k.get("volume"), 0.0), 0.0)

    total_volume = sum(volumes)
    if total_volume <= 0:
        return {
            "available": False,
            "price": close,
            "poc": close,
            "vah": close,
            "val": close,
            "position": "unknown",
            "current_bin_is_lvn": False,
            "current_bin_is_hvn": False,
            "near_hvn_or_poc": False,
            "reclaimed_val": False,
            "rejected_vah": False,
            "accepted_below_value": False,
            "accepted_above_value": False,
            "profile_note": "zero_volume",
        }

    centers = [min_price + (i + 0.5) * step for i in range(bins)]
    poc_idx = max(range(bins), key=lambda i: volumes[i])
    poc = centers[poc_idx]

    included: set[int] = set()
    cum = 0.0
    for idx in sorted(range(bins), key=lambda i: volumes[i], reverse=True):
        included.add(idx)
        cum += volumes[idx]
        if cum >= total_volume * value_area_pct:
            break

    val = min(min_price + i * step for i in included)
    vah = max(min_price + (i + 1) * step for i in included)

    nonzero = [v for v in volumes if v > 0]
    hvn_cut = _percentile(nonzero, 75)
    lvn_cut = _percentile(nonzero, 25)

    current_idx = int((close - min_price) / step)
    current_idx = max(0, min(bins - 1, current_idx))
    current_vol = volumes[current_idx]
    max_vol = max(volumes) if volumes else 1.0
    current_rel_vol = current_vol / max(max_vol, 1e-9)

    hvn_indices = [i for i, v in enumerate(volumes) if v >= hvn_cut and v > 0]
    lvn_indices = [i for i, v in enumerate(volumes) if v <= lvn_cut and v > 0]

    hvn_below = [centers[i] for i in hvn_indices if centers[i] <= close]
    hvn_above = [centers[i] for i in hvn_indices if centers[i] >= close]
    nearest_hvn_below = max(hvn_below) if hvn_below else None
    nearest_hvn_above = min(hvn_above) if hvn_above else None

    distance_to_poc = abs(close - poc) / max(abs(close), 1e-9)
    hvn_distances = [
        abs(close - x) / max(abs(close), 1e-9)
        for x in (nearest_hvn_below, nearest_hvn_above)
        if x is not None
    ]
    nearest_hvn_distance = min(hvn_distances) if hvn_distances else None

    if close < val:
        position = "below_value"
    elif close > vah:
        position = "above_value"
    else:
        position = "inside_value"

    reclaimed_val = prev_close < val <= close
    rejected_vah = prev_close > vah >= close
    accepted_below_value = close < val and prev_close < val
    accepted_above_value = close > vah and prev_close > vah

    return {
        "available": True,
        "price": round(close, 2),
        "poc": round(poc, 2),
        "vah": round(vah, 2),
        "val": round(val, 2),
        "position": position,
        "below_value_area": position == "below_value",
        "above_value_area": position == "above_value",
        "inside_value_area": position == "inside_value",
        "current_bin": current_idx,
        "current_bin_relative_volume": round(current_rel_vol, 4),
        "current_bin_is_lvn": current_idx in lvn_indices or current_rel_vol <= 0.35,
        "current_bin_is_hvn": current_idx in hvn_indices or current_rel_vol >= 0.75,
        "nearest_hvn_below": round(nearest_hvn_below, 2) if nearest_hvn_below is not None else None,
        "nearest_hvn_above": round(nearest_hvn_above, 2) if nearest_hvn_above is not None else None,
        "distance_to_poc_pct": round(distance_to_poc, 5),
        "nearest_hvn_distance_pct": round(nearest_hvn_distance, 5) if nearest_hvn_distance is not None else None,
        "near_hvn_or_poc": distance_to_poc <= 0.0025 or (nearest_hvn_distance is not None and nearest_hvn_distance <= 0.0025),
        "reclaimed_val": reclaimed_val,
        "rejected_vah": rejected_vah,
        "accepted_below_value": accepted_below_value,
        "accepted_above_value": accepted_above_value,
        "volume_gap_pressure": (current_idx in lvn_indices or current_rel_vol <= 0.35) and position != "inside_value",
        "profile_note": "proxy_from_1h_candles",
    }


def block_formal_long(
    htf_ctx: dict[str, Any],
    msb: dict[str, Any],
    matrix: dict[str, Any],
    aux: dict[str, Any],
    vp: dict[str, Any] | None,
) -> list[str]:
    """Return reasons why a 1H formal long alert should be downgraded/suppressed."""

    vp = vp or {}
    if not vp.get("available", False):
        return []

    reasons: list[str] = []
    h4 = str(htf_ctx.get("h4_direction") or htf_ctx.get("text", ""))
    relation = str(htf_ctx.get("relation", "neutral"))
    msb_dir = str(msb.get("direction", "neutral"))
    matrix_dir = str(matrix.get("matrix_direction", "neutral"))
    momentum = str(aux.get("momentum_desc", ""))

    bearish_background = h4 == "bear" or "偏空" in str(htf_ctx.get("text", "")) or relation in {"counter", "strong_counter"}
    not_accepted_value = bool(vp.get("accepted_below_value")) or (
        bool(vp.get("below_value_area")) and not bool(vp.get("reclaimed_val"))
    )
    thin_air_down = bool(vp.get("volume_gap_pressure")) and bool(vp.get("below_value_area"))
    supply_overhead = msb_dir == "bear" or matrix_dir == "bear"
    weak_momentum = "偏强" not in momentum and "买盘修复" not in momentum and "卖压释放" not in momentum

    if bearish_background and not_accepted_value:
        reasons.append("bearish_htf_below_value")
    if thin_air_down and weak_momentum:
        reasons.append("lvn_no_long_acceptance")
    if supply_overhead and bool(vp.get("below_value_area")):
        reasons.append("supply_overhead_value_not_reclaimed")
    if matrix_dir == "bear" and weak_momentum:
        reasons.append("matrix_bear_no_long_momentum")

    return reasons


def block_formal_short(
    htf_ctx: dict[str, Any],
    msb: dict[str, Any],
    matrix: dict[str, Any],
    aux: dict[str, Any],
    vp: dict[str, Any] | None,
) -> list[str]:
    """Return reasons why a 1H formal short alert should be downgraded/suppressed."""

    vp = vp or {}
    if not vp.get("available", False):
        return []

    reasons: list[str] = []
    h4 = str(htf_ctx.get("h4_direction") or htf_ctx.get("text", ""))
    relation = str(htf_ctx.get("relation", "neutral"))
    msb_dir = str(msb.get("direction", "neutral"))
    matrix_dir = str(matrix.get("matrix_direction", "neutral"))
    momentum = str(aux.get("momentum_desc", ""))

    bullish_background = h4 == "bull" or "偏多" in str(htf_ctx.get("text", "")) or relation in {"counter", "strong_counter"}
    not_rejected_value = bool(vp.get("accepted_above_value")) or (
        bool(vp.get("above_value_area")) and not bool(vp.get("rejected_vah"))
    )
    thin_air_up = bool(vp.get("volume_gap_pressure")) and bool(vp.get("above_value_area"))
    demand_under = msb_dir == "bull" or matrix_dir == "bull"
    weak_short_momentum = "偏弱" not in momentum and "卖压释放" not in momentum and "买盘衰减" not in momentum

    if bullish_background and not_rejected_value:
        reasons.append("bullish_htf_above_value")
    if thin_air_up and weak_short_momentum:
        reasons.append("lvn_no_short_rejection")
    if demand_under and bool(vp.get("above_value_area")):
        reasons.append("demand_under_value_not_rejected")
    if matrix_dir == "bull" and weak_short_momentum:
        reasons.append("matrix_bull_no_short_momentum")

    return reasons


def attach_vp_fields(decision: dict[str, Any], vp: dict[str, Any] | None, reasons: list[str] | None = None) -> dict[str, Any]:
    """Attach compact internal fields for logs/debugging without affecting copy."""

    if not vp:
        return decision
    out = dict(decision)
    out["vp_position"] = vp.get("position", "unknown")
    out["vp_poc"] = vp.get("poc")
    out["vp_vah"] = vp.get("vah")
    out["vp_val"] = vp.get("val")
    out["vp_current_bin_is_lvn"] = bool(vp.get("current_bin_is_lvn", False))
    out["vp_near_hvn_or_poc"] = bool(vp.get("near_hvn_or_poc", False))
    if reasons:
        out["vp_filter_reasons"] = ",".join(reasons)
    return out
