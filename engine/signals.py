from __future__ import annotations

from typing import Any

from engine.structure import (
    detect_recent_equal_levels,
    detect_recent_fvg_fill,
    detect_recent_liquidity_sweep,
    detect_near_pivot_level,
    latest_structure_event,
)

SIGNAL_CLASS = {
    "A_LONG": 1,
    "A_SHORT": 1,
    "B_PULLBACK_LONG": 2,
    "B_PULLBACK_SHORT": 2,
    "C_LEFT_LONG": 3,
    "C_LEFT_SHORT": 3,
    "X_BREAKOUT_LONG": 4,
    "X_BREAKOUT_SHORT": 4,
}


def _float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _atr(k: dict) -> float:
    return max(_float(k.get("atr"), 0.0), abs(_float(k.get("close"), 0.0)) * 0.0012, 1e-9)


def _count(*conds: bool) -> int:
    return sum(bool(c) for c in conds)


def _body_size(k: dict) -> float:
    return abs(_float(k.get("close")) - _float(k.get("open")))


def _range_size(k: dict) -> float:
    return max(_float(k.get("high")) - _float(k.get("low")), 1e-9)


def _body_ratio(k: dict) -> float:
    return _body_size(k) / _range_size(k)


def _upper_wick(k: dict) -> float:
    return _float(k.get("high")) - max(_float(k.get("open")), _float(k.get("close")))


def _lower_wick(k: dict) -> float:
    return min(_float(k.get("open")), _float(k.get("close"))) - _float(k.get("low"))


def _momentum_up(k: dict, prev: dict | None = None) -> bool:
    prev_hist = _float(prev.get("cm_hist"), 0.0) if prev else _float(k.get("cm_hist"), 0.0)
    return bool(k.get("cm_macd_above_signal")) and (
        bool(k.get("cm_hist_up")) or _float(k.get("cm_hist"), 0.0) >= prev_hist
    )


def _momentum_down(k: dict, prev: dict | None = None) -> bool:
    prev_hist = _float(prev.get("cm_hist"), 0.0) if prev else _float(k.get("cm_hist"), 0.0)
    return (not bool(k.get("cm_macd_above_signal"))) and (
        bool(k.get("cm_hist_down")) or _float(k.get("cm_hist"), 0.0) <= prev_hist
    )


def _ema_alignment(k: dict, direction: str) -> str:
    close = _float(k.get("close"))
    ema20 = _float(k.get("ema20"))
    ema120 = _float(k.get("ema120"))
    ema169 = _float(k.get("ema169"))
    if direction == "long":
        if close >= ema20 >= ema120 and ema20 >= ema169:
            return "supportive"
        if close >= ema20:
            return "mixed"
        return "opposing"
    if close <= ema20 <= ema120 and ema20 <= ema169:
        return "supportive"
    if close <= ema20:
        return "mixed"
    return "opposing"


def _tai_heat(k: dict) -> str:
    tai = _float(k.get("tai_value"), 0.0)
    p20 = _float(k.get("tai_p20"), 0.0)
    p40 = _float(k.get("tai_p40"), 0.0)
    p60 = _float(k.get("tai_p60"), 0.0)
    p80 = _float(k.get("tai_p80"), 0.0)
    if tai <= p20:
        return "cold"
    if tai <= p40:
        return "cool"
    if tai <= p60:
        return "neutral"
    if tai <= p80:
        return "warm"
    return "hot"


def _heat_order(heat: str) -> int:
    return {"cold": 0, "cool": 1, "neutral": 2, "warm": 3, "hot": 4}.get(heat, 2)


