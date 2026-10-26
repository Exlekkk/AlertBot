"""Controlled forming-volume observations using closed 1H structure only."""
from __future__ import annotations

import math
import os
from typing import Any

from engine.key_zones import _select_zone
from engine.trial_decision import _box_context, assess_trial_candidate, build_trial_context
from engine.volume_profile import block_formal_long, block_formal_short
from engine.x_signals import MIN_15M_ABNORMAL_VOLUME, MIN_1H_ABNORMAL_VOLUME

INTERVAL_MS = {"15m": 900_000, "1h": 3_600_000}


def early_observation_mode() -> str:
    mode = os.getenv("SMCT_EARLY_OBSERVATION_MODE", "off").strip().lower()
    return mode if mode in {"off", "shadow", "live"} else "off"


def evaluate_early_observation(
    symbol: str, timeframe: str, raw: list[dict], closed_1h: list[dict],
    htf: dict, liq: dict, msb: dict, matrix: dict, aux: dict,
    vp: dict, range_lock: dict, evidence: dict,
    *, now_ms: int, observation_state: dict | None = None,
) -> dict[str, Any]:
    """Volume is a timing catalyst, never forming structure/acceptance evidence.

    Absolute volume and ratio must pass on the SAME source timeframe. Ratio
    uses 20 completed bars, excluding the forming bar; no volume extrapolation.
    No state writes, pending confirmations or structural builders on raw data.
    """
    result: dict[str, Any] = {
        "symbol": symbol, "timeframe": timeframe, "should_alert": False,
        "forming": True, "closed_confirmation": False,
        "suppress_reason": "insufficient_history",
    }
    def reject(reason: str) -> dict:
        return dict(result, suppress_reason=reason)

    if timeframe not in INTERVAL_MS or len(raw) < 21 or len(closed_1h) < 40:
        return result
    duration = INTERVAL_MS[timeframe]
    k = dict(raw[-1])
    try:
        stamp = int(k["open_time"])
        end = int(k["close_time"])
        numbers = [float(k[key]) for key in ("open", "high", "low", "close", "volume")]
        if not all(math.isfinite(n) for n in numbers):
            return reject("invalid_forming_data")
        o, high, low, price, volume = numbers
        if min(o, high, low, price) <= 0 or volume < 0 or not low <= min(o, price) <= max(o, price) <= high:
            return reject("invalid_forming_data")
        if stamp % duration or end != stamp + duration - 1 or not stamp <= now_ms <= end:
            return reject("not_current_forming_candle")
        # Refuse missing/duplicate/out-of-order history and boundary races.
        history = raw[-21:-1]
        if any(int(b["open_time"]) != stamp - (20-i)*duration or int(b["close_time"]) != int(b["open_time"])+duration-1 for i, b in enumerate(history)):
            return reject("non_contiguous_history")
        context_stamp = int(closed_1h[-1]["open_time"])
        if context_stamp != now_ms // INTERVAL_MS["1h"] * INTERVAL_MS["1h"] - INTERVAL_MS["1h"]:
            return reject("stale_closed_structure")
        volumes = [float(b["volume"]) for b in history]
        if any(not math.isfinite(v) or v < 0 for v in volumes):
            return reject("invalid_volume_history")
        mean = sum(volumes) / 20
        ratio = volume / mean if mean > 0 else 0
    except (KeyError, TypeError, ValueError, OverflowError):
        return reject("invalid_forming_data")
    result.update(open_time=stamp, volume=volume, volume_ratio=round(ratio, 3), structure_open_time=context_stamp)
    floor = MIN_15M_ABNORMAL_VOLUME if timeframe == "15m" else MIN_1H_ABNORMAL_VOLUME
    if volume <= floor or ratio < 1.8:
        return reject("volume_not_abnormal")
    if price == o:
        return reject("flat_forming_body")

    # All anchors and scores were built on closed 1H bars. Only the final price
    # interaction is inspected on raw data; never run IFVG/sweep/range on it.
    k.update(atr=closed_1h[-1]["atr"], forming=True)
    selected = _select_zone(closed_1h + [k], liq, msb, evidence_bundle=evidence)
    if not selected or selected["source"] not in {"ifvg_zone", "fibonacci_ote"}:
        return reject("no_clear_structure_location")
    side = "long" if selected["side"] == "lower" else "short"
    if (side == "long" and price <= o) or (side == "short" and price >= o):
        return reject("forming_reaction_against_side")
    if timeframe == "1h" and observation_state:
        last = observation_state.get("last_formal_open_time")
        last_side = observation_state.get("last_formal_side")
        if last is not None and stamp-int(last) < INTERVAL_MS["1h"]*4 and last_side == selected["side"]:
            return reject("recent_closed_observation")
    filters = block_formal_long(htf, msb, matrix, aux, vp) if side == "long" else block_formal_short(htf, msb, matrix, aux, vp)
    if filters:
        return reject("vp_value_filter_"+filters[0])
    zone = tuple(selected["zone"])
    atr = float(k["atr"])
    if atr <= 0 or (min(abs(price-zone[0]), abs(price-zone[1])) > atr * 0.35 and not zone[0] <= price <= zone[1]):
        return reject("too_far_from_structure")
    ctx = build_trial_context(closed_1h, htf, liq, msb, matrix, aux, vp=vp, range_lock=range_lock, evidence_bundle=evidence)
    _, _, _, ctx["box_ratio"], ctx["box_position"] = _box_context(price, range_lock, {})
    ctx["scores"][side] += 1.5
    ctx["evidence"][side].append("forming_abnormal_volume:+1.50")
    # Preserve closed formal cooldowns as read-only context for 1H. The 15m
    # lane never reads/writes the 1H delivery or observation state.
    invalid = min(low, zone[0])-atr*0.05 if side == "long" else max(high, zone[1])+atr*0.05
    assessment = assess_trial_candidate(
        side, "LOWER_KEY_ZONE_TEST" if side == "long" else "UPPER_KEY_ZONE_TEST",
        zone, invalid, k, float(closed_1h[-2]["close"]), selected["source"],
        str(selected.get("interaction", "inside")), ctx,
        observation_state if timeframe == "1h" else {}, stamp,
    )
    result.update(direction=side, zone=zone, invalid_level=round(invalid, 2), price=price,
                  trial_quality_blocks=assessment["hard_blocks"], trial_score=assessment["score"],
                  trial_evidence=assessment["reasons"])
    if not assessment["promote_early"]:
        return reject("trial_quality_" + (assessment["hard_blocks"][0] if assessment["hard_blocks"] else "below_early_threshold"))
    result.update(
        should_alert=True, suppress_reason="", htf_context=htf.get("text", "4H 背景中性"),
        zone_source=selected["source"], evidence={**evidence, "forming_volume": {
            "timeframe": timeframe, "open_time": stamp, "volume": volume,
            "ratio": round(ratio, 3), "confirmed": False}},
        alert_type=("PREALERT_LONG" if side == "long" else "PREALERT_SHORT") if timeframe == "15m" else
                   ("EARLY_LONG_TRIAL" if side == "long" else "EARLY_SHORT_TRIAL"),
        state_version="FORMING_OBSERVATION", score=assessment["score"],
    )
    return result
