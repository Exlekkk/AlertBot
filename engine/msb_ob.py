from __future__ import annotations

from typing import Any

from engine.trend_config import TREND_ENGINE_CONFIG


def classify_msb_leg(atr_move: float, range_ratio: float, body_quality: float, position_score: float) -> str:
    c = TREND_ENGINE_CONFIG["msb"]
    weak_count = sum(
        [
            atr_move < c["atr_short_max"],
            range_ratio < c["range_short_max"],
            body_quality < c["body_short_max"],
            position_score < c["position_short_max"],
        ]
    )
    if weak_count >= c["short_weak_count_min"]:
        return "SHORT"
    if atr_move >= c["atr_extended_min"] or range_ratio >= c["range_extended_min"]:
        return "EXTENDED"
    if (
        atr_move >= c["atr_long_min"]
        and range_ratio >= c["range_long_min"]
        and body_quality >= c["body_long_min"]
        and position_score >= c["position_long_min"]
    ):
        return "LONG"
    return "MID"



def _latest_active_fvg(klines_1h: list[dict[str, Any]], lookback: int = 12) -> dict[str, Any]:
    """Return the most recent simple 3-candle FVG proxy.

    This is intentionally conservative and only used as an internal key-zone
    source.  It does not try to expose or fully replicate a TradingView script.
    """

    if len(klines_1h) < 3:
        return {"zone": None, "direction": "none"}

    start = max(2, len(klines_1h) - lookback)
    latest_close = float(klines_1h[-1]["close"])
    latest: dict[str, Any] = {"zone": None, "direction": "none", "age": None}

    for i in range(start, len(klines_1h)):
        left = klines_1h[i - 2]
        right = klines_1h[i]
        left_high = float(left["high"])
        left_low = float(left["low"])
        right_high = float(right["high"])
        right_low = float(right["low"])

        if right_low > left_high:
            zone = (round(left_high, 2), round(right_low, 2))
            # Keep if price has not closed far below the zone.
            if latest_close >= zone[0]:
                latest = {"zone": zone, "direction": "bull", "age": len(klines_1h) - 1 - i}
        elif right_high < left_low:
            zone = (round(right_high, 2), round(left_low, 2))
            # Keep if price has not closed far above the zone.
            if latest_close <= zone[1]:
                latest = {"zone": zone, "direction": "bear", "age": len(klines_1h) - 1 - i}

    return latest


def _build_legacy_msb_ob_context(klines_1h: list[dict[str, Any]], liquidity_ctx: dict[str, Any]) -> dict[str, Any]:
    zcfg = TREND_ENGINE_CONFIG["zone"]
    latest, prev = klines_1h[-1], klines_1h[-2]

    close = float(latest["close"])
    open_ = float(latest["open"])
    high = float(latest["high"])
    low = float(latest["low"])
    atr = float(latest.get("atr", max(close * 0.004, 1.0)))

    broke_up = close > liquidity_ctx["prev_high"]
    broke_down = close < liquidity_ctx["prev_low"]
    direction = "bull" if broke_up else "bear" if broke_down else "neutral"

    atr_move = abs(close - float(prev["close"])) / max(atr, 1e-9)
    structure_range = max(abs(liquidity_ctx["prev_high"] - liquidity_ctx["prev_low"]), atr)
    range_ratio = abs(close - float(prev["close"])) / structure_range
    body_quality = abs(close - open_) / max(high - low, 1e-9)

    if direction == "neutral":
        position_score = 0.3
    elif direction == "bull":
        position_score = (close - liquidity_ctx["prev_low"]) / max(structure_range, 1e-9)
    else:
        position_score = (liquidity_ctx["prev_high"] - close) / max(structure_range, 1e-9)

    position_score = max(0.0, min(1.4, position_score))
    leg_type = classify_msb_leg(atr_move, range_ratio, body_quality, position_score)

    zone_low = min(float(prev["open"]), float(prev["close"]), low)
    zone_high = max(float(prev["open"]), float(prev["close"]), high)
    mid = zone_low + (zone_high - zone_low) * zcfg["continuation_mid_ratio"]
    pad = atr * zcfg["merge_width_atr_mult"]

    fvg = _latest_active_fvg(klines_1h)

    return {
        "direction": direction,
        "leg_type": leg_type,
        "has_order_block_context": direction != "neutral" and leg_type != "SHORT",
        "quality": min(
            100,
            int((atr_move * 0.35 + range_ratio * 0.30 + body_quality * 0.2 + min(position_score, 1.0) * 0.15) * 100),
        ),
        "structure_zone": (round(zone_low, 2), round(zone_high, 2)),
        "order_block_zone": (
            round(min(float(prev["low"]), zone_low), 2),
            round(max(float(prev["high"]), zone_high), 2),
        ),
        "mid_observe_zone": (round(mid - pad, 2), round(mid + pad, 2)),
        "active_fvg_zone": fvg["zone"],
        "active_fvg_direction": fvg["direction"],
        "active_fvg_age": fvg["age"],
        "metrics": {
            "atr_move": atr_move,
            "range_ratio": range_ratio,
            "body_quality": body_quality,
            "position_score": position_score,
        },
    }