def _cross_tf_heat_profile(k_15m: dict, k_1h: dict, k_4h: dict) -> dict[str, Any]:
    heat_15m = _tai_heat(k_15m)
    heat_1h = _tai_heat(k_1h)
    heat_4h = _tai_heat(k_4h)

    orders = [_heat_order(heat_15m), _heat_order(heat_1h), _heat_order(heat_4h)]
    avg_order = sum(orders) / 3.0
    coldish = sum(1 for x in orders if x <= 1)
    warmish = sum(1 for x in orders if x >= 3)

    tai_1h = _float(k_1h.get("tai_value"), 0.0)
    tai_1h_prev = _float(k_1h.get("tai_prev"), tai_1h)
    tai_1h_p20 = _float(k_1h.get("tai_p20"), 0.0)
    tai_15m = _float(k_15m.get("tai_value"), 0.0)
    tai_15m_prev = _float(k_15m.get("tai_prev"), tai_15m)

    h1_rising = bool(k_1h.get("tai_rising")) or tai_1h > tai_1h_prev
    m15_rising = bool(k_15m.get("tai_rising")) or tai_15m > tai_15m_prev

    frozen_eligible = tai_1h <= tai_1h_p20
    freeze_mode = frozen_eligible and coldish == 3 and avg_order <= 0.9 and not h1_rising

    if freeze_mode:
        budget = "frozen"
    elif coldish >= 2 or avg_order <= 1.45:
        budget = "restricted"
    elif warmish >= 2 and avg_order >= 2.7:
        budget = "expanded"
    else:
        budget = "normal"

    return {
        "tai_heat_15m": heat_15m,
        "tai_heat_1h": heat_1h,
        "tai_heat_4h": heat_4h,
        "tai_budget_mode": budget,
        "freeze_mode": freeze_mode,
        "strict_low_heat": heat_1h in {"cold", "cool"},
        "h1_tai_rising": h1_rising,
        "m15_tai_rising": m15_rising,
        "allow_low_heat_probe": h1_rising or m15_rising,
    }


def _structure_context(klines: list[dict]) -> dict[str, Any]:
    eq = detect_recent_equal_levels(klines)
    return {
        "bos_up": latest_structure_event(klines, direction="up", kinds=("bos",), max_bars_ago=14),
        "bos_down": latest_structure_event(klines, direction="down", kinds=("bos",), max_bars_ago=14),
        "mss_up": latest_structure_event(klines, direction="up", kinds=("mss",), max_bars_ago=18),
        "mss_down": latest_structure_event(klines, direction="down", kinds=("mss",), max_bars_ago=18),
        "bull_fvg": detect_recent_fvg_fill(klines, "bull"),
        "bear_fvg": detect_recent_fvg_fill(klines, "bear"),
        "bull_sweep": detect_recent_liquidity_sweep(klines, "bull"),
        "bear_sweep": detect_recent_liquidity_sweep(klines, "bear"),
        "near_bull": detect_near_pivot_level(klines, "bull"),
        "near_bear": detect_near_pivot_level(klines, "bear"),
        "eqh": eq.get("eqh"),
        "eql": eq.get("eql"),
    }


def _background_4h_direction(klines_4h: list[dict]) -> str:
    latest, prev = klines_4h[-1], klines_4h[-2]
    ctx = _structure_context(klines_4h)

    bull_score = _count(
        bool(ctx["bos_up"] or ctx["mss_up"]),
        _ema_alignment(latest, "long") != "opposing",
        _momentum_up(latest, prev),
        bool(ctx["bull_fvg"] or ctx["bull_sweep"] or ctx["near_bull"] or ctx["eql"]),
    )
    bear_score = _count(
        bool(ctx["bos_down"] or ctx["mss_down"]),
        _ema_alignment(latest, "short") != "opposing",
        _momentum_down(latest, prev),
        bool(ctx["bear_fvg"] or ctx["bear_sweep"] or ctx["near_bear"] or ctx["eqh"]),
    )

    if bull_score >= 4 and bear_score <= 1:
        return "bull"
    if bear_score >= 4 and bull_score <= 1:
        return "bear"
    if bull_score > bear_score:
        return "lean_bull"
    if bear_score > bull_score:
        return "lean_bear"
    return "neutral"


def _trigger_15m_state(direction: str, latest: dict, prev: dict, ctx_15m: dict[str, Any]) -> str:
    vol_ratio = _float(latest.get("volume")) / max(_float(latest.get("vol_sma20")), 1e-9)
    close = _float(latest.get("close"))
    prev_close = _float(prev.get("close"))

    if direction == "long":
        score = _count(
            bool(ctx_15m["bos_up"] or ctx_15m["mss_up"]),
            bool(latest.get("fl_buy_signal")) or _float(latest.get("fl_trend")) > 0,
            _momentum_up(latest, prev),
            close >= prev_close,
            bool(ctx_15m["bull_sweep"] or ctx_15m["bull_fvg"]),
        )
        if score >= 4 and vol_ratio >= 1.03:
            return "confirm_long"
        if score >= 2:
            return "repairing_long"
        if score >= 1:
            return "probing_long"
        return "idle"

    score = _count(
        bool(ctx_15m["bos_down"] or ctx_15m["mss_down"]),
        bool(latest.get("fl_sell_signal")) or _float(latest.get("fl_trend")) < 0,
        _momentum_down(latest, prev),
        close <= prev_close,
        bool(ctx_15m["bear_sweep"] or ctx_15m["bear_fvg"]),
    )
    if score >= 4 and vol_ratio >= 1.03:
        return "confirm_short"
    if score >= 2:
        return "repairing_short"
    if score >= 1:
        return "probing_short"
    return "idle"


