from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from typing import Any

from engine.indicators import enrich_klines
from engine.liquidity import build_liquidity_context
from engine.msb_ob import build_msb_ob_context


@dataclass(frozen=True)
class PrealertConfig:
    """15m early-entry shadow configuration.

    The 15m layer is intentionally isolated from the 1H scanner:
    - it never changes 1H decisions;
    - it never changes 1H Telegram copy;
    - it only returns/logs a possible long/short entry location while shadowed.
    """

    touch_atr_mult: float = 0.24
    touch_pct: float = 0.0010
    min_reaction_body_ratio: float = 0.46
    min_wick_body_ratio: float = 0.70
    min_long_wick_body_ratio: float = 0.90
    min_short_wick_body_ratio: float = 0.70
    min_risk_reward_room: float = 0.0026
    max_risk_pct: float = 0.0042
    cooldown_bars: int = 12
    min_lead_to_1h_close_min: int = 30
    min_trigger_score: int = 8
    min_klines_15m: int = 80
    min_klines_1h: int = 80
    max_zone_width_pct: float = 0.0120
    local_sweep_lookback: int = 12
    require_1h_context: bool = True
    fvg_only_requires_liquidity: bool = True


DEFAULT_PREALERT_CONFIG = PrealertConfig()


def _f(value: Any, default: float = 0.0) -> float:
    try:
        f = float(value)
        if math.isnan(f) or math.isinf(f):
            return default
        return f
    except (TypeError, ValueError):
        return default


def _ordered_zone(zone: tuple[float, float] | list[float]) -> tuple[float, float]:
    a, b = float(zone[0]), float(zone[1])
    return (round(min(a, b), 2), round(max(a, b), 2))


def _zone_hash(zone: tuple[float, float], side: str) -> str:
    zl, zh = zone
    # Coarse clustering prevents the same 1H area from bypassing 15m cooldown.
    cluster_low = round(zl / 150.0) * 150
    cluster_high = round(zh / 150.0) * 150
    return hashlib.md5(f"{side}|{cluster_low:.0f}|{cluster_high:.0f}".encode()).hexdigest()[:10]


def _temperature_bucket(k: dict[str, Any]) -> str:
    value = _f(k.get("tai_value"))
    p20 = _f(k.get("tai_p20"))
    p40 = _f(k.get("tai_p40"))
    p60 = _f(k.get("tai_p60"))
    p80 = _f(k.get("tai_p80"))
    if not (p20 < p40 < p60 < p80):
        return "中性"
    if value < p20:
        return "过冷"
    if value < p40:
        return "偏冷"
    if value < p60:
        return "中性"
    if value < p80:
        return "偏热"
    return "过热"


def _momentum_state(k15: list[dict[str, Any]]) -> dict[str, Any]:
    latest = k15[-1]
    prev = k15[-2]
    prev3 = k15[-3] if len(k15) >= 3 else prev

    rar_now = _f(latest.get("rar_value"), 50.0)
    rar_prev = _f(prev.get("rar_value"), 50.0)
    rar_prev3 = _f(prev3.get("rar_value"), rar_prev)
    rar_trigger = _f(latest.get("rar_trigger"), 50.0)
    rar_slope = rar_now - rar_prev3

    inertia_now = _f(latest.get("inertia"), 50.0)
    inertia_prev = _f(prev3.get("inertia"), inertia_now)
    inertia_slope = inertia_now - inertia_prev

    close = _f(latest.get("close"))
    prev_close = _f(prev.get("close"), close)
    open_ = _f(latest.get("open"))
    atr = max(_f(latest.get("atr")), abs(close) * 0.001, 1.0)
    price_impulse = (close - prev_close) / max(atr, 1e-9)

    vol = _f(latest.get("volume"), 0.0)
    vol_sma20 = _f(latest.get("vol_sma20"), 0.0)
    volume_ratio = vol / max(vol_sma20, 1e-9) if vol_sma20 > 0 else 1.0

    turn_down = rar_now < rar_trigger or rar_now < rar_prev or rar_slope < -0.35 or inertia_slope < -0.35
    turn_up = rar_now > rar_trigger or rar_now > rar_prev or rar_slope > 0.35 or inertia_slope > 0.35

    return {
        "rar_now": rar_now,
        "rar_trigger": rar_trigger,
        "rar_slope": rar_slope,
        "inertia_slope": inertia_slope,
        "price_impulse": price_impulse,
        "volume_ratio": volume_ratio,
        "turn_down": bool(turn_down),
        "turn_up": bool(turn_up),
        "bearish_candle": close < open_,
        "bullish_candle": close > open_,
    }


