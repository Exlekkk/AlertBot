from __future__ import annotations

import hashlib
from typing import Any

from engine.trend_config import TREND_ENGINE_CONFIG


LOWER_ALERT_TYPES = {"LOWER_KEY_ZONE_TEST", "FAST_PULLBACK_OBSERVE", "RANGE_LOWER_PROBE"}
UPPER_ALERT_TYPES = {"UPPER_KEY_ZONE_TEST", "FAST_REBOUND_OBSERVE", "RANGE_UPPER_PROBE"}


def _zone_hash(zone: tuple[float, float]) -> str:
    zl, zh = zone
    return hashlib.md5(f"{zl:.2f}-{zh:.2f}".encode()).hexdigest()[:10]


def _ordered_zone(zone: tuple[float, float]) -> tuple[float, float]:
    low, high = float(zone[0]), float(zone[1])
    return (round(min(low, high), 2), round(max(low, high), 2))


def _touches_lower_zone(k: dict[str, Any], prev_close: float, zone: tuple[float, float], pad: float) -> bool:
    zl, zh = zone
    low = float(k["low"])
    close = float(k["close"])
    # A lower test means price was above or near the zone and traded into it.
    return prev_close >= zl and low <= zh + pad and close >= zl - pad


def _touches_upper_zone(k: dict[str, Any], prev_close: float, zone: tuple[float, float], pad: float) -> bool:
    zl, zh = zone
    high = float(k["high"])
    close = float(k["close"])
    # An upper test means price was below or near the zone and traded into it.
    return prev_close <= zh and high >= zl - pad and close <= zh + pad


def _select_zone(
    klines_1h: list[dict[str, Any]],
    liq: dict[str, Any],
    msb: dict[str, Any],
) -> dict[str, Any]:
    cfg = TREND_ENGINE_CONFIG["key_zone"]
    latest = klines_1h[-1]
    prev_close = float(klines_1h[-2]["close"])
    close = float(latest["close"])
    atr = float(latest.get("atr", max(close * 0.004, 1.0)))
    pad = max(atr * cfg["touch_atr_mult"], close * cfg["touch_pct"])

    zones: list[dict[str, Any]] = []

    # Range edges from recent high/low context.
    prev_low = float(liq.get("prev_low", close))
    prev_high = float(liq.get("prev_high", close))
    range_pad = max(atr * cfg["range_edge_atr_mult"], close * cfg["touch_pct"])
    zones.append({"side": "lower", "source": "range_lower_zone", "zone": _ordered_zone((prev_low - range_pad, prev_low + range_pad))})
    zones.append({"side": "upper", "source": "range_upper_zone", "zone": _ordered_zone((prev_high - range_pad, prev_high + range_pad))})

    # Structural zones from the trend engine.  These are not exposed in messages.
    for source in ("structure_zone", "order_block_zone", "mid_observe_zone"):
        raw = msb.get(source)
        if not raw:
            continue
        zone = _ordered_zone(tuple(raw))
        if zone[1] < close:
            zones.append({"side": "lower", "source": source, "zone": zone})
        elif zone[0] > close:
            zones.append({"side": "upper", "source": source, "zone": zone})
        else:
            # If price is inside the zone, infer side from the latest movement.
            side = "lower" if close >= prev_close else "upper"
            zones.append({"side": side, "source": source, "zone": zone})

    lower_hits = [z for z in zones if z["side"] == "lower" and _touches_lower_zone(latest, prev_close, z["zone"], pad)]
    upper_hits = [z for z in zones if z["side"] == "upper" and _touches_upper_zone(latest, prev_close, z["zone"], pad)]

    if lower_hits:
        # Prefer the closest lower zone.
        return min(lower_hits, key=lambda z: abs(close - z["zone"][1]))
    if upper_hits:
        return min(upper_hits, key=lambda z: abs(close - z["zone"][0]))
    return {}