def _long_failure_pressure(
    latest_1h: dict,
    prev_1h: dict,
    ctx_1h: dict[str, Any],
    latest_15m: dict,
    prev_15m: dict,
    ctx_15m: dict[str, Any],
) -> int:
    atr15 = _atr(latest_15m)
    close15 = _float(latest_15m.get("close"))
    ema20_15 = _float(latest_15m.get("ema20"))
    prev_close15 = _float(prev_15m.get("close"))
    high15 = _float(latest_15m.get("high"))

    return _count(
        bool(ctx_15m["bear_sweep"] or ctx_15m["eqh"] or ctx_1h["eqh"] or ctx_1h["near_bear"]),
        bool(ctx_15m["bos_down"] or ctx_15m["mss_down"]),
        _momentum_down(latest_15m, prev_15m),
        close15 < ema20_15,
        close15 < prev_close15,
        _upper_wick(latest_15m) >= atr15 * 0.18 and _body_ratio(latest_15m) < 0.55,
        (not _momentum_up(latest_1h, prev_1h)) and _momentum_down(latest_1h, prev_1h),
        high15 <= _float(prev_15m.get("high")) + atr15 * 0.08,
    )


def _short_failure_pressure(
    latest_1h: dict,
    prev_1h: dict,
    ctx_1h: dict[str, Any],
    latest_15m: dict,
    prev_15m: dict,
    ctx_15m: dict[str, Any],
) -> int:
    atr15 = _atr(latest_15m)
    close15 = _float(latest_15m.get("close"))
    ema20_15 = _float(latest_15m.get("ema20"))
    prev_close15 = _float(prev_15m.get("close"))
    low15 = _float(latest_15m.get("low"))

    return _count(
        bool(ctx_15m["bull_sweep"] or ctx_15m["eql"] or ctx_1h["eql"] or ctx_1h["near_bull"]),
        bool(ctx_15m["bos_up"] or ctx_15m["mss_up"]),
        _momentum_up(latest_15m, prev_15m),
        close15 > ema20_15,
        close15 > prev_close15,
        _lower_wick(latest_15m) >= atr15 * 0.18 and _body_ratio(latest_15m) < 0.55,
        (not _momentum_down(latest_1h, prev_1h)) and _momentum_up(latest_1h, prev_1h),
        low15 >= _float(prev_15m.get("low")) - atr15 * 0.08,
    )


def _direction_context(ctx: dict[str, Any], direction: str) -> bool:
    if direction == "long":
        return bool(ctx["bull_fvg"] or ctx["bull_sweep"] or ctx["near_bull"] or ctx["eql"])
    return bool(ctx["bear_fvg"] or ctx["bear_sweep"] or ctx["near_bear"] or ctx["eqh"])


def _early_warning(latest_15m: dict, direction: str) -> bool:
    if direction == "long":
        return bool(
            latest_15m.get("sss_bull_div")
            or latest_15m.get("sss_oversold_warning")
            or latest_15m.get("fl_buy_signal")
        )
    return bool(
        latest_15m.get("sss_bear_div")
        or latest_15m.get("sss_overbought_warning")
        or latest_15m.get("fl_sell_signal")
    )