def _last_candle(
    klines: list[dict[str, Any]],
    start: int,
    end: int,
    bullish: bool,
) -> int | None:
    low = max(0, min(int(start), int(end)))
    high = min(len(klines) - 1, max(int(start), int(end)))
    matches = [
        index
        for index in range(low, high + 1)
        if (float(klines[index]["close"]) > float(klines[index]["open"])) == bullish
        and float(klines[index]["close"]) != float(klines[index]["open"])
    ]
    return matches[-1] if matches else None


def _zone_from_candle(klines: list[dict[str, Any]], index: int | None) -> tuple[float, float] | None:
    if index is None:
        return None
    bar = klines[index]
    return (round(float(bar["low"]), 2), round(float(bar["high"]), 2))


def _pine_msb_state(klines: list[dict[str, Any]]) -> dict[str, Any]:
    """Translate the supplied MSB-OB Pine state machine to closed candles."""

    cfg = TREND_ENGINE_CONFIG["chart_framework"]["msb_ob"]
    zigzag_length = int(cfg["zigzag_length"])
    fib_factor = float(cfg["fib_factor"])
    trend = 1
    market = 1
    segment_high = float(klines[0]["high"])
    segment_high_index = 0
    segment_low = float(klines[0]["low"])
    segment_low_index = 0
    high_points: list[tuple[float, int]] = []
    low_points: list[tuple[float, int]] = []
    zones: list[dict[str, Any]] = []
    structure_events: list[dict[str, Any]] = []
    last_market_signature: tuple[float, float, float, float] | None = None

    for index, bar in enumerate(klines):
        high = float(bar["high"])
        low = float(bar["low"])
        if trend == 1 and high >= segment_high:
            segment_high, segment_high_index = high, index
        if trend == -1 and low <= segment_low:
            segment_low, segment_low_index = low, index

        if index + 1 < zigzag_length:
            continue
        window = klines[index - zigzag_length + 1 : index + 1]
        to_up = high >= max(float(item["high"]) for item in window)
        to_down = low <= min(float(item["low"]) for item in window)
        previous_trend = trend
        if trend == 1 and to_down:
            trend = -1
        elif trend == -1 and to_up:
            trend = 1

        if trend != previous_trend:
            if trend == -1:
                high_points.append((segment_high, segment_high_index))
                high_points = high_points[-8:]
                segment_low, segment_low_index = low, index
            else:
                low_points.append((segment_low, segment_low_index))
                low_points = low_points[-8:]
                segment_high, segment_high_index = high, index

        if len(high_points) >= 2 and len(low_points) >= 2:
            h0, h1 = high_points[-1], high_points[-2]
            l0, l1 = low_points[-1], low_points[-2]
            signature = (h0[0], h1[0], l0[0], l1[0])
            previous_market = market
            if signature != last_market_signature:
                if market == 1 and l0[0] < l1[0] - abs(h0[0] - l1[0]) * fib_factor:
                    market = -1
                elif market == -1 and h0[0] > h1[0] + abs(h1[0] - l0[0]) * fib_factor:
                    market = 1
                last_market_signature = signature

            if market != previous_market:
                if market == 1:
                    ob_index = _last_candle(klines, h1[1], l0[1], bullish=False)
                    bb_index = _last_candle(klines, l1[1] - zigzag_length, h1[1], bullish=True)
                    for kind, candle_index in (
                        ("bu_ob", ob_index),
                        ("bu_bb" if l0[0] < l1[0] else "bu_mb", bb_index),
                    ):
                        zone = _zone_from_candle(klines, candle_index)
                        if zone:
                            zones.insert(0, {"kind": kind, "side": "bull", "zone": zone, "origin_index": candle_index, "created_index": index})
                    structure_events.append({"event": "bullish_msb", "direction": "bull", "index": index, "level": h1[0]})
                else:
                    ob_index = _last_candle(klines, l1[1], h0[1], bullish=True)
                    bb_index = _last_candle(klines, h1[1] - zigzag_length, l1[1], bullish=False)
                    for kind, candle_index in (
                        ("be_ob", ob_index),
                        ("be_bb" if h0[0] > h1[0] else "be_mb", bb_index),
                    ):
                        zone = _zone_from_candle(klines, candle_index)
                        if zone:
                            zones.insert(0, {"kind": kind, "side": "bear", "zone": zone, "origin_index": candle_index, "created_index": index})
                    structure_events.append({"event": "bearish_msb", "direction": "bear", "index": index, "level": l1[0]})
                zones = zones[:10]

        close = float(bar["close"])
        survivors: list[dict[str, Any]] = []
        for zone_item in zones:
            bottom, top = zone_item["zone"]
            invalid = close < bottom if zone_item["side"] == "bull" else close > top
            if not invalid:
                zone_item["in_zone"] = bottom < close < top
                survivors.append(zone_item)
        zones = survivors

    latest_event = structure_events[-1] if structure_events else {}
    return {
        "market": market,
        "trend": trend,
        "direction": "bull" if market == 1 else "bear",
        "structure_event": latest_event.get("event", "none"),
        "structure_event_age": len(klines) - 1 - int(latest_event["index"]) if latest_event else None,
        "structure_level": latest_event.get("level"),
        "zones": zones,
        "high_points": high_points,
        "low_points": low_points,
    }