def _momentum_bucket(k15: list[dict[str, Any]], side: str) -> str:
    m = _momentum_state(k15)
    if side == "short":
        if m["turn_down"] and m["bearish_candle"]:
            return "短线动能转弱"
        if m["price_impulse"] < -0.35:
            return "短线卖压释放"
        return "短线买盘衰减"
    if m["turn_up"] and m["bullish_candle"]:
        return "短线动能修复"
    if m["price_impulse"] > 0.35:
        return "短线买盘修复"
    return "短线卖压衰减"


def _htf_context_text(klines_4h: list[dict[str, Any]]) -> str:
    latest = klines_4h[-1]
    ema10 = _f(latest.get("ema10"))
    ema20 = _f(latest.get("ema20"))
    close = _f(latest.get("close"))
    atr = max(_f(latest.get("atr")), abs(close) * 0.002, 1.0)
    strength = abs(ema10 - ema20) / atr
    if strength <= 0.45:
        return "4H 震荡"
    return "4H 偏多" if ema10 > ema20 else "4H 偏空"


def _context_text_1h(msb: dict[str, Any], liq: dict[str, Any]) -> str:
    direction = str(msb.get("direction", "neutral"))
    sweep = str(liq.get("sweep_type", "none"))
    rr = str(liq.get("reclaim_or_reject", "none"))

    if sweep == "buyside" and rr == "reject":
        return "1H 扫上失败语境"
    if sweep == "sellside" and rr == "reclaim":
        return "1H 扫下收回语境"
    if direction == "bull":
        return "1H 多头结构语境"
    if direction == "bear":
        return "1H 空头结构语境"
    if msb.get("active_fvg_zone"):
        return "1H FVG/回补语境"
    if msb.get("has_order_block_context"):
        return "1H OB/MB 语境"
    return "1H 震荡结构语境"