def _state_candidate(
    direction: str,
    background_4h: str,
    latest_1h: dict,
    prev_1h: dict,
    ctx_1h: dict[str, Any],
    latest_15m: dict,
    prev_15m: dict,
    ctx_15m: dict[str, Any],
    trigger_long: str,
    trigger_short: str,
    heat_profile: dict[str, Any],
) -> tuple[str, int, list[str]]:
    support_ctx = _direction_context(ctx_1h, direction)
    trigger_state = trigger_long if direction == "long" else trigger_short
    ema_support = _ema_alignment(latest_1h, direction)
    background_support = background_4h in {"bull", "lean_bull"} if direction == "long" else background_4h in {"bear", "lean_bear"}
    momentum_ok = _momentum_up(latest_1h, prev_1h) if direction == "long" else _momentum_down(latest_1h, prev_1h)
    fail_pressure = _long_failure_pressure(latest_1h, prev_1h, ctx_1h, latest_15m, prev_15m, ctx_15m) if direction == "long" else _short_failure_pressure(latest_1h, prev_1h, ctx_1h, latest_15m, prev_15m, ctx_15m)
    struct_up = bool(ctx_1h["bos_up"] or ctx_1h["mss_up"]) if direction == "long" else bool(ctx_1h["bos_down"] or ctx_1h["mss_down"])
    basis: list[str] = []
    if struct_up:
        basis.append("smc_bos" if direction == "long" else "smc_bos_down")
    if support_ctx:
        basis.append("zone")
    if _early_warning(latest_15m, direction):
        basis.append("early_warning")

    drive_score = _count(
        background_support,
        struct_up,
        ema_support == "supportive",
        momentum_ok,
        trigger_state == f"confirm_{direction}",
    ) - max(0, fail_pressure - 1)

    repair_score = _count(
        background_4h != ("bear" if direction == "long" else "bull"),
        support_ctx,
        ema_support != "opposing",
        trigger_state in {f"confirm_{direction}", f"repairing_{direction}"},
        (_float(latest_15m.get("close")) >= _float(prev_15m.get("close"))) if direction == "long" else (_float(latest_15m.get("close")) <= _float(prev_15m.get("close"))),
    ) - fail_pressure

    probe_score = _count(
        support_ctx,
        trigger_state in {f"confirm_{direction}", f"repairing_{direction}", f"probing_{direction}"},
        _early_warning(latest_15m, direction),
        ema_support != "opposing",
    ) - max(0, fail_pressure - 2)

    restricted = heat_profile["tai_budget_mode"] in {"restricted", "frozen"}
    low_heat_probe_ok = heat_profile["allow_low_heat_probe"] and support_ctx and _early_warning(latest_15m, direction)

    if fail_pressure >= 4 and not low_heat_probe_ok:
        return "range_neutral", 0, [f"{direction}_failed_exit"]

    if drive_score >= 4 and fail_pressure <= 2:
        return (f"trend_drive_{direction}", drive_score, basis + ["trigger_confirm"])

    repair_threshold = 4 if restricted else 3
    if repair_score >= repair_threshold and fail_pressure <= (1 if restricted else 2):
        return (f"repair_{direction}", repair_score, basis + ["repair"])

    probe_threshold = 3 if restricted else 2
    if probe_score >= probe_threshold and (not restricted or low_heat_probe_ok):
        return (f"probe_{direction}", probe_score, basis + ["probe"])

    return "range_neutral", max(drive_score, repair_score, probe_score), basis


def _choose_state(
    background_4h: str,
    latest_1h: dict,
    prev_1h: dict,
    ctx_1h: dict[str, Any],
    latest_15m: dict,
    prev_15m: dict,
    ctx_15m: dict[str, Any],
    trigger_long: str,
    trigger_short: str,
    heat_profile: dict[str, Any],
) -> tuple[str, int, list[str]]:
    long_state, long_score, long_basis = _state_candidate(
        "long",
        background_4h,
        latest_1h,
        prev_1h,
        ctx_1h,
        latest_15m,
        prev_15m,
        ctx_15m,
        trigger_long,
        trigger_short,
        heat_profile,
    )
    short_state, short_score, short_basis = _state_candidate(
        "short",
        background_4h,
        latest_1h,
        prev_1h,
        ctx_1h,
        latest_15m,
        prev_15m,
        ctx_15m,
        trigger_long,
        trigger_short,
        heat_profile,
    )

    best_score = max(long_score, short_score)
    if best_score <= 1:
        return "range_neutral", best_score, []

    if long_state != "range_neutral" and short_state != "range_neutral" and abs(long_score - short_score) <= 1:
        return "range_neutral", best_score, ["dual_conflict"]

    if heat_profile["freeze_mode"] and best_score < 4:
        return "range_neutral", best_score, ["freeze_mode"]

    if heat_profile["strict_low_heat"] and best_score < 3:
        return "range_neutral", best_score, ["low_heat_no_lock"]

    if long_score > short_score:
        return long_state, long_score, long_basis
    if short_score > long_score:
        return short_state, short_score, short_basis
    return "range_neutral", best_score, []


