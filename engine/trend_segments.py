from __future__ import annotations

from typing import Any

from engine.framework import relation_to_htf
from engine.trend_config import TREND_ENGINE_CONFIG
from engine.volume_profile import attach_vp_fields, block_formal_long, block_formal_short


def apply_higher_timeframe_bias(base_score: int, relation: str) -> tuple[int, int, bool]:
    cfg = TREND_ENGINE_CONFIG["score"]
    if relation == "aligned":
        delta = cfg["htf_aligned_bonus"]
    elif relation == "counter":
        delta = cfg["htf_counter_penalty"]
    elif relation == "strong_counter":
        delta = cfg["htf_strong_counter_penalty"]
    else:
        delta = 0

    score = base_score + delta
    filtered = (
        relation == "strong_counter"
        and score < cfg["strong_counter_suppress_below"]
        and base_score <= cfg["medium_quality_max"]
    )
    return score, delta, filtered


def _direction_from_msb(msb_direction: str) -> str:
    if msb_direction == "bull":
        return "long"
    if msb_direction == "bear":
        return "short"
    return "neutral"


def _matching_sweep(direction: str, liq: dict[str, Any]) -> bool:
    sweep_type = liq.get("sweep_type", "none")
    reclaim_or_reject = liq.get("reclaim_or_reject", "none")
    if direction == "long":
        return sweep_type == "sellside" and reclaim_or_reject == "reclaim"
    if direction == "short":
        return sweep_type == "buyside" and reclaim_or_reject == "reject"
    return False