def _candidate_zones(klines_1h: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    liq = build_liquidity_context(klines_1h)
    msb = build_msb_ob_context(klines_1h, liq)
    zones: list[dict[str, Any]] = []

    fvg_zone = msb.get("active_fvg_zone")
    if fvg_zone:
        fvg_direction = str(msb.get("active_fvg_direction", "none"))
        if fvg_direction == "bull":
            sides = ["long"]
            role = "support"
        elif fvg_direction == "bear":
            sides = ["short"]
            role = "resistance"
        else:
            sides = ["long", "short"]
            role = "dual"
        zones.append(
            {
                "zone": _ordered_zone(fvg_zone),
                "source": "fvg_zone",
                "direction": fvg_direction,
                "sides": sides,
                "role": role,
                "priority": 2,
                "structural": bool(msb.get("has_order_block_context")),
            }
        )

    msb_direction = str(msb.get("direction", "neutral"))
    has_ob_context = bool(msb.get("has_order_block_context"))
    recent_sweep = bool(liq.get("recent_sweep_valid"))

    # Broad zones are useful only when 1H has a real OB/MSB/sweep/FVG context.
    # They are not allowed to become a standalone moving-range trigger.
    allow_broad = has_ob_context or recent_sweep or bool(fvg_zone)
    if allow_broad:
        for key, source, priority in (
            ("mid_observe_zone", "mid_observe_zone", 4),
            ("order_block_zone", "order_block_zone", 3),
            ("structure_zone", "structure_zone", 1),
        ):
            zone = msb.get(key)
            if not zone:
                continue
            if msb_direction == "bull":
                sides = ["long"]
                role = "support"
            elif msb_direction == "bear":
                sides = ["short"]
                role = "resistance"
            else:
                sides = ["long", "short"]
                role = "dual"
            zones.append(
                {
                    "zone": _ordered_zone(zone),
                    "source": source,
                    "direction": msb_direction,
                    "sides": sides,
                    "role": role,
                    "priority": priority,
                    "structural": has_ob_context,
                }
            )

    # Deduplicate near-identical zones while preserving higher priority.
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for z in sorted(zones, key=lambda x: int(x["priority"]), reverse=True):
        zl, zh = z["zone"]
        key = f"{round(zl / 50)}-{round(zh / 50)}-{','.join(z['sides'])}"
        if key in seen:
            continue
        seen.add(key)
        out.append(z)
    return out, liq, msb


def _touches_zone(k: dict[str, Any], zone: tuple[float, float], pad: float) -> bool:
    zl, zh = zone
    return _f(k.get("high")) >= zl - pad and _f(k.get("low")) <= zh + pad


def _reaction_quality(k: dict[str, Any]) -> tuple[float, float, float]:
    open_ = _f(k.get("open"))
    close = _f(k.get("close"))
    high = _f(k.get("high"))
    low = _f(k.get("low"))
    rng = max(high - low, 1e-9)
    body = abs(close - open_)
    upper_wick = high - max(open_, close)
    lower_wick = min(open_, close) - low
    return body / rng, upper_wick / max(body, 1e-9), lower_wick / max(body, 1e-9)


def _zone_position(zone: tuple[float, float], close: float) -> str:
    zl, zh = zone
    if close < zl:
        return "below"
    if close > zh:
        return "above"
    return "inside"


def _lead_to_1h_close_min(k: dict[str, Any]) -> int:
    open_time = int(k.get("open_time", 0) or 0)
    return int(60 - ((open_time // 60000) % 60))


def _local_sweep_event(k15: list[dict[str, Any]], cfg: PrealertConfig) -> dict[str, Any]:
    """Detect a recent 15m sweep/reclaim/reject event.

    This is the early-entry part of the engine.  It may look back one closed
    15m bar so that the bot can still log the setup after the first confirmation
    candle, without waiting for a full 1H candle.
    """

    if len(k15) < cfg.local_sweep_lookback + 3:
        return {
            "event": "none",
            "level": None,
            "bars_ago": None,
            "sweep_high_reject": False,
            "sweep_low_reclaim": False,
        }

    close = _f(k15[-1].get("close"))
    atr = max(_f(k15[-1].get("atr")), abs(close) * 0.001, 1.0)
    buffer = max(atr * 0.08, abs(close) * 0.00035)

    # Check latest first, then previous bar.  Earlier events become too stale
    # for a 15m entry-position alert.
    for bars_ago in (0, 1):
        idx = len(k15) - 1 - bars_ago
        bar = k15[idx]
        hist_start = max(0, idx - cfg.local_sweep_lookback)
        hist = k15[hist_start:idx]
        if len(hist) < max(4, cfg.local_sweep_lookback // 2):
            continue

        prev_high = max(_f(k.get("high")) for k in hist)
        prev_low = min(_f(k.get("low")) for k in hist)
        high = _f(bar.get("high"))
        low = _f(bar.get("low"))
        bar_close = _f(bar.get("close"))

        if high > prev_high + buffer and bar_close < prev_high - buffer:
            # If previous bar swept high, require current bar not to reclaim it.
            if bars_ago == 1 and close > prev_high + buffer:
                continue
            return {
                "event": "sweep_high_reject",
                "level": round(prev_high, 2),
                "bars_ago": bars_ago,
                "sweep_high_reject": True,
                "sweep_low_reclaim": False,
            }

        if low < prev_low - buffer and bar_close > prev_low + buffer:
            # If previous bar swept low, require current bar not to lose it.
            if bars_ago == 1 and close < prev_low - buffer:
                continue
            return {
                "event": "sweep_low_reclaim",
                "level": round(prev_low, 2),
                "bars_ago": bars_ago,
                "sweep_high_reject": False,
                "sweep_low_reclaim": True,
            }

    return {
        "event": "none",
        "level": None,
        "bars_ago": None,
        "sweep_high_reject": False,
        "sweep_low_reclaim": False,
    }


def _nearest_key_level(price: float) -> dict[str, Any]:
    """BTC round-number context.

    This is not a standalone trigger.  It only explains/supports a setup that
    already has 1H context and 15m reaction.
    """

    if price <= 0:
        return {"level": None, "distance_pct": None, "kind": "none"}

    steps = [1000.0, 500.0, 250.0]
    best_level: float | None = None
    best_step = 0.0
    best_dist = float("inf")
    for step in steps:
        level = round(price / step) * step
        dist = abs(price - level)
        if dist < best_dist:
            best_level, best_step, best_dist = level, step, dist

    distance_pct = best_dist / max(price, 1e-9)
    if best_step >= 1000:
        kind = "整数位"
    elif best_step >= 500:
        kind = "半整数位"
    else:
        kind = "短线整数位"
    return {"level": round(float(best_level), 2), "distance_pct": distance_pct, "kind": kind}


def _key_level_reaction(side: str, latest: dict[str, Any], key: dict[str, Any], pad: float) -> str:
    level = key.get("level")
    if level is None:
        return "none"

    level_f = float(level)
    high = _f(latest.get("high"))
    low = _f(latest.get("low"))
    close = _f(latest.get("close"))
    open_ = _f(latest.get("open"))
    near = low - pad <= level_f <= high + pad
    if not near:
        return "none"

    if side == "short" and high >= level_f - pad and close < level_f and close <= open_:
        return "key_reject"
    if side == "long" and low <= level_f + pad and close > level_f and close >= open_:
        return "key_reclaim"
    return "key_touch"


def _zone_interaction(
    side: str,
    latest: dict[str, Any],
    prev: dict[str, Any],
    zone: tuple[float, float],
    pad: float,
) -> dict[str, Any]:
    zl, zh = zone
    close = _f(latest.get("close"))
    open_ = _f(latest.get("open"))
    high = _f(latest.get("high"))
    low = _f(latest.get("low"))
    prev_close = _f(prev.get("close"), close)
    zone_mid = (zl + zh) / 2.0
    body_ratio, upper_wick_ratio, lower_wick_ratio = _reaction_quality(latest)
    touched = _touches_zone(latest, zone, pad) or _touches_zone(prev, zone, pad)
    upper_half_touched = high >= zone_mid - pad
    lower_half_touched = low <= zone_mid + pad

    if side == "short":
        rejected = touched and close <= zh + pad * 0.15 and (
            close < prev_close
            or close <= zone_mid
            or (upper_half_touched and close < open_)
        )
        wick = upper_wick_ratio >= 0.70
        body = body_ratio >= 0.46 and close < open_
        close_through = close < zl - pad * 0.20
        location_ok = close <= zh + pad and high >= zl - pad
        reaction = "upper_reject" if rejected else "zone_touch"
    else:
        reclaimed = touched and close >= zl - pad * 0.15 and (
            close > prev_close
            or close >= zone_mid
            or (lower_half_touched and close > open_)
        )
        wick = lower_wick_ratio >= 0.90
        body = body_ratio >= 0.46 and close > open_
        close_through = close > zh + pad * 0.20
        location_ok = close >= zl - pad and low <= zh + pad
        rejected = reclaimed
        reaction = "lower_reclaim" if reclaimed else "zone_touch"

    return {
        "touched": bool(touched),
        "location_ok": bool(location_ok),
        "reacted": bool(rejected),
        "wick_ok": bool(wick),
        "body_ok": bool(body),
        "close_through": bool(close_through),
        "body_ratio": body_ratio,
        "upper_wick_ratio": upper_wick_ratio,
        "lower_wick_ratio": lower_wick_ratio,
        "position": _zone_position(zone, close),
        "reaction": reaction,
    }


def _risk_ok(side: str, entry: float, zone: tuple[float, float], latest: dict[str, Any], cfg: PrealertConfig) -> tuple[bool, float, float, float]:
    atr = max(_f(latest.get("atr")), abs(entry) * 0.001, 1.0)
    pad = max(atr * 0.25, abs(entry) * 0.001)
    zl, zh = zone

    if side == "short":
        invalid = round(max(zh, _f(latest.get("high"))) + pad, 2)
        risk_pct = max(0.0, (invalid - entry) / max(entry, 1e-9))
        room_pct = max(0.0, (entry - zl) / max(entry, 1e-9))
    else:
        invalid = round(min(zl, _f(latest.get("low"))) - pad, 2)
        risk_pct = max(0.0, (entry - invalid) / max(entry, 1e-9))
        room_pct = max(0.0, (zh - entry) / max(entry, 1e-9))

    return risk_pct <= cfg.max_risk_pct and room_pct >= cfg.min_risk_reward_room, invalid, round(risk_pct, 5), round(room_pct, 5)


def _tai_filter(side: str, temperature: str, latest: dict[str, Any], momentum: dict[str, Any]) -> tuple[str, int, str]:
    """Return (filter_text, score_delta, hard_reject_reason)."""

    close = _f(latest.get("close"))
    open_ = _f(latest.get("open"))
    price_down = close < open_ or momentum["price_impulse"] < -0.15
    price_up = close > open_ or momentum["price_impulse"] > 0.15

    if side == "short":
        if temperature in {"偏热", "过热"} and price_down:
            return "TAI活跃但价格承压", 1, ""
        if temperature in {"偏冷", "过冷"} and not price_down:
            return "TAI偏冷，做空降权", -1, "tai_cold_without_short_reaction"
        return f"TAI {temperature}", 0, ""

    if temperature in {"偏冷", "过冷"} and price_up:
        return "TAI低位修复", 1, ""
    if temperature in {"偏热", "过热"} and not price_up:
        return "TAI偏热，做多降权", -1, "tai_hot_without_long_reclaim"
    return f"TAI {temperature}", 0, ""


def _score_setup(
    side: str,
    cand: dict[str, Any],
    klines_15m: list[dict[str, Any]],
    zone: tuple[float, float],
    cfg: PrealertConfig,
    htf_text: str,
    msb: dict[str, Any],
    liq1h: dict[str, Any],
) -> dict[str, Any]:
    latest = klines_15m[-1]
    prev = klines_15m[-2]
    entry = _f(latest.get("close"))
    atr = max(_f(latest.get("atr")), abs(entry) * 0.001, 1.0)
    pad = max(atr * cfg.touch_atr_mult, abs(entry) * cfg.touch_pct)
    zone_width_pct = (zone[1] - zone[0]) / max(entry, 1e-9)

    if zone_width_pct > cfg.max_zone_width_pct:
        return {"ok": False, "reject_reason": "zone_too_wide", "score": 0}

    if side not in cand.get("sides", ["long", "short"]):
        return {"ok": False, "reject_reason": "zone_role_mismatch", "score": 0}

    interaction = _zone_interaction(side, latest, prev, zone, pad)
    if not interaction["location_ok"] or not interaction["touched"]:
        return {"ok": False, "reject_reason": "not_near_1h_poi", "score": 0}

    local_liq = _local_sweep_event(klines_15m, cfg)
    momentum = _momentum_state(klines_15m)
    temperature = _temperature_bucket(latest)
    tai_text, tai_score, tai_reject = _tai_filter(side, temperature, latest, momentum)
    key = _nearest_key_level(entry)
    key_reaction = _key_level_reaction(side, latest, key, pad)

    source = str(cand.get("source", "context_zone"))
    score = 0
    reasons: list[str] = []

    # 1H/4H context: required for the 15m entry reminder, but not enough alone.
    score += 2
    reasons.append(_context_text_1h(msb, liq1h))

    if source in {"order_block_zone", "mid_observe_zone"}:
        score += 2
        reasons.append("1H OB/MB POI")
    elif source == "structure_zone":
        score += 1
        reasons.append("1H 结构区")
    elif source == "fvg_zone":
        score += 1
        reasons.append("1H FVG")
    else:
        # Backward-compatible test/custom zones are treated as contextual POI.
        score += 2
        reasons.append("1H 自定义 POI")

    if side == "short":
        if local_liq["sweep_high_reject"]:
            score += 3
            reasons.append("15m 扫上失败")
        if interaction["reacted"]:
            score += 2
            reasons.append("15m 压力反应")
        if interaction["wick_ok"]:
            score += 1
            reasons.append("上影线拒绝")
        if interaction["body_ok"] or interaction["close_through"]:
            score += 1
            reasons.append("15m 收线偏弱")
        if momentum["turn_down"]:
            score += 1
            reasons.append("RAR/Inertial 转弱")
        if key_reaction == "key_reject":
            score += 1
            reasons.append(f"{key['kind']}被拒")
        if htf_text == "4H 偏多":
            score -= 1
            reasons.append("4H偏多，做空降权")
        reaction_type = "sweep_high_reject" if local_liq["sweep_high_reject"] else interaction["reaction"]
        setup_type = "short_entry_prealert"
    else:
        if local_liq["sweep_low_reclaim"]:
            score += 3
            reasons.append("15m 扫下收回")
        if interaction["reacted"]:
            score += 2
            reasons.append("15m 承接反应")
        if interaction["wick_ok"]:
            score += 1
            reasons.append("下影线收回")
        if interaction["body_ok"] or interaction["close_through"]:
            score += 1
            reasons.append("15m 收线修复")
        if momentum["turn_up"]:
            score += 1
            reasons.append("RAR/Inertial 修复")
        if key_reaction == "key_reclaim":
            score += 1
            reasons.append(f"{key['kind']}收回")
        if htf_text == "4H 偏空":
            score -= 1
            reasons.append("4H偏空，做多降权")
        reaction_type = "sweep_low_reclaim" if local_liq["sweep_low_reclaim"] else interaction["reaction"]
        setup_type = "long_entry_prealert"

    score += tai_score
    if tai_text:
        reasons.append(tai_text)

    # Core anti-noise gate: no single FVG / no single TAI / no single touch.
    has_liquidity = bool(local_liq["sweep_high_reject"] if side == "short" else local_liq["sweep_low_reclaim"])
    has_zone_reaction = bool(interaction["reacted"] and (interaction["wick_ok"] or interaction["body_ok"] or interaction["close_through"]))
    has_key_reaction = key_reaction in {"key_reject", "key_reclaim"}

    if not (has_liquidity or has_zone_reaction or has_key_reaction):
        return {"ok": False, "reject_reason": "no_15m_reaction_confirmation", "score": score}

    if source == "fvg_zone" and cfg.fvg_only_requires_liquidity and not (has_liquidity or has_key_reaction):
        return {"ok": False, "reject_reason": "fvg_only_without_liquidity", "score": score}

    if tai_reject and not (has_liquidity or has_key_reaction):
        return {"ok": False, "reject_reason": tai_reject, "score": score}

    risk_ok, invalid, risk_pct, room_pct = _risk_ok(side, entry, zone, latest, cfg)
    if not risk_ok:
        return {
            "ok": False,
            "reject_reason": "risk_reward_not_enough",
            "score": score,
            "risk_pct": risk_pct,
            "room_pct": room_pct,
            "invalid_level": invalid,
        }

    ok = score >= cfg.min_trigger_score
    if not ok:
        return {"ok": False, "reject_reason": "trigger_score_too_low", "score": score}

    liquidity_event = str(local_liq["event"])
    if liquidity_event == "none":
        liquidity_event = "zone_reaction_without_local_sweep"

    key_context = "none"
    if key.get("level") is not None and key.get("distance_pct") is not None:
        key_context = f"{key['kind']} {key['level']} distance={float(key['distance_pct']):.3%} reaction={key_reaction}"

    return {
        "ok": True,
        "score": score,
        "invalid_level": invalid,
        "risk_pct": risk_pct,
        "room_pct": room_pct,
        "setup_type": setup_type,
        "liquidity_event": liquidity_event,
        "structure_context": _context_text_1h(msb, liq1h),
        "poi_type": source,
        "key_level_context": key_context,
        "reaction_type": reaction_type,
        "momentum_filter": _momentum_bucket(klines_15m, side),
        "tai_regime": temperature,
        "early_entry_reason": " + ".join(reasons[:8]),
        "trigger_score": score,
        "reject_reason": "",
        "zone_position": interaction["position"],
        "reaction_score": score,
        "zone_width_pct": round(zone_width_pct, 5),
        "rar_now": round(float(momentum["rar_now"]), 3),
        "rar_trigger": round(float(momentum["rar_trigger"]), 3),
        "price_impulse": round(float(momentum["price_impulse"]), 3),
        "volume_ratio": round(float(momentum["volume_ratio"]), 3),
    }


def evaluate_15m_prealert(
    symbol: str,
    klines_15m: list[dict[str, Any]],
    klines_1h: list[dict[str, Any]],
    klines_4h: list[dict[str, Any]],
    cfg: PrealertConfig = DEFAULT_PREALERT_CONFIG,
) -> dict[str, Any]:
    """Return a 15m prealert decision.

    v1.3.0 design:
    - 1H remains the official alert body and logic owner.
    - 15m is only an early-entry location reminder.
    - This function is shadow/log/backtest safe and never sends Telegram.
    """

    if len(klines_15m) < cfg.min_klines_15m or len(klines_1h) < cfg.min_klines_1h or len(klines_4h) < 20:
        return {
            "symbol": symbol,
            "timeframe": "15m",
            "alert_type": "NO_15M_PREALERT",
            "direction": "neutral",
            "should_alert": False,
            "shadow_only": True,
            "primary_timeframe": "1h",
            "does_not_affect_1h": True,
            "suppress_reason": "insufficient_history",
        }

    latest = klines_15m[-1]
    entry = _f(latest.get("close"))
    lead_to_close = _lead_to_1h_close_min(latest)
    if lead_to_close < cfg.min_lead_to_1h_close_min:
        return {
            "symbol": symbol,
            "timeframe": "15m",
            "alert_type": "NO_15M_PREALERT",
            "direction": "neutral",
            "price": round(entry, 2),
            "should_alert": False,
            "shadow_only": True,
            "primary_timeframe": "1h",
            "does_not_affect_1h": True,
            "suppress_reason": "too_close_to_1h_close",
            "lead_to_1h_close_min": lead_to_close,
        }

    candidate_result = _candidate_zones(klines_1h)
    if (
        isinstance(candidate_result, tuple)
        and len(candidate_result) == 3
    ):
        candidates, liq1h, msb = candidate_result
    else:
        # Compatibility for tests / external callers that patch _candidate_zones
        # to return only a list of zones.
        candidates = candidate_result  # type: ignore[assignment]
        liq1h = build_liquidity_context(klines_1h)
        msb = build_msb_ob_context(klines_1h, liq1h)
    htf_text = _htf_context_text(klines_4h)

    if cfg.require_1h_context and not candidates:
        return {
            "symbol": symbol,
            "timeframe": "15m",
            "alert_type": "NO_15M_PREALERT",
            "direction": "neutral",
            "price": round(entry, 2),
            "should_alert": False,
            "shadow_only": True,
            "primary_timeframe": "1h",
            "does_not_affect_1h": True,
            "suppress_reason": "no_1h_structure_context",
            "htf_context": htf_text,
            "structure_context": _context_text_1h(msb, liq1h),
        }

    best: dict[str, Any] | None = None
    best_reject = "no_qualified_15m_entry_location"

    for cand in candidates:
        zone = cand["zone"]
        for side in ("short", "long"):
            if side not in cand.get("sides", ["long", "short"]):
                continue

            scored = _score_setup(side, cand, klines_15m, zone, cfg, htf_text, msb, liq1h)
            if not scored.get("ok"):
                if int(scored.get("score", 0) or 0) >= int(best["score"]) if best else False:
                    best_reject = str(scored.get("reject_reason", best_reject))
                continue

            risk_pct = float(scored.get("risk_pct", 0.0) or 0.0)
            score = int(scored.get("score", 0) or 0) + int(cand.get("priority", 1))
            candidate = {
                "symbol": symbol,
                "timeframe": "15m",
                "alert_type": "PREALERT_SHORT" if side == "short" else "PREALERT_LONG",
                "direction": side,
                "title": "📍 BTC 15m 做空预警" if side == "short" else "📍 BTC 15m 做多预警",
                "price": round(entry, 2),
                "zone": zone,
                "zone_low": zone[0],
                "zone_high": zone[1],
                "zone_source": cand.get("source", "context_zone"),
                "zone_hash": _zone_hash(zone, side),
                "invalid_level": scored["invalid_level"],
                "risk_pct": round(risk_pct, 5),
                "room_pct": scored.get("room_pct"),
                "score": score,
                "should_alert": True,
                "shadow_only": True,
                "primary_timeframe": "1h",
                "does_not_affect_1h": True,
                "suppress_reason": "",
                "htf_context": htf_text,
                "momentum_desc": scored["momentum_filter"],
                "temperature_desc": f"热度 {scored['tai_regime']}",
                "open_time": int(latest.get("open_time", 0) or 0),
                "close_time": int(latest.get("close_time", 0) or 0),
                "lead_to_1h_close_min": lead_to_close,
                **scored,
            }
            candidate["score"] = score
            if best is None or (candidate["score"], -candidate["risk_pct"]) > (best["score"], -best["risk_pct"]):
                best = candidate

    if best:
        return best

    return {
        "symbol": symbol,
        "timeframe": "15m",
        "alert_type": "NO_15M_PREALERT",
        "direction": "neutral",
        "price": round(entry, 2),
        "should_alert": False,
        "shadow_only": True,
        "primary_timeframe": "1h",
        "does_not_affect_1h": True,
        "suppress_reason": best_reject,
        "htf_context": htf_text,
        "structure_context": _context_text_1h(msb, liq1h),
    }


def format_prealert_log(decision: dict[str, Any]) -> str:
    if not decision.get("should_alert"):
        return (
            f"no_15m_prealert symbol={decision.get('symbol')} "
            f"reason={decision.get('suppress_reason')} price={decision.get('price')}"
        )

    zone = decision.get("zone") or (decision.get("zone_low"), decision.get("zone_high"))
    return (
        "would_send_15m_prealert "
        f'title="{decision.get("title")}" '
        f"side={decision.get('direction')} "
        f"price={float(decision.get('price')):.2f} "
        f"zone={float(zone[0]):.2f}-{float(zone[1]):.2f} "
        f"invalid={float(decision.get('invalid_level')):.2f} "
        f"source={decision.get('zone_source')} "
        f"setup={decision.get('setup_type')} "
        f"reason={decision.get('early_entry_reason')} "
        f"htf={decision.get('htf_context')} "
        f"momentum={decision.get('momentum_desc')} "
        f"temperature={decision.get('temperature_desc')}"
    )


def ensure_enriched(klines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not klines:
        return []
    if "atr" in klines[-1] and "rar_value" in klines[-1] and "tai_value" in klines[-1]:
        return klines
    return enrich_klines(klines)