def _phase_name_from_state(state_1h: str) -> str:
    if state_1h.startswith("trend_drive_"):
        return "continuation"
    if state_1h.startswith("repair_"):
        return "repair"
    if state_1h.startswith("probe_"):
        return "early"
    return "none"


def _state_to_signal(state_1h: str) -> tuple[str | None, str | None]:
    mapping = {
        "trend_drive_long": ("A_LONG", "long"),
        "trend_drive_short": ("A_SHORT", "short"),
        "repair_long": ("B_PULLBACK_LONG", "long"),
        "repair_short": ("B_PULLBACK_SHORT", "short"),
        "probe_long": ("C_LEFT_LONG", "long"),
        "probe_short": ("C_LEFT_SHORT", "short"),
    }
    return mapping.get(state_1h, (None, None))


def _h1_tai_bias_from_heat(heat_1h: str, state_1h: str) -> str:
    if state_1h.startswith("trend_drive_"):
        if heat_1h in {"warm", "hot"}:
            return "drive"
        if heat_1h == "neutral":
            return "support"
        return "flat"

    if state_1h.startswith("repair_"):
        if heat_1h in {"warm", "neutral"}:
            return "support"
        return "flat"

    if state_1h.startswith("probe_"):
        if heat_1h in {"warm", "hot"}:
            return "support"
        return "flat"

    return "flat"


def _h1_tai_slot_from_heat(heat_1h: str) -> str:
    return {
        "cold": "ice",
        "cool": "cool",
        "neutral": "mid",
        "warm": "warm",
        "hot": "hot",
    }.get(heat_1h, "mid")


def _phase_anchor(
    symbol: str,
    direction: str,
    state_1h: str,
    background_4h_direction: str,
    trigger_15m_state: str,
    heat_1h: str,
    structure_basis: list[str],
) -> str:
    phase_name = _phase_name_from_state(state_1h)
    trigger_bucket = "confirm"
    if trigger_15m_state.startswith("repairing_"):
        trigger_bucket = "repair"
    elif trigger_15m_state.startswith("probing_"):
        trigger_bucket = "probe"
    elif trigger_15m_state == "idle":
        trigger_bucket = "idle"
    basis_key = ",".join(sorted(structure_basis[:3])) or "none"
    return "|".join([symbol, direction, phase_name, background_4h_direction, trigger_bucket, heat_1h, basis_key])


def _signal_confidence(
    signal_name: str,
    direction: str,
    state_1h: str,
    candidate_score: int,
    trigger_15m_state: str,
    structure_basis: list[str],
    background_4h_direction: str,
    heat_profile: dict[str, Any],
) -> int:
    if signal_name.startswith("A_"):
        score = 68
    elif signal_name.startswith("B_"):
        score = 62
    elif signal_name.startswith("C_"):
        score = 54
    else:
        score = 55

    supportive_bg = (
        (direction == "long" and background_4h_direction in {"bull", "lean_bull"})
        or (direction == "short" and background_4h_direction in {"bear", "lean_bear"})
    )
    opposing_bg = (
        (direction == "long" and background_4h_direction in {"bear", "lean_bear"})
        or (direction == "short" and background_4h_direction in {"bull", "lean_bull"})
    )

    if supportive_bg:
        score += 6 if background_4h_direction in {"bull", "bear"} else 3
    elif opposing_bg:
        score -= 8 if background_4h_direction in {"bull", "bear"} else 5
    else:
        score -= 4

    if state_1h in {"trend_drive_long", "trend_drive_short"}:
        score += 8
    elif state_1h in {"repair_long", "repair_short"}:
        score += 5
    elif state_1h in {"probe_long", "probe_short"}:
        score += 2
    elif state_1h == "range_neutral":
        score -= 8

    if trigger_15m_state in {"confirm_long", "confirm_short"}:
        score += 6
    elif trigger_15m_state in {"repairing_long", "repairing_short"}:
        score += 2
    elif trigger_15m_state in {"probing_long", "probing_short"}:
        score -= 1
    else:
        score -= 4

    score += min(8, len(structure_basis) * 2)
    score += min(8, max(0, candidate_score - 2) * 2)

    budget = heat_profile["tai_budget_mode"]
    if budget == "restricted":
        score -= 10
    elif budget == "frozen":
        score -= 16

    if heat_profile["tai_heat_1h"] in {"cold", "cool"} and heat_profile["tai_heat_4h"] in {"cold", "cool"}:
        score -= 5

    if signal_name.startswith("A_"):
        score = max(62, min(88, score))
    elif signal_name.startswith("B_"):
        score = max(56, min(78, score))
    elif signal_name.startswith("C_"):
        score = max(48, min(68, score))
    else:
        score = max(48, min(62, score))

    return int(score)


