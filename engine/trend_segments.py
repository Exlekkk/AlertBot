from __future__ import annotations

from typing import Any

from engine.trend_config import TREND_ENGINE_CONFIG


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
) -> dict[str, Any]:
    trend_state = trend_state or {}
    cfg = TREND_ENGINE_CONFIG["score"]

    direction = _direction_from_msb(str(msb.get("direction", "neutral")))
    leg_type = str(msb.get("leg_type", "SHORT"))
    has_recent_sweep = bool(liq.get("recent_sweep_valid", False)) and liq.get("reclaim_or_reject") != "none"
    has_sweep = has_recent_sweep and _matching_sweep(direction, liq)
    same_trend = trend_state.get("direction") == direction and bool(trend_state.get("has_snapshot", False))

    alert_type = "NO_TRADE_RANGE"
    tradable_leg = leg_type in {"MID", "LONG", "EXTENDED"}
    if direction != "neutral":
        if has_sweep and tradable_leg:
            alert_type = "BULLISH_STRUCTURE_SHIFT" if direction == "long" else "BEARISH_STRUCTURE_SHIFT"
        elif same_trend and tradable_leg:
            alert_type = "BULLISH_CONTINUATION" if direction == "long" else "BEARISH_CONTINUATION"

    liq_score = 12 if has_sweep else 2
    msb_score = int(msb.get("quality", 0))
    expected_matrix_direction = "bull" if direction == "long" else "bear" if direction == "short" else "neutral"
    matrix_score = 6 if direction != "neutral" and matrix.get("matrix_direction") == expected_matrix_direction else 0
    momentum_desc = str(aux.get("momentum_desc", "动能 一般"))
    temperature_desc = str(aux.get("temperature_desc", "热度 中性"))
    aux_score = 4 if (("偏强" in momentum_desc and direction == "long") or ("偏弱" in momentum_desc and direction == "short")) else 0

    base_score = liq_score + int(msb_score * 0.75) + matrix_score + aux_score
    htf_relation = str(htf_ctx.get("relation", "neutral"))
    score, htf_delta, htf_filtered = apply_higher_timeframe_bias(base_score, htf_relation)

    suppress_reason = ""
    if direction == "neutral":
        suppress_reason = "neutral_direction"
    elif has_sweep and leg_type == "SHORT":
        suppress_reason = "short_structure_leg"
    elif not has_sweep and not same_trend:
        suppress_reason = "no_sweep_no_trend_state"
    elif htf_filtered and alert_type.endswith("STRUCTURE_SHIFT"):
        suppress_reason = "medium_quality_1h_against_strong_4h"
    elif score < cfg["min_alert_score"]:
        suppress_reason = "below_min_score"

    should_alert = alert_type != "NO_TRADE_RANGE" and suppress_reason == ""

    if alert_type.endswith("CONTINUATION"):
        zone_source = "mid_continuation_zone"
        zone = tuple(msb["mid_observe_zone"])
    elif has_sweep:
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

    return {
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
            "trend_matrix": matrix_score,
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
