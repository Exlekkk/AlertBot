"""Independent 15m W-bottom / double-bottom demand-reclaim evidence.

Verification layer only (weight 0.2 in trial_decision). Never a solo formal
catalyst. Deliberately NOT a field-flip of ``detect_small_m_top`` /
``m15_supply_reject_m_top`` — own detector, own evidence key
``structure_15m_demand``, own reason tag ``m15_demand_reclaim_w_bottom``.

Purpose: bottom-fish + true vs false rebound (neckline reclaim vs fail).
"""
from __future__ import annotations

from typing import Any

from engine.structure import _atr_value, _price_tolerance, find_pivots


def detect_small_w_bottom(
    klines: list[dict],
    *,
    lookback: int = 48,
    atr_mult: float = 0.35,
    demand_zone: tuple[float, float] | None = None,
    max_bars_ago: int = 4,
) -> dict[str, Any] | None:
    """Detect a compact 15m W / double-bottom with demand reclaim.

    Requirements (structure common sense, not an M-top mirror):
    - two recent swing lows near equal, or both probing ``demand_zone``
    - a clear neckline peak between the lows
    - bullish reclaim after the right trough (close above the W low)
    - annotate ``neckline_reclaim`` (true rebound break) vs ``false_bounce``
      (pierce then fail back under the right low / mid)

    Returns None when no qualifying W is found.
    """

    if len(klines) < 12:
        return None
    window_start = max(0, len(klines) - lookback)
    _, pivot_lows = find_pivots(klines, left=1, right=1)
    recent = [i for i in pivot_lows if i >= window_start]
    last = len(klines) - 1
    # Fresh wick low may not be a confirmed pivot yet — allow as right trough.
    local_low_idx = min(
        range(max(window_start, last - 6), last + 1),
        key=lambda i: float(klines[i]["low"]),
    )
    if local_low_idx not in recent:
        recent.append(local_low_idx)
    recent = sorted(set(recent))
    if len(recent) < 2:
        return None

    tol = _price_tolerance(klines, atr_mult=atr_mult)
    demand = None
    if demand_zone is not None:
        demand = (
            min(float(demand_zone[0]), float(demand_zone[1])),
            max(float(demand_zone[0]), float(demand_zone[1])),
        )

    best: dict[str, Any] | None = None
    for i in range(len(recent) - 1):
        a = recent[i]
        b = recent[i + 1]
        if b - a < 2:
            continue
        if last - b > max_bars_ago:
            continue
        la = float(klines[a]["low"])
        lb = float(klines[b]["low"])
        neckline = max(float(klines[j]["high"]) for j in range(a, b + 1))
        w_low = min(la, lb)
        if neckline - w_low < tol * 0.8:
            continue  # flat, not a W

        near_equal = abs(la - lb) <= tol * 1.25
        taps_demand = False
        if demand is not None:
            pad = tol
            right_taps = lb <= demand[1] + pad and lb >= demand[0] - pad * 3
            left_near = abs(la - lb) <= max(tol * 2.8, (demand[1] - demand[0]) * 0.75) or (
                la <= demand[1] + pad * 2.5
            )
            taps_demand = bool(right_taps and left_near)
        if not (near_equal or taps_demand):
            continue

        # Reclaim: bullish reaction off the right trough (own logic vs M reject).
        right = klines[b]
        close_b = float(right["close"])
        open_b = float(right["open"])
        high_b = float(right["high"])
        low_b = float(right["low"])
        candle_range = max(high_b - low_b, 1e-9)
        lower_wick = min(open_b, close_b) - low_b
        reclaimed = (
            close_b > open_b
            and close_b >= w_low + tol * 0.25
            and lower_wick / candle_range >= 0.25
        )
        later = klines[b : last + 1]
        later_reclaim = any(
            float(k["close"]) > float(k["open"])
            and float(k["low"]) <= w_low + tol
            and float(k["close"]) >= w_low + tol * 0.25
            for k in later
        )
        if not (reclaimed or later_reclaim):
            continue

        # True vs false rebound: did price hold a neckline break?
        post = klines[b : last + 1]
        pierced_neck = any(float(k["high"]) >= neckline - tol * 0.5 for k in post)
        last_close = float(klines[last]["close"])
        neckline_reclaim = pierced_neck and last_close >= neckline - tol
        failed_back = pierced_neck and last_close < (w_low + neckline) * 0.5
        false_bounce = bool(pierced_neck and not neckline_reclaim and failed_back)

        candidate = {
            "active": True,
            "side": "long",
            "pattern": "small_w_bottom",
            "left_index": a,
            "right_index": b,
            "left_low": round(la, 2),
            "right_low": round(lb, 2),
            "neckline": round(neckline, 2),
            "w_low": round(w_low, 2),
            "bars_ago": last - b,
            "near_equal": near_equal,
            "taps_demand": taps_demand,
            "neckline_reclaim": neckline_reclaim,
            "false_bounce": false_bounce,
            "demand_zone": [round(demand[0], 2), round(demand[1], 2)] if demand else None,
        }
        best = candidate
    return best


