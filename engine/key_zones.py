from __future__ import annotations

import hashlib
from typing import Any

from engine.trend_config import TREND_ENGINE_CONFIG


LOWER_ALERT_TYPES = {
    "LOWER_KEY_ZONE_TEST",
    "LOWER_KEY_ZONE_RECLAIM",
    "FAST_PULLBACK_OBSERVE",
    "RANGE_LOWER_PROBE",
}
UPPER_ALERT_TYPES = {
    "UPPER_KEY_ZONE_TEST",
    "UPPER_KEY_ZONE_REJECTION",
    "FAST_REBOUND_OBSERVE",
    "RANGE_UPPER_PROBE",
}


def _zone_hash(zone: tuple[float, float]) -> str:
    zl, zh = zone
    return hashlib.md5(f"{zl:.2f}-{zh:.2f}".encode()).hexdigest()[:10]



def _zone_cluster_hash(zone: tuple[float, float], side: str, source: str, atr: float, close: float) -> str:
    """Stable cluster key for moving zones.

    Exact zone bounds can drift every candle as the proxy zone updates.  Using a
    cluster prevents "same practical area, new hash" from producing an hourly
    alert stream after a waterfall.
    """

    zl, zh = zone
    center = (float(zl) + float(zh)) / 2.0
    bucket = max(float(atr) * 2.0, abs(float(close)) * 0.004, 1.0)
    bucket_id = round(center / bucket)
    family = "range" if "range" in source else "structural"
    return f"{side}|{family}|{bucket_id}"


def _bar_open_time(k: dict[str, Any], fallback: int) -> int:
    for key in ("open_time", "close_time", "timestamp", "time"):
        if key in k and k.get(key) is not None:
            try:
                return int(k.get(key))
            except (TypeError, ValueError):
                pass
    return int(fallback)


