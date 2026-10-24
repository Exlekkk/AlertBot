from __future__ import annotations

import math
from typing import Any

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


def _zone(value: Any) -> tuple[float, float] | None:
    if not isinstance(value, (list, tuple)) or len(value) < 2:
        return None
    low = _f(value[0], float("nan"))
    high = _f(value[1], float("nan"))
    if math.isnan(low) or math.isnan(high):
        return None
    low, high = min(low, high), max(low, high)
    return (low, high) if high > low else None


def _distance_to_zone(close: float, value: Any) -> float | None:
    zone = _zone(value)
    if not zone:
        return None
    if zone[0] <= close <= zone[1]:
        return 0.0
    return min(abs(close - zone[0]), abs(close - zone[1]))


def _append_score(scores: dict[str, float], evidence: dict[str, list[str]], side: str, value: float, reason: str) -> None:
    scores[side] += value
    evidence[side].append(f"{reason}:{value:+.2f}")


def _box_context(
    close: float,
    range_lock: dict[str, Any],
    ict: dict[str, Any],
) -> tuple[bool, float | None, float | None, float | None, str]:
    active = bool(range_lock.get("active", False)) or bool(ict.get("coexist", False))
    box_low = _f(range_lock.get("box_low"), float("nan"))
    box_high = _f(range_lock.get("box_high"), float("nan"))

    if math.isnan(box_low) or math.isnan(box_high) or box_high <= box_low:
        bull = _zone(ict.get("bullish_nearest"))
        bear = _zone(ict.get("bearish_nearest"))
        if bull and bear:
            box_low = min(bull[0], bear[0])
            box_high = max(bull[1], bear[1])

    if math.isnan(box_low) or math.isnan(box_high) or box_high <= box_low:
        return active, None, None, None, "unknown"

    ratio = (close - box_low) / max(box_high - box_low, 1e-9)
    cfg = TREND_ENGINE_CONFIG["trial_decision"]
    if ratio < 0:
        position = "below_box"
    elif ratio > 1:
        position = "above_box"
    elif ratio <= float(cfg.get("range_lower_cut", 0.38)):
        position = "lower_edge"
    elif ratio >= float(cfg.get("range_upper_cut", 0.62)):
        position = "upper_edge"
    else:
        position = "middle"
    return active, box_low, box_high, ratio, position