def _signal_dict(
    name: str,
    symbol: str,
    direction: str,
    price: float,
    *,
    zone_low: float | None,
    zone_high: float | None,
    structure_basis: list[str],
    background_4h_direction: str,
    state_1h: str,
    trigger_15m_state: str,
    heat_profile: dict[str, Any],
    candidate_score: int,
) -> dict[str, Any]:
    rank = SIGNAL_CLASS[name]
    eta_map = {1: (15, 135), 2: (30, 180), 3: (45, 210)}
    eta_min, eta_max = eta_map.get(rank, (20, 120))

    heat_1h = heat_profile["tai_heat_1h"]
    phase_name = _phase_name_from_state(state_1h)
    phase_anchor = _phase_anchor(
        symbol=symbol,
        direction=direction,
        state_1h=state_1h,
        background_4h_direction=background_4h_direction,
        trigger_15m_state=trigger_15m_state,
        heat_1h=heat_1h,
        structure_basis=structure_basis,
    )
    h1_tai_bias = _h1_tai_bias_from_heat(heat_1h, state_1h)
    h1_tai_slot = _h1_tai_slot_from_heat(heat_1h)
    segment_id = f"{symbol}|15m|{state_1h}|{direction}|{heat_1h}"

    return {
        "signal": name,
        "symbol": symbol,
        "timeframe": "15m",
        "priority": rank,
        "direction": direction,
        "price": price,
        "trend_1h": state_1h,
        "status": "active" if rank <= 2 else "early",
        "zone_low": zone_low,
        "zone_high": zone_high,
        "structure_basis": structure_basis,
        "eta_min_minutes": eta_min,
        "eta_max_minutes": eta_max,
        "cooldown_seconds": {1: 45 * 60, 2: 60 * 60, 3: 90 * 60}.get(rank, 30 * 60),
        "phase_rank": {"continuation": 3, "repair": 2, "early": 1}.get(phase_name, 0),
        "phase_name": phase_name,
        "phase_context": f"{state_1h}|{background_4h_direction}|{trigger_15m_state}|{heat_1h}",
        "phase_anchor": phase_anchor,
        "trigger_state": trigger_15m_state,
        "bg_bias": background_4h_direction,
        "h1_tai_bias": h1_tai_bias,
        "h1_tai_slot": h1_tai_slot,
        "signature": f"{name}|{direction}|{round(zone_low or price)}-{round(zone_high or price)}|{heat_1h}",
        "background_4h_direction": background_4h_direction,
        "state_1h": state_1h,
        "trigger_15m_state": trigger_15m_state,
        "tai_heat_1h": heat_1h,
        "tai_heat_15m": heat_profile["tai_heat_15m"],
        "tai_heat_4h": heat_profile["tai_heat_4h"],
        "tai_budget_mode": heat_profile["tai_budget_mode"],
        "heat_restricted": heat_profile["tai_budget_mode"] in {"restricted", "frozen"},
        "freeze_mode": heat_profile["freeze_mode"],
        "segment_id": segment_id,
        "candidate_score": candidate_score,
        "confidence": _signal_confidence(
            name,
            direction,
            state_1h,
            candidate_score,
            trigger_15m_state,
            structure_basis,
            background_4h_direction,
            heat_profile,
        ),
    }


def _build_zone(direction: str, signal_name: str, latest_15m: dict) -> tuple[float, float]:
    price = _float(latest_15m.get("close"))
    ema10 = _float(latest_15m.get("ema10"))
    ema20 = _float(latest_15m.get("ema20"))
    atr15 = _atr(latest_15m)
    if signal_name.startswith("A_"):
        if direction == "long":
            return (
                round(min(ema10, ema20, price - atr15 * 0.25), 2),
                round(max(ema10, ema20, price - atr15 * 0.03), 2),
            )
        return (
            round(min(ema10, ema20, price + atr15 * 0.03), 2),
            round(max(ema10, ema20, price + atr15 * 0.25), 2),
        )
    if signal_name.startswith("B_"):
        if direction == "long":
            return (
                round(min(ema10, ema20, price - atr15 * 0.35), 2),
                round(max(ema10, ema20, price + atr15 * 0.05), 2),
            )
        return (
            round(min(ema10, ema20, price - atr15 * 0.05), 2),
            round(max(ema10, ema20, price + atr15 * 0.35), 2),
        )
    if direction == "long":
        return (
            round(min(ema10, ema20, price - atr15 * 0.45), 2),
            round(max(ema10, ema20, price + atr15 * 0.08), 2),
        )
    return (
        round(min(ema10, ema20, price - atr15 * 0.08), 2),
        round(max(ema10, ema20, price + atr15 * 0.45), 2),
    )


