from __future__ import annotations

from typing import Any

from engine.trend_config import TREND_ENGINE_CONFIG


def classify_msb_leg(atr_move: float, range_ratio: float, body_quality: float, position_score: float) -> str:
    c = TREND_ENGINE_CONFIG["msb"]
    weak_count = sum([
        atr_move < c["atr_short_max"],
        range_ratio < c["range_short_max"],
        body_quality < c["body_short_max"],
        position_score < c["position_short_max"],
    ])
    if weak_count >= c["short_weak_count_min"]:
        return "SHORT"
    if atr_move >= c["atr_extended_min"] or range_ratio >= c["range_extended_min"]:
        return "EXTENDED"
    if atr_move >= c["atr_long_min"] and range_ratio >= c["range_long_min"] and body_quality >= c["body_long_min"] and position_score >= c["position_long_min"]:
        return "LONG"
    return "MID"


def build_msb_ob_context(klines_1h: list[dict[str, Any]], liquidity_ctx: dict[str, Any]) -> dict[str, Any]:
    zcfg = TREND_ENGINE_CONFIG["zone"]
    latest, prev = klines_1h[-1], klines_1h[-2]
    close, open_ = float(latest["close"]), float(latest["open"])
    high, low = float(latest["high"]), float(latest["low"])
    atr = float(latest.get("atr", max(close * 0.004, 1.0)))
    broke_up = close > liquidity_ctx["prev_high"]
    broke_down = close < liquidity_ctx["prev_low"]
    direction = "bull" if broke_up else "bear" if broke_down else "neutral"
    atr_move = abs(close - float(prev["close"])) / max(atr, 1e-9)
    structure_range = max(abs(liquidity_ctx["prev_high"] - liquidity_ctx["prev_low"]), atr)
    range_ratio = abs(close - float(prev["close"])) / structure_range
    body_quality = abs(close - open_) / max(high - low, 1e-9)
    position_score = 0.3 if direction == "neutral" else ((close - liquidity_ctx["prev_low"]) if direction == "bull" else (liquidity_ctx["prev_high"] - close)) / max(structure_range, 1e-9)
    position_score = max(0.0, min(1.4, position_score))
    leg_type = classify_msb_leg(atr_move, range_ratio, body_quality, position_score)
    zone_low = min(float(prev["open"]), float(prev["close"]), low)
    zone_high = max(float(prev["open"]), float(prev["close"]), high)
    mid = zone_low + (zone_high - zone_low) * zcfg["continuation_mid_ratio"]
    pad = atr * zcfg["merge_width_atr_mult"]
    return {"direction": direction, "leg_type": leg_type, "quality": min(100, int((atr_move * 0.35 + range_ratio * 0.30 + body_quality * 0.2 + min(position_score, 1.0) * 0.15) * 100)), "structure_zone": (round(zone_low, 2), round(zone_high, 2)), "order_block_zone": (round(min(float(prev["low"]), zone_low), 2), round(max(float(prev["high"]), zone_high), 2)), "mid_observe_zone": (round(mid - pad, 2), round(mid + pad, 2)), "metrics": {"atr_move": atr_move, "range_ratio": range_ratio, "body_quality": body_quality, "position_score": position_score}}