def build_trial_context(
    klines_1h: list[dict[str, Any]],
    htf_ctx: dict[str, Any],
    liq: dict[str, Any],
    msb: dict[str, Any],
    matrix: dict[str, Any],
    aux: dict[str, Any],
    vp: dict[str, Any] | None = None,
    range_lock: dict[str, Any] | None = None,
    ict: dict[str, Any] | None = None,
    evidence_bundle: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build weighted 1H direction context for formal trial decisions.

    This layer intentionally does not require a fixed indicator checklist.
    Structure, location, acceptance and auxiliary evidence add or subtract
    weight; only risk/location/staleness become hard blocks later.
    """

    latest = klines_1h[-1]
    close = _f(latest.get("close"))
    atr = max(_f(latest.get("atr"), max(abs(close) * 0.004, 1.0)), 1e-9)
    vp = vp or {}
    range_lock = range_lock or {}
    ict = ict or {}
    evidence_bundle = evidence_bundle if isinstance(evidence_bundle, dict) else {}

    scores = {"long": 0.0, "short": 0.0}
    evidence = {"long": [], "short": []}

    ict_exact_bonus = 0.5 if bool(ict.get("is_exact", False)) else 0.0
    if ict.get("bullish_active"):
        _append_score(scores, evidence, "long", 1.5 + ict_exact_bonus, "ict_plus_ob_active")
    if ict.get("bearish_active"):
        _append_score(scores, evidence, "short", 1.5 + ict_exact_bonus, "ict_minus_ob_active")

    bull_dist = ict.get("bullish_distance_atr")
    bear_dist = ict.get("bearish_distance_atr")
    if bull_dist is not None and _f(bull_dist, 99.0) <= 0.35:
        _append_score(scores, evidence, "long", 2.0, "near_ict_plus_ob")
    if bear_dist is not None and _f(bear_dist, 99.0) <= 0.35:
        _append_score(scores, evidence, "short", 2.0, "near_ict_minus_ob")

    ict_structure_direction = str(ict.get("structure_direction", "neutral"))
    ict_structure_event = str(ict.get("structure_event", "none"))
    ict_structure_age = ict.get("structure_event_age")
    if ict_structure_direction == "bull":
        _append_score(scores, evidence, "long", 1.0, "ict_structure_bull")
    elif ict_structure_direction == "bear":
        _append_score(scores, evidence, "short", 1.0, "ict_structure_bear")
    if ict_structure_age is not None and _f(ict_structure_age, 99.0) <= 4:
        if ict_structure_event == "bullish_mss":
            _append_score(scores, evidence, "long", 2.5, "fresh_bullish_mss")
        elif ict_structure_event == "bearish_mss":
            _append_score(scores, evidence, "short", 2.5, "fresh_bearish_mss")
        elif ict_structure_event == "bullish_bos":
            _append_score(scores, evidence, "long", 1.5, "fresh_bullish_bos")
        elif ict_structure_event == "bearish_bos":
            _append_score(scores, evidence, "short", 1.5, "fresh_bearish_bos")

    if ict.get("bullish_fvg"):
        _append_score(scores, evidence, "long", 1.0, "active_ict_bull_fvg")
    if ict.get("bearish_fvg"):
        _append_score(scores, evidence, "short", 1.0, "active_ict_bear_fvg")
    # A broken bullish OB is a bearish breaker; a broken bearish OB is a
    # bullish breaker.  Keep breaker polarity separate from its origin label.
    if ict.get("bullish_breakers"):
        _append_score(scores, evidence, "short", 1.0, "bearish_breaker_context")
    if ict.get("bearish_breakers"):
        _append_score(scores, evidence, "long", 1.0, "bullish_breaker_context")
    premium_discount = str(ict.get("premium_discount", "unknown"))
    if premium_discount == "discount":
        _append_score(scores, evidence, "long", 0.5, "ict_discount_location")
        _append_score(scores, evidence, "short", -0.25, "short_in_discount")
    elif premium_discount == "premium":
        _append_score(scores, evidence, "short", 0.5, "ict_premium_location")
        _append_score(scores, evidence, "long", -0.25, "long_in_premium")

    if bool(liq.get("recent_sweep_valid")):
        if liq.get("sweep_type") == "sellside" and liq.get("reclaim_or_reject") == "reclaim":
            _append_score(scores, evidence, "long", 3.5, "sellside_sweep_reclaim")
        elif liq.get("sweep_type") == "buyside" and liq.get("reclaim_or_reject") == "reject":
            _append_score(scores, evidence, "short", 3.5, "buyside_sweep_reject")

    msb_direction = str(msb.get("direction", "neutral"))
    if msb_direction == "bull":
        _append_score(scores, evidence, "long", 2.5, "msb_bull")
    elif msb_direction == "bear":
        _append_score(scores, evidence, "short", 2.5, "msb_bear")

    fvg_direction = str(msb.get("active_fvg_direction", "none"))
    if fvg_direction == "bull":
        _append_score(scores, evidence, "long", 1.25, "bull_fvg_context")
    elif fvg_direction == "bear":
        _append_score(scores, evidence, "short", 1.25, "bear_fvg_context")

    matrix_direction = str(matrix.get("matrix_direction", "neutral"))
    matrix_source = str(matrix.get("source", "legacy"))
    # Dual-log / classic-swing channel weights peeled (weight 0).
    _ = (matrix_direction, matrix_source)

    fibonacci = msb.get("fibonacci", {}) if isinstance(msb.get("fibonacci"), dict) else {}
    fib_direction = str(fibonacci.get("trend", "neutral"))
    if fib_direction == "bull":
        _append_score(scores, evidence, "long", 0.75, "fibonacci_bull_swing")
        if fibonacci.get("in_ote"):
            _append_score(scores, evidence, "long", 1.25, "bullish_ote_location")
    elif fib_direction == "bear":
        _append_score(scores, evidence, "short", 0.75, "fibonacci_bear_swing")
        if fibonacci.get("in_ote"):
            _append_score(scores, evidence, "short", 1.25, "bearish_ote_location")

    if vp.get("reclaimed_val"):
        _append_score(scores, evidence, "long", 1.5, "value_reclaimed")
    if vp.get("rejected_vah"):
        _append_score(scores, evidence, "short", 1.5, "value_rejected")
    if vp.get("accepted_below_value"):
        _append_score(scores, evidence, "long", -1.5, "accepted_below_value")
        _append_score(scores, evidence, "short", 0.75, "accepted_below_value")
    if vp.get("accepted_above_value"):
        _append_score(scores, evidence, "short", -1.5, "accepted_above_value")
        _append_score(scores, evidence, "long", 0.75, "accepted_above_value")

    fvg_profile = vp.get("fvg_profile", {}) if isinstance(vp.get("fvg_profile"), dict) else {}
    nearest_fvg = fvg_profile.get("nearest") if isinstance(fvg_profile.get("nearest"), dict) else None
    if nearest_fvg:
        fvg_side = str(nearest_fvg.get("direction", "none"))
        distance = _f(nearest_fvg.get("distance"), 99.0) / atr
        if distance <= 0.35 and fvg_side == "bull":
            _append_score(scores, evidence, "long", 1.0, "near_bull_fvg_volume_poc")
        elif distance <= 0.35 and fvg_side == "bear":
            _append_score(scores, evidence, "short", 1.0, "near_bear_fvg_volume_poc")

    volume_pivots = vp.get("high_volume_pivots", {}) if isinstance(vp.get("high_volume_pivots"), dict) else {}
    support = volume_pivots.get("support") if isinstance(volume_pivots.get("support"), dict) else None
    resistance = volume_pivots.get("resistance") if isinstance(volume_pivots.get("resistance"), dict) else None
    if support and _distance_to_zone(close, support.get("zone")) is not None and _f(_distance_to_zone(close, support.get("zone")), 99.0) / atr <= 0.35:
        side = "short" if support.get("broken") else "long"
        _append_score(scores, evidence, side, 1.25, "flipped_volume_support" if support.get("broken") else "high_volume_support")
    if resistance and _distance_to_zone(close, resistance.get("zone")) is not None and _f(_distance_to_zone(close, resistance.get("zone")), 99.0) / atr <= 0.35:
        side = "long" if resistance.get("broken") else "short"
        _append_score(scores, evidence, side, 1.25, "flipped_volume_resistance" if resistance.get("broken") else "high_volume_resistance")

    rar_slope = _f(aux.get("rar_slope"))
    # Inertial fully peeled from trial scoring and phase detection.
    _ = aux.get("inertia_slope")
    if rar_slope >= 0.35:
        _append_score(scores, evidence, "long", 1.0, "rar_turn_up")
    elif rar_slope <= -0.35:
        _append_score(scores, evidence, "short", 1.0, "rar_turn_down")
    if aux.get("rar_above_trigger") and rar_slope >= 0:
        _append_score(scores, evidence, "long", 0.5, "rar_above_trigger")
    elif not aux.get("rar_above_trigger", True) and rar_slope <= 0:
        _append_score(scores, evidence, "short", 0.5, "rar_below_trigger")

    momentum = str(aux.get("momentum_desc", ""))
    if "偏强" in momentum or "买盘" in momentum or ("修复" in momentum and rar_slope > 0):
        _append_score(scores, evidence, "long", 1.5, "momentum_supports_long")
    if "偏弱" in momentum or "卖压" in momentum or "转弱" in momentum:
        _append_score(scores, evidence, "short", 1.5, "momentum_supports_short")

    # 1H formation/TAI temperature peeled; core-levels filter is soft lean only.
    # Prefer scanner evidence_bundle; fall back to aux side-channel.
    core = evidence_bundle.get("core_levels_filter") if isinstance(evidence_bundle.get("core_levels_filter"), dict) else {}
    if not core:
        core = aux.get("core_levels_filter") if isinstance(aux.get("core_levels_filter"), dict) else {}
    if core.get("allowed") and core.get("filter_only", True):
        if core.get("midline_event") == "reclaim_above_50":
            _append_score(scores, evidence, "long", 0.5, "core_levels_reclaim_50")
        elif core.get("midline_event") == "loss_below_50":
            _append_score(scores, evidence, "short", 0.5, "core_levels_loss_50")
        elif core.get("lean") == "bull" and not core.get("squeeze"):
            _append_score(scores, evidence, "long", 0.25, "core_levels_bull_lean")
        elif core.get("lean") == "bear" and not core.get("squeeze"):
            _append_score(scores, evidence, "short", 0.25, "core_levels_bear_lean")

    volume_flow = aux.get("volume_orderflow", {}) if isinstance(aux.get("volume_orderflow"), dict) else {}
    if volume_flow.get("downside_stop_run"):
        _append_score(scores, evidence, "long", 1.5, "volume_proxy_downside_stop_run_reclaim")
    if volume_flow.get("upside_stop_run"):
        _append_score(scores, evidence, "short", 1.5, "volume_proxy_upside_stop_run_reject")
    if volume_flow.get("accepted_breakout_up"):
        _append_score(scores, evidence, "long", 1.5, "volume_accepted_breakout_up")
    if volume_flow.get("accepted_breakout_down"):
        _append_score(scores, evidence, "short", 1.5, "volume_accepted_breakout_down")
    if volume_flow.get("absorption") == "sell_absorption_proxy":
        _append_score(scores, evidence, "long", 0.75, "sell_absorption_proxy")
    elif volume_flow.get("absorption") == "buy_absorption_proxy":
        _append_score(scores, evidence, "short", 0.75, "buy_absorption_proxy")

    h4 = str(htf_ctx.get("h4_direction", ""))
    htf_text = str(htf_ctx.get("text", ""))
    if h4 == "bull" or "偏多" in htf_text:
        _append_score(scores, evidence, "long", 0.75, "h4_bull_background")
    elif h4 == "bear" or "偏空" in htf_text:
        _append_score(scores, evidence, "short", 0.75, "h4_bear_background")

    # --- Candle-approx evidence: prefer scanner evidence_bundle; side-channels are fallback ---
    auto_range = evidence_bundle.get("auto_range") if isinstance(evidence_bundle.get("auto_range"), dict) else {}
    if not auto_range:
        auto_range = range_lock.get("auto_range") if isinstance(range_lock.get("auto_range"), dict) else {}
    last_range_event = auto_range.get("last_event")
    if last_range_event == "deviation_down":
        _append_score(scores, evidence, "long", 1.5, "range_reclaim_after_break_down")
    elif last_range_event == "deviation_up":
        _append_score(scores, evidence, "short", 1.5, "range_reclaim_after_break_up")
    # pending break: soft location pressure only, never a confirmed breakout catalyst
    if auto_range.get("pending_break") == "up":
        _append_score(scores, evidence, "long", 0.25, "range_break_pending_up")
    elif auto_range.get("pending_break") == "down":
        _append_score(scores, evidence, "short", 0.25, "range_break_pending_down")

    sweep_ctx = evidence_bundle.get("sweep") if isinstance(evidence_bundle.get("sweep"), dict) else {}
    if not sweep_ctx:
        sweep_ctx = liq.get("sweep_hunter") if isinstance(liq.get("sweep_hunter"), dict) else {}
    if sweep_ctx.get("swept") and sweep_ctx.get("recent_sweep_valid"):
        if sweep_ctx.get("side") == "sell_side" and sweep_ctx.get("reclaim_or_reject") == "reclaim":
            _append_score(scores, evidence, "long", 2.0, "sweep_sell_side_reclaim")
        elif sweep_ctx.get("side") == "buy_side" and sweep_ctx.get("reclaim_or_reject") == "reject":
            _append_score(scores, evidence, "short", 2.0, "sweep_buy_side_reject")

    delta = evidence_bundle.get("delta_profile") if isinstance(evidence_bundle.get("delta_profile"), dict) else {}
    if not delta:
        delta = vp.get("delta_profile") if isinstance(vp.get("delta_profile"), dict) else {}
    node_bias = str(delta.get("node_bias") or vp.get("node_bias") or "neutral")
    va_pos = str(delta.get("value_area_pos") or vp.get("value_area_pos") or "inside")
    if node_bias == "bull" and va_pos in {"inside", "above"}:
        _append_score(scores, evidence, "long", 1.0, "profile_node_bull")
    elif node_bias == "bear" and va_pos in {"inside", "below"}:
        _append_score(scores, evidence, "short", 1.0, "profile_node_bear")

    # Prefer evidence.ifvg (scanner canonical); fall back to range_lock.imbalance
    imbalance = evidence_bundle.get("ifvg") if isinstance(evidence_bundle.get("ifvg"), dict) else {}
    if not imbalance:
        imbalance = range_lock.get("imbalance") if isinstance(range_lock.get("imbalance"), dict) else {}
    nearest_imb = imbalance.get("nearest_active") if isinstance(imbalance.get("nearest_active"), dict) else None
    if nearest_imb and nearest_imb.get("inverted") and not nearest_imb.get("invalidated"):
        # inverted gap: direction 1 (bullish origin) acting as resistance after invert → short lean
        if int(nearest_imb.get("direction") or 0) == 1:
            _append_score(scores, evidence, "short", 1.25, "imbalance_inverted_resistance")
        elif int(nearest_imb.get("direction") or 0) == -1:
            _append_score(scores, evidence, "long", 1.25, "imbalance_inverted_support")

    # Soft confluence when 2+ structure candle-evidence tags agree (joint weight).
    # Pending-break, soft leans, and core_levels_* filter tags do NOT count —
    # core_levels remains soft filter-only weight, never structure confluence.
    _confluence_tokens = {
        "long": (
            "range_reclaim_after_break_down",
            "sweep_sell_side_reclaim",
            "profile_node_bull",
            "imbalance_inverted_support",
        ),
        "short": (
            "range_reclaim_after_break_up",
            "sweep_buy_side_reject",
            "profile_node_bear",
            "imbalance_inverted_resistance",
        ),
    }
    for _side, _tokens in _confluence_tokens.items():
        _hits = sum(1 for token in _tokens if any(token in r for r in evidence[_side]))
        if _hits >= 2:
            _append_score(scores, evidence, _side, 0.75, "evidence_confluence")

    range_active, box_low, box_high, box_ratio, box_position = _box_context(close, range_lock, ict)
    if range_active and box_position == "lower_edge":
        _append_score(scores, evidence, "long", 1.5, "range_lower_location")
        _append_score(scores, evidence, "short", -2.0, "short_at_range_low")
    elif range_active and box_position == "upper_edge":
        _append_score(scores, evidence, "short", 1.5, "range_upper_location")
        _append_score(scores, evidence, "long", -2.0, "long_at_range_high")
    elif range_active and box_position == "middle":
        _append_score(scores, evidence, "long", -0.75, "range_middle")
        _append_score(scores, evidence, "short", -0.75, "range_middle")

    price_impulse = _f(aux.get("price_impulse"))
    recent = klines_1h[-6:]
    recent_low = min(_f(k.get("low"), close) for k in recent)
    recent_high = max(_f(k.get("high"), close) for k in recent)
    long_extension_atr = max(0.0, close - recent_low) / atr
    short_extension_atr = max(0.0, recent_high - close) / atr
    if range_active:
        delta = scores["long"] - scores["short"]
        phase = "range_bullish" if delta >= 2.0 else "range_bearish" if delta <= -2.0 else "range_neutral"
    elif price_impulse <= -0.75 and rar_slope > 0:
        phase = "selloff_repair"
    elif price_impulse >= 0.75 and rar_slope < 0:
        phase = "rebound_pressure"
    elif scores["long"] > scores["short"]:
        phase = "trend_up"
    elif scores["short"] > scores["long"]:
        phase = "trend_down"
    else:
        phase = "undetermined"

    return {
        "market_phase": phase,
        "range_active": range_active,
        "box_low": box_low,
        "box_high": box_high,
        "box_ratio": box_ratio,
        "box_position": box_position,
        "range_cluster": str(range_lock.get("cluster", "")),
        "accepted_breakout": str(
            range_lock.get("accepted_breakout")
            or auto_range.get("accepted_breakout")
            or "none"
        ),
        "ict_ob_coexist": bool(ict.get("coexist", False)),
        "ict_ob_source": str(ict.get("source", "none")),
        "ict_bullish_active": bool(ict.get("bullish_active", False)),
        "ict_bearish_active": bool(ict.get("bearish_active", False)),
        "ict_bullish_distance_atr": ict.get("bullish_distance_atr"),
        "ict_bearish_distance_atr": ict.get("bearish_distance_atr"),
        "ict_structure_event": ict_structure_event,
        "ict_structure_event_age": ict_structure_age,
        "liquidity_bars_since": liq.get("bars_since_sweep"),
        "premium_discount": premium_discount,
        "fibonacci_trend": fib_direction,
        "in_ote": bool(fibonacci.get("in_ote", False)),
        "killzones": list((aux.get("killzone") or {}).get("active", [])) if isinstance(aux.get("killzone"), dict) else [],
        "orderflow_source": str(volume_flow.get("source", "none")),
        "is_true_orderflow": bool(volume_flow.get("is_true_orderflow", False)),
        "chart_framework_active": bool(
            str(ict.get("source", "none")) in {"luxalgo_pine_reimplementation", "explicit_feed"}
            or bool(auto_range)
            or bool(sweep_ctx)
            or bool(delta)
            or bool(volume_flow)
        ),
        "evidence_bundle_keys": sorted(
            k for k, v in evidence_bundle.items() if isinstance(v, dict) and v
        ),
        "scores": scores,
        "evidence": evidence,
        "price": close,
        "atr": atr,
        "price_impulse": price_impulse,
        "long_extension_atr": round(long_extension_atr, 3),
        "short_extension_atr": round(short_extension_atr, 3),
    }


def _bars_between(current_open_time: int, previous_open_time: Any) -> int | None:
    if previous_open_time in (None, ""):
        return None
    try:
        previous = int(previous_open_time)
    except (TypeError, ValueError):
        return None
    delta = current_open_time - previous
    if delta < 0:
        return None
    return int(delta // 3_600_000) if current_open_time > 10_000_000_000 else int(delta)


def assess_trial_candidate(
    direction: str,
    alert_type: str,
    zone: tuple[float, float],
    invalid_level: float,
    latest: dict[str, Any],
    prev2_close: float,
    zone_source: str,
    interaction: str,
    trial_context: dict[str, Any],
    observation_state: dict[str, Any] | None = None,
    current_bar: int | None = None,
) -> dict[str, Any]:
    """Score a formal trial and apply only location/risk/context hard blocks."""

    cfg = TREND_ENGINE_CONFIG["trial_decision"]
    observation_state = observation_state or {}
    side = "long" if direction == "long" else "short"
    opposite = "short" if side == "long" else "long"
    close = _f(latest.get("close"))
    open_ = _f(latest.get("open"), close)
    high = _f(latest.get("high"), close)
    low = _f(latest.get("low"), close)
    atr = max(_f(latest.get("atr"), trial_context.get("atr", 1.0)), 1e-9)
    zone_low, zone_high = min(zone), max(zone)
    invalid = _f(invalid_level)

    score = _f(trial_context.get("scores", {}).get(side))
    opposite_score = _f(trial_context.get("scores", {}).get(opposite))
    reasons = list(trial_context.get("evidence", {}).get(side, []))
    hard_blocks: list[str] = []
    reaction_score = 0.0

    formal_reactions = {
        "LOWER_KEY_ZONE_RECLAIM",
        "UPPER_KEY_ZONE_REJECTION",
        "SECONDARY_CONFIRM_LOWER",
        "SECONDARY_CONFIRM_UPPER",
    }
    secondary_confirmation = alert_type in {"SECONDARY_CONFIRM_LOWER", "SECONDARY_CONFIRM_UPPER"}
    if alert_type in formal_reactions:
        reaction_score += 3.5
        reasons.append("confirmed_zone_reaction:+3.50")
    elif interaction in {"reclaimed_above", "rejected_below"}:
        reaction_score += 2.5
        reasons.append("zone_accept_reject:+2.50")

    if (side == "long" and close > open_) or (side == "short" and close < open_):
        reaction_score += 0.75
        reasons.append("candle_support:+0.75")

    candle_range = max(high - low, 1e-9)
    if side == "long" and (min(open_, close) - low) / candle_range >= 0.35:
        reaction_score += 0.75
        reasons.append("lower_wick_reaction:+0.75")
    if side == "short" and (high - max(open_, close)) / candle_range >= 0.35:
        reaction_score += 0.75
        reasons.append("upper_wick_reaction:+0.75")

    if (side == "long" and zone_source == "ict_plus_ob") or (side == "short" and zone_source == "ict_minus_ob"):
        reaction_score += 1.5
        reasons.append("matching_ict_ob:+1.50")
    elif zone_source in {"fvg_zone", "fvg_volume_profile"}:
        reaction_score += 0.75
        reasons.append("matching_fvg:+0.75")
    elif zone_source == "fibonacci_ote":
        reaction_score += 1.0
        reasons.append("matching_ote:+1.00")
    elif zone_source in {"high_volume_support", "high_volume_resistance"}:
        reaction_score += 0.75
        reasons.append("matching_volume_pivot:+0.75")

    score += reaction_score
    direction_advantage = score - opposite_score

    if side == "long":
        distance_from_zone = max(0.0, close - zone_high)
        risk_distance = close - invalid
    else:
        distance_from_zone = max(0.0, zone_low - close)
        risk_distance = invalid - close

    zone_chase_atr = distance_from_zone / atr
    risk_atr = risk_distance / atr
    risk_pct = risk_distance / max(abs(close), 1e-9)
    price_impulse = (close - float(prev2_close)) / atr

    if risk_distance <= 0:
        hard_blocks.append("invalid_risk_side")
    if risk_atr > float(cfg.get("max_risk_atr", 2.4)) or risk_pct > float(cfg.get("max_risk_pct", 0.018)):
        hard_blocks.append("risk_too_wide")
    if zone_chase_atr > float(cfg.get("max_zone_chase_atr", 1.0)) and (
        (side == "long" and price_impulse > 0.65) or (side == "short" and price_impulse < -0.65)
    ):
        hard_blocks.append("late_chase")

    accepted_breakout = str(trial_context.get("accepted_breakout", "none"))
    breakout_matches = (side == "long" and accepted_breakout == "up") or (side == "short" and accepted_breakout == "down")
    box_position = str(trial_context.get("box_position", "unknown"))
    has_reference_box = trial_context.get("box_low") is not None and trial_context.get("box_high") is not None
    if has_reference_box and not breakout_matches:
        if (side == "long" and box_position == "upper_edge") or (side == "short" and box_position == "lower_edge"):
            hard_blocks.append("wrong_range_edge")

    if trial_context.get("range_active") and not breakout_matches:
        box_low = trial_context.get("box_low")
        box_high = trial_context.get("box_high")
        if box_low is not None and box_high is not None and risk_distance > 0:
            reward = max(0.0, _f(box_high) - close) if side == "long" else max(0.0, close - _f(box_low))
            reward_risk = reward / risk_distance
            if reward_risk < float(cfg.get("min_range_reward_risk", 0.8)):
                hard_blocks.append("poor_range_reward_risk")
        else:
            reward_risk = None
    else:
        reward_risk = None

    reason_blob = " ".join(reasons)
    matching_fresh_event = (
        (side == "long" and ("sellside_sweep_reclaim" in reason_blob or "sweep_sell_side_reclaim" in reason_blob))
        or (side == "short" and ("buyside_sweep_reject" in reason_blob or "sweep_buy_side_reject" in reason_blob))
        or breakout_matches
    )
    bull_dist = trial_context.get("ict_bullish_distance_atr")
    bear_dist = trial_context.get("ict_bearish_distance_atr")
    reason_text = " ".join(reasons)
    fresh_structure_matches = (
        side == "long"
        and any(token in reason_text for token in ("fresh_bullish_mss", "fresh_bullish_bos"))
    ) or (
        side == "short"
        and any(token in reason_text for token in ("fresh_bearish_mss", "fresh_bearish_bos"))
    )
    rar_aligned = (side == "long" and "rar_turn_up" in reason_text) or (side == "short" and "rar_turn_down" in reason_text)
    # Inertial / dual-log peeled; evidence helpers + core-levels are optional aux alignment.
    evidence_aux_aligned = any(
        token in reason_text
        for token in (
            "sweep_sell_side_reclaim" if side == "long" else "sweep_buy_side_reject",
            "range_reclaim_after_break_down" if side == "long" else "range_reclaim_after_break_up",
            "imbalance_inverted_support" if side == "long" else "imbalance_inverted_resistance",
            "profile_node_bull" if side == "long" else "profile_node_bear",
            "core_levels_reclaim_50" if side == "long" else "core_levels_loss_50",
            "evidence_confluence",
        )
    )
    matching_distance = bull_dist if side == "long" else bear_dist
    near_matching_ict_ob = matching_distance is not None and _f(matching_distance, 99.0) <= 0.35
    structure_aligned = any(
        token in reason_text
        for token in (
            "msb_bull" if side == "long" else "msb_bear",
            "ict_structure_bull" if side == "long" else "ict_structure_bear",
            "fibonacci_bull_swing" if side == "long" else "fibonacci_bear_swing",
        )
    )
    volume_catalyst = any(
        token in reason_text
        for token in (
            "volume_proxy_downside_stop_run_reclaim" if side == "long" else "volume_proxy_upside_stop_run_reject",
            "volume_accepted_breakout_up" if side == "long" else "volume_accepted_breakout_down",
            "sell_absorption_proxy" if side == "long" else "buy_absorption_proxy",
        )
    )
    # Inertial peeled: ICT proximity + RAR is enough; evidence / core-levels also qualify.
    auxiliary_reversal = (
        near_matching_ict_ob and rar_aligned
    ) or (
        structure_aligned and (rar_aligned or evidence_aux_aligned)
    ) or (
        near_matching_ict_ob and evidence_aux_aligned
    )
    directional_catalyst = bool(matching_fresh_event or fresh_structure_matches or volume_catalyst or auxiliary_reversal)
    # The pending-confirmation engine separately requires a real post-trial
    # push out of the parent zone.  That push is new directional information;
    # demanding another sweep/MSS on the same candle would silently disable
    # otherwise valid secondary confirmations.
    effective_directional_catalyst = bool(directional_catalyst or secondary_confirmation)
    recent_extension_atr = _f(
        trial_context.get("long_extension_atr") if side == "long" else trial_context.get("short_extension_atr")
    )
    if (
        recent_extension_atr > float(cfg.get("max_recent_extension_atr", 2.3))
        and zone_chase_atr > 0.20
        and not matching_fresh_event
    ):
        hard_blocks.append("missed_early_window")
    if (
        side == "short"
        and trial_context.get("ict_bullish_active")
        and not trial_context.get("ict_bearish_active")
        and bull_dist is not None
        and _f(bull_dist, 99.0) <= 0.20
        and not matching_fresh_event
    ):
        hard_blocks.append("short_into_active_ict_plus_ob")
    if (
        side == "long"
        and trial_context.get("ict_bearish_active")
        and not trial_context.get("ict_bullish_active")
        and bear_dist is not None
        and _f(bear_dist, 99.0) <= 0.20
        and not matching_fresh_event
    ):
        hard_blocks.append("long_into_active_ict_minus_ob")

    if trial_context.get("ict_ob_coexist") and not effective_directional_catalyst:
        hard_blocks.append("ict_coexist_without_fresh_directional_evidence")

    if trial_context.get("chart_framework_active") and not effective_directional_catalyst:
        hard_blocks.append("formal_without_directional_catalyst")

    if opposite_score - score >= float(cfg.get("opposite_conflict_margin", 2.5)):
        hard_blocks.append("opposite_structure_dominates")
    current_formal_side = "lower" if side == "long" else "upper"
    previous_formal_side = str(observation_state.get("last_formal_side", ""))
    current_box_low = trial_context.get("box_low")
    current_box_high = trial_context.get("box_high")
    previous_box_low = observation_state.get("last_formal_box_low")
    previous_box_high = observation_state.get("last_formal_box_high")
    same_box = False
    if None not in {current_box_low, current_box_high, previous_box_low, previous_box_high}:
        current_low, current_high = _f(current_box_low), _f(current_box_high)
        previous_low, previous_high = _f(previous_box_low), _f(previous_box_high)
        overlap = max(0.0, min(current_high, previous_high) - max(current_low, previous_low))
        minimum_width = max(min(current_high - current_low, previous_high - previous_low), 1e-9)
        same_box = overlap / minimum_width >= 0.60
    elif observation_state.get("last_formal_range_cluster"):
        same_box = observation_state.get("last_formal_range_cluster") == trial_context.get("range_cluster")
    bars_since_flip = _bars_between(int(current_bar), observation_state.get("last_formal_open_time")) if current_bar is not None else None
    new_event_now = bool(
        breakout_matches
        or fresh_structure_matches
        or (
            matching_fresh_event
            and trial_context.get("liquidity_bars_since") is not None
            and int(trial_context.get("liquidity_bars_since")) == 0
        )
    )
    if (
        same_box
        and previous_formal_side == current_formal_side
        and bars_since_flip is not None
        and bars_since_flip <= int(cfg.get("same_side_formal_cooldown_bars", 12))
        and not new_event_now
        and not secondary_confirmation
    ):
        hard_blocks.append("same_box_same_side_cooldown_without_new_information")
    if (
        same_box
        and previous_formal_side in {"lower", "upper"}
        and previous_formal_side != current_formal_side
        and bars_since_flip is not None
        and bars_since_flip < int(cfg.get("opposite_flip_cooldown_bars", 6))
        and not matching_fresh_event
    ):
        hard_blocks.append("same_box_opposite_flip_without_new_information")

    minimum = float(cfg.get("formal_min_score", 7.0))
    if trial_context.get("range_active") and box_position == "middle" and not breakout_matches:
        minimum = float(cfg.get("range_mid_min_score", 10.0))

    allow_formal = (
        not hard_blocks
        and score >= minimum
        and direction_advantage >= float(cfg.get("direction_advantage_min", 1.0))
    )
    early_evidence = reaction_score >= 1.5 and zone_chase_atr <= 0.35
    promote_early = bool(
        allow_formal
        and alert_type not in formal_reactions
        and early_evidence
        and score >= float(cfg.get("early_trial_min_score", 8.0))
    )

    return {
        "allow_formal": allow_formal,
        "promote_early": promote_early,
        "score": round(score, 3),
        "opposite_score": round(opposite_score, 3),
        "direction_advantage": round(direction_advantage, 3),
        "minimum_score": minimum,
        "reaction_score": round(reaction_score, 3),
        "hard_blocks": hard_blocks,
        "reasons": reasons,
        "zone_chase_atr": round(zone_chase_atr, 3),
        "risk_atr": round(risk_atr, 3),
        "risk_pct": round(risk_pct, 5),
        "reward_risk": round(reward_risk, 3) if reward_risk is not None else None,
        "recent_extension_atr": round(recent_extension_atr, 3),
        "market_phase": trial_context.get("market_phase", "undetermined"),
        "box_position": box_position,
        "ict_ob_coexist": bool(trial_context.get("ict_ob_coexist", False)),
        "directional_catalyst": effective_directional_catalyst,
    }