def build_msb_ob_context(klines_1h: list[dict[str, Any]], liquidity_ctx: dict[str, Any]) -> dict[str, Any]:
    """Build MSB/OB/BB/MB context from the supplied Pine algorithm.

    The legacy one-candle breakout classifier is retained only as a sparse-data
    fallback.  With normal scanner history, structure direction and zones come
    from the 9 / 0.33 MSB-OB state machine shown on the user's chart.
    """

    if len(klines_1h) < 40:
        fallback = _build_legacy_msb_ob_context(klines_1h, liquidity_ctx)
        fallback["source"] = "legacy_sparse_history_fallback"
        return fallback

    state = _pine_msb_state(klines_1h)
    latest = klines_1h[-1]
    previous = klines_1h[-2]
    close = float(latest["close"])
    open_ = float(latest["open"])
    high = float(latest["high"])
    low = float(latest["low"])
    atr = max(float(latest.get("atr", close * 0.004) or close * 0.004), 1e-9)
    recent = klines_1h[-25:]
    recent_high = max(float(bar["high"]) for bar in recent[:-1])
    recent_low = min(float(bar["low"]) for bar in recent[:-1])
    structure_range = max(recent_high - recent_low, atr)
    atr_move = abs(close - float(previous["close"])) / atr
    range_ratio = abs(close - float(previous["close"])) / structure_range
    body_quality = abs(close - open_) / max(high - low, 1e-9)
    position_score = (close - recent_low) / structure_range if state["direction"] == "bull" else (recent_high - close) / structure_range
    position_score = max(0.0, min(1.4, position_score))
    leg_type = classify_msb_leg(atr_move, range_ratio, body_quality, position_score)

    side_zones = [item for item in state["zones"] if item["side"] == state["direction"]]
    ob_zones = [item for item in side_zones if item["kind"].endswith("_ob")]
    bb_zones = [item for item in side_zones if item["kind"].endswith("_bb") or item["kind"].endswith("_mb")]
    nearest = min(side_zones, key=lambda item: 0.0 if item["zone"][0] <= close <= item["zone"][1] else min(abs(close - item["zone"][0]), abs(close - item["zone"][1]))) if side_zones else None
    order_block = ob_zones[0]["zone"] if ob_zones else nearest["zone"] if nearest else None
    continuation = bb_zones[0]["zone"] if bb_zones else order_block
    if nearest:
        structure_zone = nearest["zone"]
    else:
        pad = atr * 0.35
        structure_zone = (close - pad, close + pad)
    if order_block is None:
        order_block = structure_zone
    if continuation is None:
        continuation = order_block

    fvg = _latest_active_fvg(klines_1h, lookback=30)
    quality = min(100, int((min(atr_move, 2.0) * 0.25 + min(range_ratio, 1.0) * 0.2 + body_quality * 0.2 + min(position_score, 1.0) * 0.2 + (0.15 if state["structure_event_age"] is not None and state["structure_event_age"] <= 6 else 0.0)) * 100))
    return {
        "source": "msb_ob_pine_reimplementation",
        "direction": state["direction"],
        "leg_type": leg_type,
        "has_order_block_context": bool(side_zones),
        "quality": quality,
        "structure_event": state["structure_event"],
        "structure_event_age": state["structure_event_age"],
        "structure_level": state["structure_level"],
        "structure_zone": tuple(round(value, 2) for value in structure_zone),
        "order_block_zone": tuple(round(value, 2) for value in order_block),
        "mid_observe_zone": tuple(round(value, 2) for value in continuation),
        "active_zones": state["zones"],
        "active_fvg_zone": fvg["zone"],
        "active_fvg_direction": fvg["direction"],
        "active_fvg_age": fvg["age"],
        "metrics": {
            "atr_move": atr_move,
            "range_ratio": range_ratio,
            "body_quality": body_quality,
            "position_score": position_score,
        },
    }