def decide_trend_segment(
    symbol: str,
    timeframe: str,
    htf_ctx: dict[str, Any],
    liq: dict[str, Any],
    msb: dict[str, Any],
    matrix: dict[str, Any],
    aux: dict[str, Any],
    trend_state: dict[str, Any] | None = None,
    vp: dict[str, Any] | None = None,
    ict: dict[str, Any] | None = None,
) -> dict[str, Any]:
    trend_state = trend_state or {}
    ict = ict or {}
    cfg = TREND_ENGINE_CONFIG["score"]

    ict_direction = str(ict.get("structure_direction", "neutral"))
    ict_event = str(ict.get("structure_event", "none"))
    ict_event_age = ict.get("structure_event_age")
    fresh_ict_structure = ict_event_age is not None and float(ict_event_age) <= 4 and ict_event != "none"
    direction = _direction_from_msb(ict_direction if ict_direction in {"bull", "bear"} else str(msb.get("direction", "neutral")))
    leg_type = str(msb.get("leg_type", "SHORT"))
    has_recent_sweep = bool(liq.get("recent_sweep_valid", False)) and liq.get("reclaim_or_reject") != "none"
    has_sweep = has_recent_sweep and _matching_sweep(direction, liq)
    ict_liquidity_event = str((ict.get("liquidity") or {}).get("event", "none")) if isinstance(ict.get("liquidity"), dict) else "none"
    if direction == "long" and ict_liquidity_event == "sellside_sweep_reclaim":
        has_sweep = True
    elif direction == "short" and ict_liquidity_event == "buyside_sweep_reject":
        has_sweep = True
    same_trend = trend_state.get("direction") == direction and bool(trend_state.get("has_snapshot", False))

    alert_type = "NO_TRADE_RANGE"
    tradable_leg = leg_type in {"MID", "LONG", "EXTENDED"}
    if direction != "neutral":
        structure_shift_ready = fresh_ict_structure or str(msb.get("structure_event", "none")) in {"bullish_msb", "bearish_msb"}
        if has_sweep and tradable_leg and (structure_shift_ready or not ict):
            alert_type = "BULLISH_STRUCTURE_SHIFT" if direction == "long" else "BEARISH_STRUCTURE_SHIFT"
        elif same_trend and tradable_leg and (not fresh_ict_structure or "bos" in ict_event or str(msb.get("direction")) in {"bull", "bear"}):
            alert_type = "BULLISH_CONTINUATION" if direction == "long" else "BEARISH_CONTINUATION"

    liq_score = 12 if has_sweep else 2
    msb_score = int(msb.get("quality", 0))
    expected_matrix_direction = "bull" if direction == "long" else "bear" if direction == "short" else "neutral"
    matrix_score = 6 if direction != "neutral" and matrix.get("matrix_direction") == expected_matrix_direction else 0
    ict_score = 8 if fresh_ict_structure and ict_direction == expected_matrix_direction else 3 if ict_direction == expected_matrix_direction else 0
    momentum_desc = str(aux.get("momentum_desc", "动能 一般"))
    temperature_desc = str(aux.get("temperature_desc", "热度 中性"))
    aux_score = 4 if (("偏强" in momentum_desc and direction == "long") or ("偏弱" in momentum_desc and direction == "short")) else 0

    base_score = liq_score + int(msb_score * 0.75) + matrix_score + ict_score + aux_score
    htf_relation = relation_to_htf(htf_ctx, direction)
    candidate_htf = {**htf_ctx, "relation": htf_relation}
    score, htf_delta, htf_filtered = apply_higher_timeframe_bias(base_score, htf_relation)

    suppress_reason = ""
    if direction == "neutral":
        suppress_reason = "neutral_direction"
    elif has_sweep and leg_type == "SHORT":
        suppress_reason = "short_structure_leg"
    elif not has_sweep and not same_trend:
        suppress_reason = "no_sweep_no_trend_state"
    elif has_sweep and ict and not fresh_ict_structure and alert_type == "NO_TRADE_RANGE":
        suppress_reason = "sweep_without_fresh_mss_choch"
    elif htf_filtered and alert_type.endswith("STRUCTURE_SHIFT"):
        suppress_reason = "medium_quality_1h_against_strong_4h"
    elif score < cfg["min_alert_score"]:
        suppress_reason = "below_min_score"

    vp_reasons: list[str] = []
    if alert_type != "NO_TRADE_RANGE" and suppress_reason == "":
        if direction == "long":
            vp_reasons = block_formal_long(candidate_htf, msb, matrix, aux, vp)
        elif direction == "short":
            vp_reasons = block_formal_short(candidate_htf, msb, matrix, aux, vp)

        # Volume Profile is a filter, not a standalone signal.  A high-quality
        # confirmed structure can still pass, but medium trial/continuation
        # alerts must not fight value acceptance, HVN/POC pressure, or LVN
        # thin-air continuation.
        if vp_reasons and (alert_type.endswith("CONTINUATION") or score < 72):
            suppress_reason = "vp_value_filter_" + vp_reasons[0]

    should_alert = alert_type != "NO_TRADE_RANGE" and suppress_reason == ""

    if alert_type.endswith("CONTINUATION"):
        zone_source = "mid_continuation_zone"
        zone = tuple(msb["mid_observe_zone"])
    elif has_sweep:
        matching_ict_zone = ict.get("bullish_nearest") if direction == "long" else ict.get("bearish_nearest")
        matching_ict_distance = ict.get("bullish_distance_atr") if direction == "long" else ict.get("bearish_distance_atr")
        if matching_ict_distance is not None and float(matching_ict_distance) > 3.0:
            matching_ict_zone = None
        if matching_ict_zone:
            zone_source = "ict_plus_ob" if direction == "long" else "ict_minus_ob"
            zone = tuple(matching_ict_zone)
        else:
            zone_source = "structure_shift_zone"
            zone = tuple(msb["structure_zone"])
    else:
        zone_source = "context_zone"
        zone = tuple(msb["order_block_zone"])

    if alert_type.endswith("STRUCTURE_SHIFT"):
        invalid_level = liq.get("sweep_level")
        if invalid_level is None:
            invalid_level = liq["prev_low"] if direction == "long" else liq["prev_high"]
    else:
        invalid_level = liq["prev_low"] if direction == "long" else liq["prev_high"]

    decision = {
        "symbol": symbol,
        "timeframe": timeframe,
        "alert_type": alert_type,
        "direction": direction,
        "price": float(aux.get("price", 0.0) or 0.0),
        "score": score,
        "score_breakdown": {
            "liquidity": liq_score,
            "msb_ob": int(msb_score * 0.75),
            "htf_context": htf_delta,
            "classical_trend": matrix_score,
            "ict_structure": ict_score,
            "aux_filters": aux_score,
            "penalty_reason": suppress_reason,
        },
        "htf_context": htf_ctx.get("text", "4H 背景中性"),
        "htf_relation": htf_relation,
        "sweep_type": liq.get("sweep_type", "none"),
        "sweep_level": liq.get("sweep_level"),
        "reclaim_or_reject": liq.get("reclaim_or_reject", "none"),
        "bars_since_sweep": liq.get("bars_since_sweep"),
        "msb_direction": msb.get("direction", "neutral"),
        "msb_quality": msb_score,
        "msb_atr_ratio": msb.get("metrics", {}).get("atr_move", 0.0),
        "msb_range_ratio": msb.get("metrics", {}).get("range_ratio", 0.0),
        "msb_body_quality": msb.get("metrics", {}).get("body_quality", 0.0),
        "ict_structure_direction": ict_direction,
        "ict_structure_event": ict_event,
        "ict_structure_event_age": ict_event_age,
        "zone_source": zone_source,
        "zone_low": zone[0],
        "zone_high": zone[1],
        "zone": zone,
        "invalid_level": float(invalid_level),
        "should_alert": should_alert,
        "suppress_reason": suppress_reason,
        "state_version": leg_type,
        "momentum_desc": momentum_desc,
        "temperature_desc": temperature_desc,
    }
    return attach_vp_fields(decision, vp, vp_reasons)