def decide_key_zone_observation(
    symbol: str,
    timeframe: str,
    klines_1h: list[dict[str, Any]],
    htf_ctx: dict[str, Any],
    liq: dict[str, Any],
    msb: dict[str, Any],
    matrix: dict[str, Any],
    aux: dict[str, Any],
    observation_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Detect key-area observation alerts.

    This layer is intentionally less strict than the structure-shift engine:
    it alerts when price quickly tests a useful upper/lower area even if no
    structure shift is confirmed.  It still avoids repeated messages while
    price stays inside the same area, and it re-arms once price leaves and
    later re-enters the area.
    """

    observation_state = observation_state or {}
    cfg = TREND_ENGINE_CONFIG["key_zone"]
    latest = klines_1h[-1]
    prev = klines_1h[-2]
    prev2 = klines_1h[-3] if len(klines_1h) >= 3 else prev

    close = float(latest["close"])
    open_ = float(latest["open"])
    prev_close = float(prev["close"])
    prev2_close = float(prev2["close"])
    atr = float(latest.get("atr", max(close * 0.004, 1.0)))
    atr = max(atr, 1e-9)

    selected = _select_zone(klines_1h, liq, msb)
    if not selected:
        update = {
            "inside_zone": False,
            "active_zone_hash": observation_state.get("active_zone_hash", ""),
            "reentry_count": int(observation_state.get("reentry_count", 0) or 0),
            "last_phase": observation_state.get("last_phase", ""),
            "last_price": close,
        }
        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "alert_type": "NO_TRADE_RANGE",
            "direction": "neutral",
            "price": close,
            "score": 0,
            "score_breakdown": {
                "key_zone": 0,
                "move_quality": 0,
                "htf_context": 0,
                "aux_filters": 0,
                "penalty_reason": "no_key_zone_touch",
            },
            "htf_context": htf_ctx.get("text", "4H 背景中性"),
            "htf_relation": htf_ctx.get("relation", "neutral"),
            "zone": (round(close, 2), round(close, 2)),
            "zone_low": round(close, 2),
            "zone_high": round(close, 2),
            "zone_source": "none",
            "invalid_level": close,
            "should_alert": False,
            "suppress_reason": "no_key_zone_touch",
            "state_version": "NO_TOUCH",
            "momentum_desc": str(aux.get("momentum_desc", "动能 一般")),
            "temperature_desc": str(aux.get("temperature_desc", "热度 中性")),
            "observation_update": update,
        }

    zone = _ordered_zone(selected["zone"])
    zone_hash = _zone_hash(zone)
    side = selected["side"]
    zone_source = selected["source"]

    two_bar_move = (close - prev2_close) / atr
    one_bar_move = (close - prev_close) / atr
    is_red = close < open_
    is_green = close > open_
    prev_red = float(prev["close"]) < float(prev["open"])
    prev_green = float(prev["close"]) > float(prev["open"])

    fast_down = two_bar_move <= -cfg["fast_move_atr"] or (is_red and prev_red and abs(two_bar_move) >= cfg["two_bar_min_atr"])
    fast_up = two_bar_move >= cfg["fast_move_atr"] or (is_green and prev_green and abs(two_bar_move) >= cfg["two_bar_min_atr"])

    if side == "lower":
        direction = "long"
        if fast_down:
            alert_type = "FAST_PULLBACK_OBSERVE"
            phase = "fast_pullback"
        elif zone_source == "range_lower_zone":
            alert_type = "RANGE_LOWER_PROBE"
            phase = "range_lower_probe"
        else:
            alert_type = "LOWER_KEY_ZONE_TEST"
            phase = "lower_test"
        invalid_level = min(float(latest["low"]), zone[0])
    else:
        direction = "short"
        if fast_up:
            alert_type = "FAST_REBOUND_OBSERVE"
            phase = "fast_rebound"
        elif zone_source == "range_upper_zone":
            alert_type = "RANGE_UPPER_PROBE"
            phase = "range_upper_probe"
        else:
            alert_type = "UPPER_KEY_ZONE_TEST"
            phase = "upper_test"
        invalid_level = max(float(latest["high"]), zone[1])

    move_quality = min(40, int(abs(two_bar_move) * 18 + abs(one_bar_move) * 8))
    key_zone_score = 34 if "range" not in zone_source else 28
    aux_score = 4 if ("偏弱" in str(aux.get("momentum_desc", "")) and side == "lower") or ("偏强" in str(aux.get("momentum_desc", "")) and side == "upper") else 0
    score = key_zone_score + move_quality + aux_score

    prev_zone_hash = str(observation_state.get("active_zone_hash", ""))
    was_inside = bool(observation_state.get("inside_zone", False))
    prev_phase = str(observation_state.get("last_phase", ""))
    reentry_count = int(observation_state.get("reentry_count", 0) or 0)

    reentered = zone_hash != prev_zone_hash or not was_inside
    phase_changed = phase != prev_phase and was_inside and zone_hash == prev_zone_hash
    if reentered:
        reentry_count += 1

    suppress_reason = ""
    if score < cfg["min_observation_score"]:
        suppress_reason = "below_observation_score"
    elif was_inside and zone_hash == prev_zone_hash and not phase_changed:
        suppress_reason = "inside_zone_unchanged"

    should_alert = suppress_reason == ""
    state_version = f"{phase.upper()}_R{reentry_count}"

    update = {
        "inside_zone": True,
        "active_zone_hash": zone_hash,
        "reentry_count": reentry_count,
        "last_phase": phase,
        "last_alert_type": alert_type,
        "last_price": close,
        "zone_low": zone[0],
        "zone_high": zone[1],
    }

    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "alert_type": alert_type,
        "direction": direction,
        "price": close,
        "score": score,
        "score_breakdown": {
            "key_zone": key_zone_score,
            "move_quality": move_quality,
            "htf_context": 0,
            "aux_filters": aux_score,
            "penalty_reason": suppress_reason,
        },
        "htf_context": htf_ctx.get("text", "4H 背景中性"),
        "htf_relation": htf_ctx.get("relation", "neutral"),
        "zone_source": zone_source,
        "zone_low": zone[0],
        "zone_high": zone[1],
        "zone": zone,
        "invalid_level": round(invalid_level, 2),
        "should_alert": should_alert,
        "suppress_reason": suppress_reason,
        "state_version": state_version,
        "momentum_desc": str(aux.get("momentum_desc", "动能 一般")),
        "temperature_desc": str(aux.get("temperature_desc", "热度 中性")),
        "observation_update": update,
    }
