from __future__ import annotations

import math
from typing import Any

from engine.chart_indicators import _pivot_indices, atr_series
from engine.trend_config import TREND_ENGINE_CONFIG


def _f(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        number = float(value)
        if math.isnan(number) or math.isinf(number):
            return default
        return number
    except (TypeError, ValueError):
        return default


def _ordered_zone(low: Any, high: Any) -> tuple[float, float] | None:
    low_f = _f(low, float("nan"))
    high_f = _f(high, float("nan"))
    if math.isnan(low_f) or math.isnan(high_f):
        return None
    zone = (min(low_f, high_f), max(low_f, high_f))
    if zone[1] <= zone[0]:
        return None
    return zone


def _zone_from_item(item: Any) -> tuple[float, float] | None:
    if isinstance(item, dict):
        for low_key, high_key in (
            ("low", "high"),
            ("bottom", "top"),
            ("zone_low", "zone_high"),
            ("ob_low", "ob_high"),
        ):
            if low_key in item and high_key in item:
                return _ordered_zone(item.get(low_key), item.get(high_key))
    if isinstance(item, (list, tuple)) and len(item) >= 2:
        return _ordered_zone(item[0], item[1])
    return None


def _explicit_zones(latest: dict[str, Any], side: str) -> list[tuple[float, float]]:
    """Read optional exact ICT fields supplied by an external data adapter.

    Binance candles do not contain LuxAlgo objects.  These aliases make that
    limitation explicit and give a TradingView/webhook adapter a stable way to
    provide the actual active +OB/-OB zones without mixing them with MSB-OB.
    """

    if side == "bull":
        list_keys = (
            "ict_bullish_ob_zones",
            "ict_plus_ob_zones",
            "ict_bull_ob_zones",
        )
        pair_keys = (
            ("ict_bullish_ob_low", "ict_bullish_ob_high"),
            ("ict_plus_ob_low", "ict_plus_ob_high"),
            ("ict_bull_ob_low", "ict_bull_ob_high"),
        )
    else:
        list_keys = (
            "ict_bearish_ob_zones",
            "ict_minus_ob_zones",
            "ict_bear_ob_zones",
        )
        pair_keys = (
            ("ict_bearish_ob_low", "ict_bearish_ob_high"),
            ("ict_minus_ob_low", "ict_minus_ob_high"),
            ("ict_bear_ob_low", "ict_bear_ob_high"),
        )

    zones: list[tuple[float, float]] = []
    for key in list_keys:
        value = latest.get(key)
        if not isinstance(value, (list, tuple)):
            continue
        # A single two-number tuple is also accepted.
        if len(value) >= 2 and all(isinstance(v, (int, float)) for v in value[:2]):
            zone = _zone_from_item(value)
            if zone:
                zones.append(zone)
            continue
        for item in value:
            zone = _zone_from_item(item)
            if zone:
                zones.append(zone)

    for low_key, high_key in pair_keys:
        if low_key in latest and high_key in latest:
            zone = _ordered_zone(latest.get(low_key), latest.get(high_key))
            if zone:
                zones.append(zone)

    return _dedupe_zones(zones)


def _dedupe_zones(zones: list[tuple[float, float]]) -> list[tuple[float, float]]:
    deduped: list[tuple[float, float]] = []
    for zone in zones:
        if not any(abs(zone[0] - z[0]) < 1e-9 and abs(zone[1] - z[1]) < 1e-9 for z in deduped):
            deduped.append(zone)
    return deduped


def _zone_distance(close: float, zone: tuple[float, float]) -> float:
    if zone[0] <= close <= zone[1]:
        return 0.0
    return min(abs(close - zone[0]), abs(close - zone[1]))


def _nearest_zone(close: float, zones: list[tuple[float, float]]) -> tuple[float, float] | None:
    if not zones:
        return None
    return min(zones, key=lambda zone: _zone_distance(close, zone))


def _zigzag_points(klines: list[dict[str, Any]], length: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """LuxAlgo-style short-right-hand zigzag plus structure events.

    ICT Concepts uses ``ta.pivothigh(left, 1)`` / ``ta.pivotlow(left, 1)`` and
    keeps alternating extremes.  This closed-bar translation preserves that
    confirmation delay and never reads future candles beyond the one right bar.
    """

    highs = [_f(bar.get("high")) for bar in klines]
    lows = [_f(bar.get("low")) for bar in klines]
    event_map: dict[int, list[tuple[int, int, float]]] = {}
    for confirm, pivot, value in _pivot_indices(highs, length, 1, True):
        event_map.setdefault(confirm, []).append((1, pivot, value))
    for confirm, pivot, value in _pivot_indices(lows, length, 1, False):
        event_map.setdefault(confirm, []).append((-1, pivot, value))

    points: list[dict[str, Any]] = []
    structure_events: list[dict[str, Any]] = []
    structure_direction = 0
    crossed_highs: set[int] = set()
    crossed_lows: set[int] = set()

    for index, bar in enumerate(klines):
        for direction, pivot, value in sorted(event_map.get(index, []), reverse=True):
            point = {"direction": direction, "index": pivot, "value": value, "confirmed_index": index}
            if points and points[-1]["direction"] == direction:
                more_extreme = value > points[-1]["value"] if direction == 1 else value < points[-1]["value"]
                if more_extreme:
                    points[-1] = point
            else:
                points.append(point)

        newest_first = list(reversed(points))

        def structure_point(direction: int) -> dict[str, Any] | None:
            # LuxAlgo uses:
            #   iH = aZZ.d.get(2) ==  1 ? 2 : 1
            #   iL = aZZ.d.get(2) == -1 ? 2 : 1
            # With an alternating ZigZag this means: when the latest point is
            # on the requested side, test the prior same-side point; when the
            # latest point is opposite, test the most recent requested-side
            # point.  A fixed "second same-side point" incorrectly lags one
            # swing whenever the latest confirmed pivot is opposite.
            if len(newest_first) >= 3:
                candidate_index = 2 if newest_first[2]["direction"] == direction else 1
                candidate = newest_first[candidate_index]
                if candidate["direction"] == direction:
                    return candidate
            return next((point for point in newest_first if point["direction"] == direction), None)

        high_point = structure_point(1)
        low_point = structure_point(-1)
        close = _f(bar.get("close"))

        if high_point and close > high_point["value"] and high_point["index"] not in crossed_highs:
            event = "bullish_mss" if structure_direction < 1 else "bullish_bos"
            structure_direction = 1
            crossed_highs.add(int(high_point["index"]))
            structure_events.append(
                {"event": event, "direction": "bull", "level": high_point["value"], "index": index, "pivot_index": high_point["index"]}
            )
        elif low_point and close < low_point["value"] and low_point["index"] not in crossed_lows:
            event = "bearish_mss" if structure_direction > -1 else "bearish_bos"
            structure_direction = -1
            crossed_lows.add(int(low_point["index"]))
            structure_events.append(
                {"event": event, "direction": "bear", "level": low_point["value"], "index": index, "pivot_index": low_point["index"]}
            )

    if structure_events:
        structure_events[-1]["age_bars"] = len(klines) - 1 - int(structure_events[-1]["index"])
    return points, structure_events


def _ict_order_blocks(klines: list[dict[str, Any]], length: int, use_body: bool) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    highs = [_f(bar.get("high")) for bar in klines]
    lows = [_f(bar.get("low")) for bar in klines]
    bullish: list[dict[str, Any]] = []
    bearish: list[dict[str, Any]] = []
    oscillator_state = 0
    swing_high: dict[str, Any] | None = None
    swing_low: dict[str, Any] | None = None

    def candle_bounds(bar: dict[str, Any]) -> tuple[float, float]:
        if use_body:
            return (min(_f(bar.get("open")), _f(bar.get("close"))), max(_f(bar.get("open")), _f(bar.get("close"))))
        return (min(_f(bar.get("low")), _f(bar.get("high"))), max(_f(bar.get("low")), _f(bar.get("high"))))

    for index, bar in enumerate(klines):
        if index >= length:
            candidate = index - length
            subsequent_high = max(highs[candidate + 1 : index + 1])
            subsequent_low = min(lows[candidate + 1 : index + 1])
            previous_state = oscillator_state
            if highs[candidate] > subsequent_high:
                oscillator_state = 0
            elif lows[candidate] < subsequent_low:
                oscillator_state = 1
            if oscillator_state == 0 and previous_state != 0:
                swing_high = {"index": candidate, "value": highs[candidate], "crossed": False}
            if oscillator_state == 1 and previous_state != 1:
                swing_low = {"index": candidate, "value": lows[candidate], "crossed": False}

        close = _f(bar.get("close"))
        open_ = _f(bar.get("open"))

        if swing_high and not swing_high["crossed"] and close > swing_high["value"]:
            swing_high["crossed"] = True
            candidates = list(range(int(swing_high["index"]) + 1, index))
            if candidates:
                location = min(candidates, key=lambda item: candle_bounds(klines[item])[0])
                bottom, top = candle_bounds(klines[location])
                bullish.insert(
                    0,
                    {
                        "zone": (bottom, top),
                        "origin_index": location,
                        "created_index": index,
                        "breaker": False,
                        "breaker_index": None,
                        "mitigated": False,
                    },
                )

        if swing_low and not swing_low["crossed"] and close < swing_low["value"]:
            swing_low["crossed"] = True
            candidates = list(range(int(swing_low["index"]) + 1, index))
            if candidates:
                location = max(candidates, key=lambda item: candle_bounds(klines[item])[1])
                bottom, top = candle_bounds(klines[location])
                bearish.insert(
                    0,
                    {
                        "zone": (bottom, top),
                        "origin_index": location,
                        "created_index": index,
                        "breaker": False,
                        "breaker_index": None,
                        "mitigated": False,
                    },
                )

        survivors: list[dict[str, Any]] = []
        for item in bullish:
            bottom, top = item["zone"]
            if index > item["created_index"] and _f(bar.get("low")) <= top and _f(bar.get("high")) >= bottom:
                item["mitigated"] = True
            if not item["breaker"] and min(close, open_) < bottom:
                item["breaker"] = True
                item["breaker_index"] = index
            elif item["breaker"] and index > int(item["breaker_index"] or index) and close > top:
                continue
            survivors.append(item)
        bullish = survivors

        survivors = []
        for item in bearish:
            bottom, top = item["zone"]
            if index > item["created_index"] and _f(bar.get("low")) <= top and _f(bar.get("high")) >= bottom:
                item["mitigated"] = True
            if not item["breaker"] and max(close, open_) > top:
                item["breaker"] = True
                item["breaker_index"] = index
            elif item["breaker"] and index > int(item["breaker_index"] or index) and close < bottom:
                continue
            survivors.append(item)
        bearish = survivors

    for item in bullish + bearish:
        item["zone"] = tuple(round(value, 2) for value in item["zone"])
        item["age_bars"] = len(klines) - 1 - int(item["origin_index"])
    return bullish, bearish


def _ict_fvgs(klines: list[dict[str, Any]], structure_length: int, visible: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    bodies = [abs(_f(bar.get("close")) - _f(bar.get("open"))) for bar in klines]
    bullish: list[dict[str, Any]] = []
    bearish: list[dict[str, Any]] = []
    previous_event = "none"

    for index in range(2, len(klines)):
        middle = klines[index - 1]
        body = bodies[index - 1]
        mean_body = sum(bodies[max(0, index - structure_length) : index]) / min(index, structure_length)
        upper_wick = _f(middle.get("high")) - max(_f(middle.get("open")), _f(middle.get("close")))
        lower_wick = min(_f(middle.get("open")), _f(middle.get("close"))) - _f(middle.get("low"))
        large_body = upper_wick < body * 0.36 and lower_wick < body * 0.36 and body > mean_body
        bull_event = large_body and _f(middle.get("close")) > _f(middle.get("open")) and _f(klines[index].get("low")) > _f(klines[index - 2].get("high"))
        bear_event = large_body and _f(middle.get("close")) < _f(middle.get("open")) and _f(klines[index].get("high")) < _f(klines[index - 2].get("low"))

        if bull_event:
            item = {
                "zone": (_f(klines[index - 2].get("high")), _f(klines[index].get("low"))),
                "created_index": index,
                "mitigated": False,
            }
            if previous_event == "bull" and bullish and bullish[0]["created_index"] == index - 1:
                bullish[0] = item
            else:
                bullish.insert(0, item)
            bullish = bullish[: max(1, visible)]
            previous_event = "bull"
        elif bear_event:
            item = {
                "zone": (_f(klines[index].get("high")), _f(klines[index - 2].get("low"))),
                "created_index": index,
                "mitigated": False,
            }
            if previous_event == "bear" and bearish and bearish[0]["created_index"] == index - 1:
                bearish[0] = item
            else:
                bearish.insert(0, item)
            bearish = bearish[: max(1, visible)]
            previous_event = "bear"
        else:
            previous_event = "none"

        bull_survivors: list[dict[str, Any]] = []
        for item in bullish:
            bottom, top = item["zone"]
            if index > item["created_index"]:
                item["mitigated"] = bool(item["mitigated"] or _f(klines[index].get("low")) < top)
                if _f(klines[index].get("low")) < bottom:
                    continue
            bull_survivors.append(item)
        bullish = bull_survivors

        bear_survivors: list[dict[str, Any]] = []
        for item in bearish:
            bottom, top = item["zone"]
            if index > item["created_index"]:
                item["mitigated"] = bool(item["mitigated"] or _f(klines[index].get("high")) > bottom)
                if _f(klines[index].get("high")) > top:
                    continue
            bear_survivors.append(item)
        bearish = bear_survivors

    for item in bullish + bearish:
        item["zone"] = tuple(round(value, 2) for value in (min(item["zone"]), max(item["zone"])))
        item["age_bars"] = len(klines) - 1 - int(item["created_index"])
    return bullish, bearish


def _ict_liquidity(
    klines: list[dict[str, Any]],
    points: list[dict[str, Any]],
    margin: float,
    visible: int,
) -> dict[str, Any]:
    atr_values = atr_series(klines, 10)
    zones: dict[str, list[dict[str, Any]]] = {"buyside": [], "sellside": []}
    for direction, name in ((1, "buyside"), (-1, "sellside")):
        same_side = [point for point in points if point["direction"] == direction]
        for position, point in enumerate(same_side):
            tolerance = atr_values[min(int(point["confirmed_index"]), len(atr_values) - 1)] * float(margin) / 10.0
            nearby = [other for other in same_side[max(0, position - 49) : position + 1] if abs(other["value"] - point["value"]) < tolerance]
            if len(nearby) < 3:
                continue
            levels = [item["value"] for item in nearby]
            center = (min(levels) + max(levels)) / 2.0
            zone = (center - tolerance, center + tolerance)
            left = min(int(item["index"]) for item in nearby)
            if zones[name] and zones[name][0]["left_index"] == left:
                zones[name][0]["zone"] = zone
            else:
                zones[name].insert(0, {"zone": zone, "left_index": left, "broken": False})
            zones[name] = zones[name][: max(1, visible)]

    latest_event = "none"
    event_level = None
    for name, items in zones.items():
        for item in items:
            bottom, top = item["zone"]
            for index in range(max(int(item["left_index"]) + 1, 1), len(klines)):
                bar = klines[index]
                if name == "buyside":
                    if _f(bar.get("high")) > top and _f(bar.get("close")) < top:
                        latest_event = "buyside_sweep_reject"
                        event_level = top
                    if _f(bar.get("close")) > top:
                        item["broken"] = True
                else:
                    if _f(bar.get("low")) < bottom and _f(bar.get("close")) > bottom:
                        latest_event = "sellside_sweep_reclaim"
                        event_level = bottom
                    if _f(bar.get("close")) < bottom:
                        item["broken"] = True
            item["zone"] = tuple(round(value, 2) for value in item["zone"])

    return {"buyside": zones["buyside"], "sellside": zones["sellside"], "event": latest_event, "event_level": event_level}


def _pine_ict_context(klines: list[dict[str, Any]]) -> dict[str, Any]:
    cfg = TREND_ENGINE_CONFIG["chart_framework"]["ict"]
    points, structure_events = _zigzag_points(klines, int(cfg["structure_length"]))
    bullish, bearish = _ict_order_blocks(klines, int(cfg["ob_swing_lookback"]), bool(cfg["use_candle_body"]))
    bullish = bullish[: max(0, int(cfg["visible_bullish_ob"]))]
    bearish = bearish[: max(0, int(cfg["visible_bearish_ob"]))]
    bull_fvg, bear_fvg = _ict_fvgs(klines, int(cfg["structure_length"]), int(cfg["visible_fvg"]))
    liquidity = _ict_liquidity(
        klines,
        points,
        float(cfg["liquidity_margin"]),
        int(cfg["visible_liquidity_boxes"]),
    )
    close = _f(klines[-1].get("close"))
    last_high = next((point for point in reversed(points) if point["direction"] == 1), None)
    last_low = next((point for point in reversed(points) if point["direction"] == -1), None)
    equilibrium = None
    premium_discount = "unknown"
    if last_high and last_low and last_high["value"] > last_low["value"]:
        equilibrium = (last_high["value"] + last_low["value"]) / 2.0
        premium_discount = "premium" if close > equilibrium else "discount" if close < equilibrium else "equilibrium"

    pd_arrays: list[dict[str, Any]] = []
    for side, items, kind in (
        ("bull", bullish, "order_block"),
        ("bear", bearish, "order_block"),
        ("bull", bull_fvg, "fvg"),
        ("bear", bear_fvg, "fvg"),
    ):
        for item in items:
            pd_arrays.append({"side": side, "kind": kind, "zone": item["zone"], "breaker": bool(item.get("breaker", False)), "mitigated": bool(item.get("mitigated", False))})

    latest_structure = structure_events[-1] if structure_events else {}
    return {
        "points": points,
        "structure_direction": latest_structure.get("direction", "neutral"),
        "structure_event": latest_structure.get("event", "none"),
        "structure_event_age": latest_structure.get("age_bars"),
        "structure_level": latest_structure.get("level"),
        "bullish_ob": bullish,
        "bearish_ob": bearish,
        "bullish_fvg": bull_fvg,
        "bearish_fvg": bear_fvg,
        "liquidity": liquidity,
        "equilibrium": round(equilibrium, 2) if equilibrium is not None else None,
        "premium_discount": premium_discount,
        "pd_arrays": pd_arrays,
    }


def build_ict_ob_context(klines_1h: list[dict[str, Any]]) -> dict[str, Any]:
    """Build a dedicated ICT +OB/-OB context, separate from MSB-OB.

    External fields still take precedence when present.  Otherwise the supplied
    LuxAlgo Pine source is deterministically translated to closed Binance
    candles and labelled as a reimplementation rather than an external feed.
    """

    if not klines_1h:
        return {
            "available": False,
            "source": "none",
            "is_exact": False,
            "bullish_active": False,
            "bearish_active": False,
            "coexist": False,
            "bullish_zones": [],
            "bearish_zones": [],
            "bullish_nearest": None,
            "bearish_nearest": None,
        }

    latest = klines_1h[-1]
    close = _f(latest.get("close"))
    atr = max(_f(latest.get("atr"), max(abs(close) * 0.004, 1.0)), 1e-9)

    pine = _pine_ict_context(klines_1h)

    bullish = _explicit_zones(latest, "bull")
    bearish = _explicit_zones(latest, "bear")
    exact = bool(bullish or bearish)
    bullish_origin_breakers = [item for item in pine["bullish_ob"] if item.get("breaker")]
    bearish_origin_breakers = [item for item in pine["bearish_ob"] if item.get("breaker")]
    if not exact:
        # Polarity matters: a broken bullish OB is bearish resistance, while a
        # broken bearish OB is bullish support.  Treating origin labels as live
        # polarity caused the old engine to select distant/wrong-side +OBs.
        bullish = [tuple(item["zone"]) for item in pine["bullish_ob"] if not item.get("breaker")]
        bullish += [tuple(item["zone"]) for item in bearish_origin_breakers]
        bearish = [tuple(item["zone"]) for item in pine["bearish_ob"] if not item.get("breaker")]
        bearish += [tuple(item["zone"]) for item in bullish_origin_breakers]

    max_active_distance = float(TREND_ENGINE_CONFIG["ict_ob"].get("max_active_distance_atr", 5.0)) * atr
    bullish = _dedupe_zones([zone for zone in bullish if _zone_distance(close, zone) <= max_active_distance])
    bearish = _dedupe_zones([zone for zone in bearish if _zone_distance(close, zone) <= max_active_distance])

    bull_nearest = _nearest_zone(close, bullish)
    bear_nearest = _nearest_zone(close, bearish)
    max_conflict_width = max(
        atr * float(TREND_ENGINE_CONFIG["ict_ob"].get("max_conflict_width_atr", 8.0)),
        abs(close) * float(TREND_ENGINE_CONFIG["ict_ob"].get("max_conflict_width_pct", 0.04)),
    )
    coexist = bool(
        bull_nearest
        and bear_nearest
        and bull_nearest[0] <= bear_nearest[1]
        and (bear_nearest[1] - bull_nearest[0]) <= max_conflict_width
    )

    return {
        "available": bool(bullish or bearish),
        "source": "explicit_feed" if exact else "luxalgo_pine_reimplementation",
        "is_exact": exact,
        "settings_match_chart": True,
        "bullish_active": bool(bullish),
        "bearish_active": bool(bearish),
        "coexist": coexist,
        "bullish_zones": [tuple(round(v, 2) for v in zone) for zone in bullish],
        "bearish_zones": [tuple(round(v, 2) for v in zone) for zone in bearish],
        "bullish_nearest": tuple(round(v, 2) for v in bull_nearest) if bull_nearest else None,
        "bearish_nearest": tuple(round(v, 2) for v in bear_nearest) if bear_nearest else None,
        "bullish_distance_atr": round(_zone_distance(close, bull_nearest) / atr, 3) if bull_nearest else None,
        "bearish_distance_atr": round(_zone_distance(close, bear_nearest) / atr, 3) if bear_nearest else None,
        "bullish_breakers": bullish_origin_breakers,
        "bearish_breakers": bearish_origin_breakers,
        "bullish_fvg": pine["bullish_fvg"],
        "bearish_fvg": pine["bearish_fvg"],
        "liquidity": pine["liquidity"],
        "structure_direction": pine["structure_direction"],
        "structure_event": pine["structure_event"],
        "structure_event_age": pine["structure_event_age"],
        "structure_level": pine["structure_level"],
        "equilibrium": pine["equilibrium"],
        "premium_discount": pine["premium_discount"],
        "pd_arrays": pine["pd_arrays"],
    }