def _candidate_allowed(signal_name: str, state_1h: str, direction: str, trigger_state: str, heat_profile: dict[str, Any], candidate_score: int, structure_basis: list[str], latest_15m: dict) -> bool:
    low_heat = heat_profile["strict_low_heat"]
    allow_probe = heat_profile["allow_low_heat_probe"]
    early_warning = _early_warning(latest_15m, direction)

    if signal_name.startswith("A_"):
        if not state_1h.startswith("trend_drive_"):
            return False
        if trigger_state != f"confirm_{direction}":
            return False
        if low_heat and not (allow_probe and candidate_score >= 5):
            return False
        return True

    if signal_name.startswith("B_"):
        if not state_1h.startswith("repair_"):
            return False
        if trigger_state not in {f"confirm_{direction}", f"repairing_{direction}"}:
            return False
        if low_heat and not (candidate_score >= 4 and allow_probe and len(structure_basis) >= 2):
            return False
        return True

    if signal_name.startswith("C_"):
        if not (state_1h.startswith("probe_") or state_1h == "range_neutral"):
            return False
        if low_heat and not (allow_probe and early_warning and candidate_score >= 2):
            return False
        if state_1h == "range_neutral":
            return early_warning and len(structure_basis) >= 2
        return True

    return True


def detect_signals(
    symbol: str,
    klines_1d: list[dict],
    klines_4h: list[dict],
    klines_1h: list[dict],
    klines_15m: list[dict],
) -> dict[str, Any]:
    if min(len(klines_1d), len(klines_4h), len(klines_1h), len(klines_15m)) < 50:
        return {
            "signals": [],
            "near_miss_signals": [],
            "background_4h_direction": "neutral",
            "state_1h": "range_neutral",
            "trigger_15m_state": "idle",
            "tai_budget_mode": "normal",
            "tai_heat_1h": "neutral",
            "tai_heat_4h": "neutral",
            "blocked_reasons": ["insufficient_data"],
        }

    latest_4h = klines_4h[-1]
    latest_1h, prev_1h = klines_1h[-1], klines_1h[-2]
    latest_15m, prev_15m = klines_15m[-1], klines_15m[-2]

    ctx_1h = _structure_context(klines_1h)
    ctx_15m = _structure_context(klines_15m)

    background_4h = _background_4h_direction(klines_4h)
    trigger_long = _trigger_15m_state("long", latest_15m, prev_15m, ctx_15m)
    trigger_short = _trigger_15m_state("short", latest_15m, prev_15m, ctx_15m)
    heat_profile = _cross_tf_heat_profile(latest_15m, latest_1h, latest_4h)

    state_1h, candidate_score, state_basis = _choose_state(
        background_4h,
        latest_1h,
        prev_1h,
        ctx_1h,
        latest_15m,
        prev_15m,
        ctx_15m,
        trigger_long,
        trigger_short,
        heat_profile,
    )

    signal_name, direction = _state_to_signal(state_1h)
    if not signal_name or not direction:
        blocked = ["range_neutral"]
        if heat_profile["tai_budget_mode"] == "restricted":
            blocked.append("heat_restricted")
        if heat_profile["tai_budget_mode"] == "frozen":
            blocked.append("heat_frozen")
        # rare high quality range-neutral C
        rare_candidates = []
        for rare_name, rare_direction, rare_trigger in (
            ("C_LEFT_LONG", "long", trigger_long),
            ("C_LEFT_SHORT", "short", trigger_short),
        ):
            rare_basis = []
            if _direction_context(ctx_1h, rare_direction):
                rare_basis.append("zone")
            if _early_warning(latest_15m, rare_direction):
                rare_basis.append("early_warning")
            rare_score = _count(
                _direction_context(ctx_1h, rare_direction),
                rare_trigger in {f"probing_{rare_direction}", f"repairing_{rare_direction}", f"confirm_{rare_direction}"},
                _early_warning(latest_15m, rare_direction),
            )
            if _candidate_allowed(
                rare_name,
                "range_neutral",
                rare_direction,
                rare_trigger,
                heat_profile,
                rare_score,
                rare_basis,
                latest_15m,
            ):
                zone_low, zone_high = _build_zone(rare_direction, rare_name, latest_15m)
                rare_candidates.append(
                    _signal_dict(
                        name=rare_name,
                        symbol=symbol,
                        direction=rare_direction,
                        price=round(_float(latest_15m.get("close")), 2),
                        zone_low=zone_low,
                        zone_high=zone_high,
                        structure_basis=rare_basis,
                        background_4h_direction=background_4h,
                        state_1h="range_neutral",
                        trigger_15m_state=rare_trigger,
                        heat_profile=heat_profile,
                        candidate_score=rare_score,
                    )
                )
        rare_candidates.sort(key=lambda x: x.get("confidence", 0), reverse=True)
        return {
            "signals": rare_candidates[:1],
            "near_miss_signals": [],
            "background_4h_direction": background_4h,
            "state_1h": "range_neutral",
            "trigger_15m_state": "idle",
            "tai_budget_mode": heat_profile["tai_budget_mode"],
            "tai_heat_1h": heat_profile["tai_heat_1h"],
            "tai_heat_4h": heat_profile["tai_heat_4h"],
            "blocked_reasons": blocked if not rare_candidates else [],
        }

    trigger_display = trigger_long if direction == "long" else trigger_short
    allowed = _candidate_allowed(
        signal_name,
        state_1h,
        direction,
        trigger_display,
        heat_profile,
        candidate_score,
        state_basis,
        latest_15m,
    )
    if not allowed:
        return {
            "signals": [],
            "near_miss_signals": [],
            "background_4h_direction": background_4h,
            "state_1h": state_1h,
            "trigger_15m_state": trigger_display,
            "tai_budget_mode": heat_profile["tai_budget_mode"],
            "tai_heat_1h": heat_profile["tai_heat_1h"],
            "tai_heat_4h": heat_profile["tai_heat_4h"],
            "blocked_reasons": [f"{signal_name.lower()}_not_publishable"],
        }

    zone_low, zone_high = _build_zone(direction, signal_name, latest_15m)
    signal = _signal_dict(
        name=signal_name,
        symbol=symbol,
        direction=direction,
        price=round(_float(latest_15m.get("close")), 2),
        zone_low=zone_low,
        zone_high=zone_high,
        structure_basis=state_basis,
        background_4h_direction=background_4h,
        state_1h=state_1h,
        trigger_15m_state=trigger_display,
        heat_profile=heat_profile,
        candidate_score=candidate_score,
    )

    return {
        "signals": [signal],
        "near_miss_signals": [],
        "background_4h_direction": background_4h,
        "state_1h": state_1h,
        "trigger_15m_state": trigger_display,
        "tai_budget_mode": heat_profile["tai_budget_mode"],
        "tai_heat_1h": heat_profile["tai_heat_1h"],
        "tai_heat_4h": heat_profile["tai_heat_4h"],
        "blocked_reasons": [],
    }


