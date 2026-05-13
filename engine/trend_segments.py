from __future__ import annotations

from typing import Any
from engine.trend_config import TREND_ENGINE_CONFIG


def apply_higher_timeframe_bias(base_score: int, relation: str) -> tuple[int, int, bool]:
    cfg = TREND_ENGINE_CONFIG["score"]
    delta = cfg["htf_aligned_bonus"] if relation == "aligned" else cfg["htf_counter_penalty"] if relation == "counter" else cfg["htf_strong_counter_penalty"] if relation == "strong_counter" else 0
    score = base_score + delta
    return score, delta, relation == "strong_counter" and score < cfg["strong_counter_suppress_below"] and base_score <= cfg["medium_quality_max"]


def decide_trend_segment(symbol: str, timeframe: str, htf_ctx: dict[str, Any], liq: dict[str, Any], msb: dict[str, Any], matrix: dict[str, Any], aux: dict[str, Any], trend_state: dict[str, Any] | None = None) -> dict[str, Any]:
    trend_state = trend_state or {}
    cfg = TREND_ENGINE_CONFIG["score"]
    direction = "long" if msb["direction"] == "bull" else "short" if msb["direction"] == "bear" else "neutral"
    has_recent_sweep = liq.get("recent_sweep_valid", False) and liq["reclaim_or_reject"] != "none"
    sweep_match = (direction == "long" and liq["sweep_type"] == "sellside" and liq["reclaim_or_reject"] == "reclaim") or (direction == "short" and liq["sweep_type"] == "buyside" and liq["reclaim_or_reject"] == "reject")
    has_sweep = has_recent_sweep and sweep_match
    same_trend = trend_state.get("direction") == direction and trend_state.get("has_snapshot", False)

    alert_type = "NO_TRADE_RANGE"
    if direction != "neutral":
        if has_sweep:
            alert_type = "BULLISH_STRUCTURE_SHIFT" if direction == "long" else "BEARISH_STRUCTURE_SHIFT"
        elif same_trend and msb["leg_type"] in {"MID", "LONG", "EXTENDED"}:
            alert_type = "BULLISH_CONTINUATION" if direction == "long" else "BEARISH_CONTINUATION"

    liq_score = 12 if has_sweep else 2
    msb_score = msb["quality"]
    matrix_score = 6 if matrix.get("matrix_direction") == ("bull" if direction == "long" else "bear") else 0
    aux_score = 4 if ("偏强" in aux["momentum_desc"] and direction == "long") or ("偏弱" in aux["momentum_desc"] and direction == "short") else 0
    base_score = liq_score + int(msb_score * 0.75) + matrix_score + aux_score
    score, htf_delta, htf_filtered = apply_higher_timeframe_bias(base_score, htf_ctx["relation"])

    suppress_reason = ""
    if direction == "neutral":
        suppress_reason = "neutral_direction"
    elif not has_sweep and not same_trend:
        suppress_reason = "no_sweep_no_trend_state"
    elif htf_filtered and alert_type.endswith("STRUCTURE_SHIFT"):
        suppress_reason = "medium_quality_1h_against_strong_4h"
    elif score < cfg["min_alert_score"]:
        suppress_reason = "below_min_score"

    should_alert = alert_type != "NO_TRADE_RANGE" and suppress_reason == ""
    zone_source = "mid_continuation_zone" if alert_type.endswith("CONTINUATION") else "structure_shift_zone" if has_sweep else "context_zone"
    zone = msb["mid_observe_zone"] if zone_source == "mid_continuation_zone" else msb["structure_zone"] if zone_source == "structure_shift_zone" else msb["order_block_zone"]

    return {"symbol": symbol, "timeframe": timeframe, "alert_type": alert_type, "direction": direction, "score": score, "score_breakdown": {"liquidity": liq_score, "msb_ob": int(msb_score * 0.75), "htf_context": htf_delta, "trend_matrix": matrix_score, "aux_filters": aux_score, "penalty_reason": suppress_reason}, "htf_context": htf_ctx["text"], "htf_relation": htf_ctx["relation"], "sweep_type": liq["sweep_type"], "sweep_level": liq["sweep_level"], "reclaim_or_reject": liq["reclaim_or_reject"], "msb_direction": msb["direction"], "msb_quality": msb["quality"], "msb_atr_ratio": msb["metrics"]["atr_move"], "msb_range_ratio": msb["metrics"]["range_ratio"], "msb_body_quality": msb["metrics"]["body_quality"], "zone_source": zone_source, "zone_low": zone[0], "zone_high": zone[1], "zone": zone, "invalid_level": liq["prev_low"] if direction == "long" else liq["prev_high"], "should_alert": should_alert, "suppress_reason": suppress_reason, "state_version": msb["leg_type"], "momentum_desc": aux["momentum_desc"], "temperature_desc": aux["temperature_desc"]}