def build_structure_15m_demand_context(
    klines_15m: list[dict],
    *,
    demand_zones: list[tuple[float, float]] | None = None,
) -> dict[str, Any]:
    """Bundle 15m W-bottom / demand-reclaim cues (independent of supply M-top)."""

    empty: dict[str, Any] = {
        "approx": True,
        "timeframe": "15m",
        "small_w_bottom": None,
        "demand_reclaim": False,
        "reclaim_low": None,
        "active": False,
        "reason": "insufficient_history",
    }
    if len(klines_15m) < 12:
        return empty

    atr = _atr_value(klines_15m)
    latest = klines_15m[-1]
    close = float(latest["close"])
    pad = max(atr * 0.2, abs(close) * 0.0006)

    chosen_demand = None
    demand_reclaim = False
    reclaim_low = None
    scan = klines_15m[-6:]
    for zone in demand_zones or []:
        zl, zh = min(zone), max(zone)
        for bar in scan:
            bl = float(bar["low"])
            bc = float(bar["close"])
            bo = float(bar["open"])
            # Dip into / under the demand band then close back up through it.
            if bl <= zh + pad and bc >= zl - pad and bc > bo:
                demand_reclaim = True
                chosen_demand = (zl, zh)
                reclaim_low = bl
                break
        if demand_reclaim:
            break
    # Fall back: strong lower-wick reclaim on a recent bar (no zone required).
    if not demand_reclaim:
        for bar in reversed(scan):
            bh = float(bar["high"])
            bc = float(bar["close"])
            bo = float(bar["open"])
            bl = float(bar["low"])
            candle_range = max(bh - bl, 1e-9)
            lower_wick = min(bo, bc) - bl
            if bc > bo and lower_wick / candle_range >= 0.35 and (bc - bl) >= atr * 0.35:
                demand_reclaim = True
                reclaim_low = bl
                break

    w_bottom = detect_small_w_bottom(
        klines_15m,
        demand_zone=chosen_demand,
        max_bars_ago=6,
    )
    if w_bottom is None and chosen_demand is not None:
        w_bottom = detect_small_w_bottom(
            klines_15m, demand_zone=chosen_demand, atr_mult=0.55, max_bars_ago=6
        )

    active = bool(w_bottom and w_bottom.get("active") and demand_reclaim)
    if active:
        reason = "m15_demand_reclaim_w_bottom"
    elif demand_reclaim:
        reason = "demand_reclaim_only"
    elif w_bottom:
        reason = "w_bottom_only"
    else:
        reason = "no_pattern"

    return {
        "approx": True,
        "timeframe": "15m",
        "small_w_bottom": w_bottom,
        "demand_reclaim": demand_reclaim,
        "reclaim_low": round(float(reclaim_low), 2) if reclaim_low is not None else None,
        "demand_zone": [round(chosen_demand[0], 2), round(chosen_demand[1], 2)] if chosen_demand else None,
        "active": active,
        "reason": reason,
    }