# compatibility with older tests / helpers
def _abc_confidence(
    signal_name: str,
    direction: str,
    background_4h_direction: str,
    phase_name: str,
    trigger_state_hint: str,
    structure_basis: list[str],
) -> int:
    trigger_state = {
        ("continuation", "explosive"): f"confirm_{direction}",
        ("repair", "ready"): f"repairing_{direction}",
        ("early", "probe"): f"probing_{direction}",
    }.get((phase_name, trigger_state_hint), "idle")
    heat_profile = {
        "tai_budget_mode": "normal",
        "tai_heat_1h": "neutral",
        "tai_heat_4h": "neutral",
    }
    state_1h = {
        "A_LONG": "trend_drive_long",
        "A_SHORT": "trend_drive_short",
        "B_PULLBACK_LONG": "repair_long",
        "B_PULLBACK_SHORT": "repair_short",
        "C_LEFT_LONG": "probe_long",
        "C_LEFT_SHORT": "probe_short",
    }.get(signal_name, "range_neutral")
    return _signal_confidence(
        signal_name,
        direction,
        state_1h,
        candidate_score=max(2, len(structure_basis)),
        trigger_15m_state=trigger_state,
        structure_basis=structure_basis,
        background_4h_direction=background_4h_direction,
        heat_profile=heat_profile,
    )
