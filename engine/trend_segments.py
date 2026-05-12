from __future__ import annotations

from typing import Any

from engine.trend_config import TREND_ENGINE_CONFIG


def apply_higher_timeframe_bias(base_score: int, relation: str) -> tuple[int, int, bool]:
    cfg = TREND_ENGINE_CONFIG["score"]
    delta = 0
    if relation == "aligned":
        delta = cfg["htf_aligned_bonus"]
    elif relation == "counter":
        delta = cfg["htf_counter_penalty"]
    elif relation == "strong_counter":
        delta = cfg["htf_strong_counter_penalty"]
    score = base_score + delta
    filter_by_htf = relation == "strong_counter" and score < cfg["strong_counter_suppress_below"] and base_score <= cfg["medium_quality_max"]
    return score, delta, filter_by_htf


def decide_trend_segment(symbol: str, timeframe: str, htf_ctx: dict[str, Any], liq: dict[str, Any], msb: dict[str, Any], matrix: dict[str, Any], aux: dict[str, Any]) -> dict[str, Any]:
    cfg = TREND_ENGINE_CONFIG["score"]
    direction = "long" if msb["direction"] == "bull" else "short" if msb["direction"] == "bear" else "neutral"
    if direction == "neutral":
        alert_type = "NO_TRADE_RANGE"
    elif msb["leg_type"] == "MID":
        alert_type = "BULLISH_CONTINUATION" if direction == "long" else "BEARISH_CONTINUATION"
    else:
        alert_type = "BULLISH_STRUCTURE_SHIFT" if direction == "long" else "BEARISH_STRUCTURE_SHIFT"

    liquidity_score = 12 if liq["sweep_type"] != "none" else 4
    msb_score = msb["quality"]
    matrix_score = 6 if matrix.get("matrix_direction") == ("bull" if direction == "long" else "bear") else 0
    aux_score = 4 if "偏强" in aux["momentum_desc"] and direction == "long" else 4 if "偏弱" in aux["momentum_desc"] and direction == "short" else 0
    base_score = liquidity_score + int(msb_score * 0.75) + matrix_score + aux_score

    score, htf_delta, filtered_by_htf = apply_higher_timeframe_bias(base_score, htf_ctx["relation"])
    should_alert = direction != "neutral" and score >= cfg["min_alert_score"] and not filtered_by_htf
    suppress_reason = "medium_quality_1h_against_strong_4h" if filtered_by_htf else "below_min_score" if direction != "neutral" and score < cfg["min_alert_score"] else ""

    zone_source = "structure_shift_zone" if msb["leg_type"] in {"LONG", "EXTENDED"} else "mid_continuation_zone" if msb["leg_type"] == "MID" else "context_zone"
    zone = msb["structure_zone"] if zone_source == "structure_shift_zone" else msb["mid_observe_zone"] if zone_source == "mid_continuation_zone" else msb["order_block_zone"]

    score_breakdown = {
        "liquidity": liquidity_score,
        "msb_ob": int(msb_score * 0.75),
        "htf_context": htf_delta,
        "trend_matrix": matrix_score,
        "aux_filters": aux_score,
        "penalty_reason": suppress_reason,
    }
    debug = {
        "symbol": symbol, "timeframe": timeframe, "alert_type": alert_type, "direction": direction, "score": score,
        "score_breakdown": score_breakdown, "htf_context": htf_ctx["text"], "htf_relation": htf_ctx["relation"],
        "sweep_type": liq["sweep_type"], "sweep_level": liq["sweep_level"], "reclaim_or_reject": liq["reclaim_or_reject"],
        "msb_direction": msb["direction"], "msb_quality": msb["quality"], "msb_atr_ratio": msb["metrics"]["atr_move"],
        "msb_range_ratio": msb["metrics"]["range_ratio"], "msb_body_quality": msb["metrics"]["body_quality"],
        "zone_source": zone_source, "zone_low": zone[0], "zone_high": zone[1],
        "invalid_level": liq["prev_low"] if direction == "long" else liq["prev_high"], "should_alert": should_alert,
        "suppress_reason": suppress_reason,
    }
    return {**debug, "zone": zone, "state_version": msb["leg_type"], "momentum_desc": aux["momentum_desc"], "temperature_desc": aux["temperature_desc"]}