def _bars_between(current_open_time: int, previous_open_time: Any) -> int | None:
    if previous_open_time in (None, ""):
        return None
    try:
        previous = int(previous_open_time)
    except (TypeError, ValueError):
        return None
    if previous <= 0:
        return None
    delta = current_open_time - previous
    if delta < 0:
        return None
    # Binance timestamps are ms.  Unit-test fallback counters are small ints.
    if current_open_time > 10_000_000_000:
        return int(delta // 3_600_000)
    return int(delta)


def _ordered_zone(zone: tuple[float, float]) -> tuple[float, float]:
    low, high = float(zone[0]), float(zone[1])
    return (round(min(low, high), 2), round(max(low, high), 2))




def _source_priority(source: str) -> int:
    if source == "fvg_zone":
        return 0
    if source in {"order_block_zone", "structure_zone", "mid_observe_zone"}:
        return 1
    return 2


def _zone_distance(close: float, z: dict[str, Any]) -> float:
    zl, zh = z["zone"]
    return min(abs(close - zl), abs(close - zh))


def _best_zone(candidates: list[dict[str, Any]], close: float, boundary: str) -> dict[str, Any]:
    if boundary == "upper":
        dist = lambda z: abs(close - z["zone"][0])
    elif boundary == "lower":
        dist = lambda z: abs(close - z["zone"][1])
    else:
        dist = lambda z: _zone_distance(close, z)
    return min(candidates, key=lambda z: (_source_priority(str(z.get("source", ""))), dist(z)))

def _touches_lower_zone(k: dict[str, Any], prev_close: float, zone: tuple[float, float], pad: float) -> bool:
    zl, zh = zone
    low = float(k["low"])
    close = float(k["close"])
    # A lower test means price was above or near the zone and traded into it.
    return prev_close >= zl - pad and low <= zh + pad and close >= zl - pad


def _touches_upper_zone(k: dict[str, Any], prev_close: float, zone: tuple[float, float], pad: float) -> bool:
    zl, zh = zone
    high = float(k["high"])
    close = float(k["close"])
    # An upper test means price was below or near the zone and traded into it.
    return prev_close <= zh + pad and high >= zl - pad and close <= zh + pad


def _zone_relation(k: dict[str, Any], zone: tuple[float, float], pad: float) -> str:
    """Describe how the latest candle interacted with a zone.

    This prevents a bearish waterfall candle that briefly touched an upper
    area from being described as a plain "upper key-zone test".  In that case
    we classify it as upper-zone rejection / sell-pressure release instead.
    """

    zl, zh = zone
    high = float(k["high"])
    low = float(k["low"])
    close = float(k["close"])

    touched = high >= zl - pad and low <= zh + pad
    if not touched:
        return "none"
    if close < zl - pad:
        return "rejected_below"
    if close > zh + pad:
        return "reclaimed_above"
    return "inside"


def _select_zone(
    klines_1h: list[dict[str, Any]],
    liq: dict[str, Any],
    msb: dict[str, Any],
) -> dict[str, Any]:
    cfg = TREND_ENGINE_CONFIG["key_zone"]
    latest = klines_1h[-1]
    prev_close = float(klines_1h[-2]["close"])
    close = float(latest["close"])
    open_ = float(latest["open"])
    atr = float(latest.get("atr", max(close * 0.004, 1.0)))
    pad = max(atr * cfg["touch_atr_mult"], close * cfg["touch_pct"])

    zones: list[dict[str, Any]] = []

    has_ob_context = bool(msb.get("has_order_block_context"))
    has_fvg_context = bool(msb.get("active_fvg_zone"))
    has_recent_sweep = bool(liq.get("recent_sweep_valid"))
    # Sweep alone is not enough for observation alerts.  It is useful for the
    # structure-shift engine, but key-zone observation must be anchored to an
    # actual FVG/structure/POI context to avoid hourly noise after a waterfall.
    has_structural_context = has_ob_context or has_fvg_context

    # FVG-style zones are valid observation targets even before a full
    # structure-shift alert.  They are internal-only and never exposed by name.
    fvg_zone = msb.get("active_fvg_zone")
    if fvg_zone:
        zone = _ordered_zone(tuple(fvg_zone))
        direction = str(msb.get("active_fvg_direction", "none"))
        relation = _zone_relation(latest, zone, pad)
        if direction == "bull":
            zones.append({"side": "lower", "source": "fvg_zone", "zone": zone, "interaction": relation})
        elif direction == "bear":
            zones.append({"side": "upper", "source": "fvg_zone", "zone": zone, "interaction": relation})

    # Structural zones from the trend engine.  Do not use synthetic zones when
    # no real structure context exists; otherwise the bot becomes noisy and
    # reports every moving range edge as a key area.
    if has_ob_context or not cfg.get("structural_zone_requires_context", True):
        for source in ("structure_zone", "order_block_zone", "mid_observe_zone"):
            raw = msb.get(source)
            if not raw:
                continue
            zone = _ordered_zone(tuple(raw))
            relation = _zone_relation(latest, zone, pad)
            if relation == "rejected_below":
                zones.append({"side": "upper", "source": source, "zone": zone, "interaction": relation})
            elif relation == "reclaimed_above":
                zones.append({"side": "lower", "source": source, "zone": zone, "interaction": relation})
            elif zone[1] < close:
                zones.append({"side": "lower", "source": source, "zone": zone, "interaction": relation})
            elif zone[0] > close:
                zones.append({"side": "upper", "source": source, "zone": zone, "interaction": relation})
            else:
                # If price is inside the zone, infer side from the latest movement.
                side = "lower" if close >= prev_close else "upper"
                zones.append({"side": side, "source": source, "zone": zone, "interaction": relation})

    # Range edges are allowed only when there is a valid context behind them
    # (recent sweep / FVG / structure).  This preserves useful range-boundary
    # alerts without turning every high/low into a Telegram message.
    if has_structural_context or not cfg.get("range_edge_requires_context", True):
        prev_low = float(liq.get("prev_low", close))
        prev_high = float(liq.get("prev_high", close))
        range_pad = max(atr * cfg["range_edge_atr_mult"], close * cfg["touch_pct"])
        zones.append({"side": "lower", "source": "range_lower_zone", "zone": _ordered_zone((prev_low - range_pad, prev_low + range_pad))})
        zones.append({"side": "upper", "source": "range_upper_zone", "zone": _ordered_zone((prev_high - range_pad, prev_high + range_pad))})

    lower_hits = [
        dict(z, interaction=z.get("interaction") or _zone_relation(latest, z["zone"], pad))
        for z in zones
        if z["side"] == "lower" and _touches_lower_zone(latest, prev_close, z["zone"], pad)
    ]
    upper_hits = [
        dict(z, interaction=z.get("interaction") or _zone_relation(latest, z["zone"], pad))
        for z in zones
        if z["side"] == "upper" and _touches_upper_zone(latest, prev_close, z["zone"], pad)
    ]

    # Directional override:
    # - strong red candle that touched an upper area should be treated as
    #   upper-zone rejection, not a neutral "upper test".
    # - strong green candle that touched a lower area should be treated as
    #   lower-zone reclaim, not a neutral "lower test".
    is_red = close < open_
    is_green = close > open_

    # If a bearish candle actually reaches a lower area, prefer the pullback /
    # support-test description over "upper-zone rejection".  This matches the
    # user's intraday use case: a waterfall into a useful area should wake them
    # up for the possible reaction, not describe only where the drop started.
    if is_red and lower_hits:
        return _best_zone(lower_hits, close, "lower")
    if is_green and upper_hits:
        return _best_zone(upper_hits, close, "upper")

    rejected_upper = [z for z in upper_hits if z.get("interaction") == "rejected_below"]
    reclaimed_lower = [z for z in lower_hits if z.get("interaction") == "reclaimed_above"]
    if is_red and rejected_upper:
        return _best_zone(rejected_upper, close, "upper")
    if is_green and reclaimed_lower:
        return _best_zone(reclaimed_lower, close, "lower")

    if lower_hits:
        # Prefer the closest lower zone.
        return _best_zone(lower_hits, close, "lower")
    if upper_hits:
        return _best_zone(upper_hits, close, "upper")
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
    interaction = str(selected.get("interaction", "inside"))
    zone_cluster = _zone_cluster_hash(zone, side, zone_source, atr, close)
    current_bar = _bar_open_time(latest, len(klines_1h))

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
        if interaction == "reclaimed_above" or (fast_up and close > zone[1]):
            alert_type = "LOWER_KEY_ZONE_RECLAIM"
            phase = "lower_reclaim"
        elif fast_down:
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
        if interaction == "rejected_below" or (fast_down and close < zone[0]):
            alert_type = "UPPER_KEY_ZONE_REJECTION"
            phase = "upper_rejection"
        elif fast_up:
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
    prev_zone_cluster = str(observation_state.get("active_zone_cluster", ""))
    was_inside = bool(observation_state.get("inside_zone", False))
    prev_phase = str(observation_state.get("last_phase", ""))
    prev_side = str(observation_state.get("last_side", ""))
    reentry_count = int(observation_state.get("reentry_count", 0) or 0)
    bars_since_alert = _bars_between(current_bar, observation_state.get("last_alert_open_time"))

    same_exact_zone = zone_hash == prev_zone_hash
    same_cluster = zone_cluster == prev_zone_cluster and side == prev_side
    actionable_upgrade = phase in {"lower_reclaim", "upper_rejection"}
    passive_observation = phase in {
        "fast_pullback",
        "fast_rebound",
        "lower_test",
        "upper_test",
        "range_lower_probe",
        "range_upper_probe",
    }

    reentered = not was_inside or not same_cluster
    if reentered:
        reentry_count += 1

    suppress_reason = ""
    if score < cfg["min_observation_score"]:
        suppress_reason = "below_observation_score"
    elif was_inside and same_cluster and phase == prev_phase:
        suppress_reason = "inside_zone_unchanged"
    elif was_inside and same_exact_zone and phase == prev_phase:
        suppress_reason = "inside_zone_unchanged"
    elif was_inside and passive_observation and bars_since_alert is not None and bars_since_alert < cfg.get("min_realert_bars", 4):
        # After an impulse / waterfall, repeated passive tests are not useful.
        # Wait for reclaim/rejection/real boundary break before speaking again.
        suppress_reason = "post_impulse_waiting_for_reaction"
    elif was_inside and same_cluster and passive_observation and not actionable_upgrade:
        suppress_reason = "same_zone_no_new_reaction"

    should_alert = suppress_reason == ""
    state_version = f"{phase.upper()}_R{reentry_count}"

    update = {
        "inside_zone": True,
        "active_zone_hash": zone_hash,
        "active_zone_cluster": zone_cluster,
        "reentry_count": reentry_count,
        "last_phase": phase,
        "last_side": side,
        "last_alert_type": alert_type if should_alert else observation_state.get("last_alert_type", alert_type),
        "last_alert_open_time": current_bar if should_alert else observation_state.get("last_alert_open_time"),
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
