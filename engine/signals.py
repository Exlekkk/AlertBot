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
    ema10 = _float(k.get("ema10"))
    ema20 = _float(k.get("ema20"))
    ema120 = _float(k.get("ema120"))
    ema169 = _float(k.get("ema169"))
    if direction == "long":
        if close >= ema10 >= ema20 and ema20 >= ema120 and ema20 >= ema169:
            return "supportive"
        if close >= ema20:
            return "mixed"
        return "opposing"
    if close <= ema10 <= ema20 and ema20 <= ema120 and ema20 <= ema169:
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
    coldish = sum(1 for x in orders if x <= 1)
    warmish = sum(1 for x in orders if x >= 3)
    avg_order = sum(orders) / 3.0

    freeze_mode = coldish == 3 or (coldish >= 2 and avg_order <= 1.0)
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
    }


def _structure_context(klines: list[dict]) -> dict[str, Any]:
    eq = detect_recent_equal_levels(klines)
    return {
        "bos_up": latest_structure_event(klines, direction="up", kinds=("bos",), max_bars_ago=12),
        "bos_down": latest_structure_event(klines, direction="down", kinds=("bos",), max_bars_ago=12),
        "mss_up": latest_structure_event(klines, direction="up", kinds=("mss",), max_bars_ago=16),
        "mss_down": latest_structure_event(klines, direction="down", kinds=("mss",), max_bars_ago=16),
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
    else:
        score = _count(
            bool(ctx_15m["bos_down"] or ctx_15m["mss_down"]),
            bool(latest.get("fl_sell_signal")) or _float(latest.get("fl_trend")) < 0,
            _momentum_down(latest, prev),
            close <= prev_close,
            bool(ctx_15m["bear_sweep"] or ctx_15m["bear_fvg"]),
        )
    if score >= 4 and vol_ratio >= 1.10:
        return f"confirm_{direction}"
    if score >= 2:
        return f"repairing_{direction}"
    if score >= 1:
        return f"probing_{direction}"
    return "idle"


def _state_candidate(direction: str, background_4h: str, latest_1h: dict, prev_1h: dict, ctx_1h: dict[str, Any], latest_15m: dict, prev_15m: dict, trigger_state: str) -> tuple[str, int, list[str]]:
    support_ctx = bool(ctx_1h["bull_fvg"] or ctx_1h["bull_sweep"] or ctx_1h["near_bull"] or ctx_1h["eql"])
    resist_ctx = bool(ctx_1h["bear_fvg"] or ctx_1h["bear_sweep"] or ctx_1h["near_bear"] or ctx_1h["eqh"])
    long_drive = _count(background_4h in {"bull", "lean_bull"}, bool(ctx_1h["bos_up"] or ctx_1h["mss_up"]), _ema_alignment(latest_1h, "long") == "supportive", _momentum_up(latest_1h, prev_1h), trigger_state == "confirm_long")
    short_drive = _count(background_4h in {"bear", "lean_bear"}, bool(ctx_1h["bos_down"] or ctx_1h["mss_down"]), _ema_alignment(latest_1h, "short") == "supportive", _momentum_down(latest_1h, prev_1h), trigger_state == "confirm_short")
    long_repair = _count(background_4h != "bear", support_ctx, _ema_alignment(latest_1h, "long") != "opposing", trigger_state in {"confirm_long", "repairing_long"}, _float(latest_15m.get("close")) >= _float(prev_15m.get("close")))
    short_repair = _count(background_4h != "bull", resist_ctx, _ema_alignment(latest_1h, "short") != "opposing", trigger_state in {"confirm_short", "repairing_short"}, _float(latest_15m.get("close")) <= _float(prev_15m.get("close")))
    long_probe = _count(support_ctx, trigger_state in {"confirm_long", "repairing_long", "probing_long"}, bool(latest_15m.get("sss_bull_div") or latest_15m.get("sss_oversold_warning") or latest_15m.get("fl_buy_signal")))
    short_probe = _count(resist_ctx, trigger_state in {"confirm_short", "repairing_short", "probing_short"}, bool(latest_15m.get("sss_bear_div") or latest_15m.get("sss_overbought_warning") or latest_15m.get("fl_sell_signal")))
    if direction == "long":
        if long_drive >= 4 and short_drive <= 1:
            return "trend_drive_long", long_drive, [x for x, ok in [("smc_bos_up", bool(ctx_1h["bos_up"])), ("ict_mss_up", bool(ctx_1h["mss_up"])), ("support_zone", support_ctx)] if ok]
        if long_repair >= 3 and short_drive <= 2:
            return "repair_long", long_repair, [x for x, ok in [("support_zone", support_ctx), ("trigger_repair", trigger_state in {"confirm_long", "repairing_long"}), ("ema_support", _ema_alignment(latest_1h, "long") != "opposing")] if ok]
        if long_probe >= 2:
            return "probe_long", long_probe, [x for x, ok in [("support_zone", support_ctx), ("early_warning", bool(latest_15m.get("sss_bull_div") or latest_15m.get("sss_oversold_warning"))), ("probing_trigger", trigger_state in {"probing_long", "repairing_long", "confirm_long"})] if ok]
        return "range_neutral", max(long_drive, long_repair, long_probe), []
    if short_drive >= 4 and long_drive <= 1:
        return "trend_drive_short", short_drive, [x for x, ok in [("smc_bos_down", bool(ctx_1h["bos_down"])), ("ict_mss_down", bool(ctx_1h["mss_down"])), ("resistance_zone", resist_ctx)] if ok]
    if short_repair >= 3 and long_drive <= 2:
        return "repair_short", short_repair, [x for x, ok in [("resistance_zone", resist_ctx), ("trigger_repair", trigger_state in {"confirm_short", "repairing_short"}), ("ema_resistance", _ema_alignment(latest_1h, "short") != "opposing")] if ok]
    if short_probe >= 2:
        return "probe_short", short_probe, [x for x, ok in [("resistance_zone", resist_ctx), ("early_warning", bool(latest_15m.get("sss_bear_div") or latest_15m.get("sss_overbought_warning"))), ("probing_trigger", trigger_state in {"probing_short", "repairing_short", "confirm_short"})] if ok]
    return "range_neutral", max(short_drive, short_repair, short_probe), []


def _choose_state(background_4h: str, latest_1h: dict, prev_1h: dict, ctx_1h: dict[str, Any], latest_15m: dict, prev_15m: dict, trigger_long: str, trigger_short: str, heat_profile: dict[str, Any]) -> tuple[str, int, list[str]]:
    long_state, long_score, long_basis = _state_candidate("long", background_4h, latest_1h, prev_1h, ctx_1h, latest_15m, prev_15m, trigger_long)
    short_state, short_score, short_basis = _state_candidate("short", background_4h, latest_1h, prev_1h, ctx_1h, latest_15m, prev_15m, trigger_short)
    if heat_profile["freeze_mode"] and max(long_score, short_score) < 5:
        return "range_neutral", max(long_score, short_score), []
    if max(long_score, short_score) <= 1:
        return "range_neutral", max(long_score, short_score), []
    if long_state != "range_neutral" and short_state != "range_neutral" and abs(long_score - short_score) <= 1:
        return "range_neutral", max(long_score, short_score), []
    if long_score > short_score:
        return long_state, long_score, long_basis
    if short_score > long_score:
        return short_state, short_score, short_basis
    return "range_neutral", max(long_score, short_score), []


def _trigger_context(direction: str, ctx_15m: dict[str, Any], latest_15m: dict) -> tuple[float | None, float | None]:
    close = _float(latest_15m.get("close"))
    atr = _atr(latest_15m)
    if direction == "long":
        lows = [_float(latest_15m.get("ema20")) - atr * 0.15]
        highs = [close, _float(latest_15m.get("ema10"))]
        for key in ("bull_fvg", "near_bull", "eql"):
            item = ctx_15m.get(key)
            if not item:
                continue
            if "zone_low" in item:
                lows.append(_float(item.get("zone_low")))
                highs.append(_float(item.get("zone_high")))
            if "price" in item:
                lows.append(_float(item.get("price")) - atr * 0.2)
                highs.append(_float(item.get("price")) + atr * 0.2)
        return min(lows), max(highs)
    lows = [close, _float(latest_15m.get("ema10"))]
    highs = [_float(latest_15m.get("ema20")) + atr * 0.15]
    for key in ("bear_fvg", "near_bear", "eqh"):
        item = ctx_15m.get(key)
        if not item:
            continue
        if "zone_low" in item:
            lows.append(_float(item.get("zone_low")))
            highs.append(_float(item.get("zone_high")))
        if "price" in item:
            lows.append(_float(item.get("price")) - atr * 0.2)
            highs.append(_float(item.get("price")) + atr * 0.2)
    return min(lows), max(highs)


def _state_to_signal(state_1h: str) -> tuple[str | None, str | None, int]:
    mapping = {"trend_drive_long": ("A_LONG", "long", 3), "trend_drive_short": ("A_SHORT", "short", 3), "repair_long": ("B_PULLBACK_LONG", "long", 2), "repair_short": ("B_PULLBACK_SHORT", "short", 2), "probe_long": ("C_LEFT_LONG", "long", 1), "probe_short": ("C_LEFT_SHORT", "short", 1)}
    return mapping.get(state_1h, (None, None, 0))


def _allow_low_heat_trend_override(name: str, direction: str, state_1h: str, state_score: int, trigger_15m_state: str, latest_1h: dict, latest_15m: dict, prev_15m: dict, background_4h_direction: str, ctx_1h: dict[str, Any], ctx_15m: dict[str, Any]) -> bool:
    if not name.startswith("A_") or not state_1h.startswith("trend_drive_") or state_score < 4:
        return False
    if direction == "long":
        bg_ok = background_4h_direction in {"bull", "lean_bull", "neutral"}
        structure_ok = bool(ctx_1h["bos_up"] or ctx_1h["mss_up"] or ctx_15m["bos_up"] or ctx_15m["mss_up"])
        zone_ok = bool(ctx_1h["bull_fvg"] or ctx_1h["bull_sweep"] or ctx_1h["near_bull"] or ctx_1h["eql"] or ctx_15m["bull_fvg"])
        ema_ok = _ema_alignment(latest_1h, "long") != "opposing" and _float(latest_15m.get("close")) >= _float(latest_15m.get("ema20"))
        flow_ok = trigger_15m_state in {"confirm_long", "repairing_long"} and _float(latest_15m.get("close")) >= _float(prev_15m.get("close"))
        return _count(bg_ok, structure_ok, zone_ok, ema_ok, flow_ok) >= 4
    bg_ok = background_4h_direction in {"bear", "lean_bear", "neutral"}
    structure_ok = bool(ctx_1h["bos_down"] or ctx_1h["mss_down"] or ctx_15m["bos_down"] or ctx_15m["mss_down"])
    zone_ok = bool(ctx_1h["bear_fvg"] or ctx_1h["bear_sweep"] or ctx_1h["near_bear"] or ctx_1h["eqh"] or ctx_15m["bear_fvg"])
    ema_ok = _ema_alignment(latest_1h, "short") != "opposing" and _float(latest_15m.get("close")) <= _float(latest_15m.get("ema20"))
    flow_ok = trigger_15m_state in {"confirm_short", "repairing_short"} and _float(latest_15m.get("close")) <= _float(prev_15m.get("close"))
    return _count(bg_ok, structure_ok, zone_ok, ema_ok, flow_ok) >= 4


def _allow_low_heat_repair_override(name: str, direction: str, state_1h: str, state_score: int, trigger_15m_state: str, latest_1h: dict, latest_15m: dict, prev_15m: dict, background_4h_direction: str, ctx_1h: dict[str, Any]) -> bool:
    if not name.startswith("B_") or not state_1h.startswith("repair_") or state_score < 4:
        return False
    if direction == "long":
        bg_ok = background_4h_direction in {"bull", "lean_bull"}
        zone_ok = bool(ctx_1h["bull_fvg"] or ctx_1h["bull_sweep"] or ctx_1h["near_bull"] or ctx_1h["eql"])
        ema_ok = _ema_alignment(latest_1h, "long") != "opposing"
        trigger_ok = trigger_15m_state == "confirm_long"
        flow_ok = _float(latest_15m.get("close")) >= _float(prev_15m.get("close"))
        return _count(bg_ok, zone_ok, ema_ok, trigger_ok, flow_ok) >= 4
    bg_ok = background_4h_direction in {"bear", "lean_bear"}
    zone_ok = bool(ctx_1h["bear_fvg"] or ctx_1h["bear_sweep"] or ctx_1h["near_bear"] or ctx_1h["eqh"])
    ema_ok = _ema_alignment(latest_1h, "short") != "opposing"
    trigger_ok = trigger_15m_state == "confirm_short"
    flow_ok = _float(latest_15m.get("close")) <= _float(prev_15m.get("close"))
    return _count(bg_ok, zone_ok, ema_ok, trigger_ok, flow_ok) >= 4


def detect_signals(symbol: str, klines_1d: list[dict], klines_4h: list[dict], klines_1h: list[dict], klines_15m: list[dict]) -> dict[str, Any]:
    latest_4h = klines_4h[-1]
    latest_1h, prev_1h = klines_1h[-1], klines_1h[-2]
    latest_15m, prev_15m = klines_15m[-1], klines_15m[-2]
    ctx_1h = _structure_context(klines_1h)
    ctx_15m = _structure_context(klines_15m)
    background_4h_direction = _background_4h_direction(klines_4h)
    trigger_long = _trigger_15m_state("long", latest_15m, prev_15m, ctx_15m)
    trigger_short = _trigger_15m_state("short", latest_15m, prev_15m, ctx_15m)
    heat_profile = _cross_tf_heat_profile(latest_15m, latest_1h, latest_4h)
    state_1h, state_score, structure_basis = _choose_state(background_4h_direction, latest_1h, prev_1h, ctx_1h, latest_15m, prev_15m, trigger_long, trigger_short, heat_profile)
    name, direction, _ = _state_to_signal(state_1h)
    signals, near_miss_signals, blocked_reasons = [], [], []
    if state_1h == "range_neutral":
        blocked_reasons.append("range_neutral")
        if heat_profile["tai_budget_mode"] in {"restricted", "frozen"}:
            blocked_reasons.append("heat_restricted_range_silence")
        return {"signals": signals, "near_miss_signals": near_miss_signals, "blocked_reasons": blocked_reasons, "background_4h_direction": background_4h_direction, "state_1h": state_1h, "trigger_15m_state": "idle", "tai_heat_1h": heat_profile["tai_heat_1h"], "tai_heat_4h": heat_profile["tai_heat_4h"], "tai_budget_mode": heat_profile["tai_budget_mode"]}
    if not name:
        blocked_reasons.append("no_state_mapping")
        return {"signals": [], "near_miss_signals": near_miss_signals, "blocked_reasons": blocked_reasons, "background_4h_direction": background_4h_direction, "state_1h": state_1h, "trigger_15m_state": trigger_long if direction == "long" else trigger_short, "tai_heat_1h": heat_profile["tai_heat_1h"], "tai_heat_4h": heat_profile["tai_heat_4h"], "tai_budget_mode": heat_profile["tai_budget_mode"]}
    active_trigger = trigger_long if direction == "long" else trigger_short
    if heat_profile["freeze_mode"]:
        blocked_reasons.append("cross_tf_heat_frozen")
        near_miss_signals.append({"candidate": name, "failed_checks": ["freeze_mode"]})
        return {"signals": [], "near_miss_signals": near_miss_signals, "blocked_reasons": blocked_reasons, "background_4h_direction": background_4h_direction, "state_1h": state_1h, "trigger_15m_state": active_trigger, "tai_heat_1h": heat_profile["tai_heat_1h"], "tai_heat_4h": heat_profile["tai_heat_4h"], "tai_budget_mode": heat_profile["tai_budget_mode"]}
    if heat_profile["tai_budget_mode"] == "restricted":
        trend_override = _allow_low_heat_trend_override(name, direction, state_1h, state_score, active_trigger, latest_1h, latest_15m, prev_15m, background_4h_direction, ctx_1h, ctx_15m)
        repair_override = _allow_low_heat_repair_override(name, direction, state_1h, state_score, active_trigger, latest_1h, latest_15m, prev_15m, background_4h_direction, ctx_1h)
        if name.startswith("A_"):
            if not (trend_override or (state_score >= 5 and active_trigger.startswith("confirm_"))):
                blocked_reasons.append("restricted_heat_blocks_weak_A")
                near_miss_signals.append({"candidate": name, "failed_checks": ["restricted_heat", "needs_confirmed_or_override_drive"]})
                return {"signals": [], "near_miss_signals": near_miss_signals, "blocked_reasons": blocked_reasons, "background_4h_direction": background_4h_direction, "state_1h": state_1h, "trigger_15m_state": active_trigger, "tai_heat_1h": heat_profile["tai_heat_1h"], "tai_heat_4h": heat_profile["tai_heat_4h"], "tai_budget_mode": heat_profile["tai_budget_mode"]}
        elif name.startswith("B_"):
            if not repair_override:
                blocked_reasons.append("restricted_heat_blocks_B")
                near_miss_signals.append({"candidate": name, "failed_checks": ["restricted_heat", "B_needs_repair_override"]})
                return {"signals": [], "near_miss_signals": near_miss_signals, "blocked_reasons": blocked_reasons, "background_4h_direction": background_4h_direction, "state_1h": state_1h, "trigger_15m_state": active_trigger, "tai_heat_1h": heat_profile["tai_heat_1h"], "tai_heat_4h": heat_profile["tai_heat_4h"], "tai_budget_mode": heat_profile["tai_budget_mode"]}
        else:
            blocked_reasons.append("restricted_heat_blocks_C")
            near_miss_signals.append({"candidate": name, "failed_checks": ["restricted_heat", "C_muted_in_cold_market"]})
            return {"signals": [], "near_miss_signals": near_miss_signals, "blocked_reasons": blocked_reasons, "background_4h_direction": background_4h_direction, "state_1h": state_1h, "trigger_15m_state": active_trigger, "tai_heat_1h": heat_profile["tai_heat_1h"], "tai_heat_4h": heat_profile["tai_heat_4h"], "tai_budget_mode": heat_profile["tai_budget_mode"]}
    if name.startswith("B_") and not active_trigger.startswith("confirm_"):
        blocked_reasons.append("B_requires_confirm_trigger")
        near_miss_signals.append({"candidate": name, "failed_checks": ["needs_confirm_trigger"]})
        return {"signals": [], "near_miss_signals": near_miss_signals, "blocked_reasons": blocked_reasons, "background_4h_direction": background_4h_direction, "state_1h": state_1h, "trigger_15m_state": active_trigger, "tai_heat_1h": heat_profile["tai_heat_1h"], "tai_heat_4h": heat_profile["tai_heat_4h"], "tai_budget_mode": heat_profile["tai_budget_mode"]}
    if name.startswith("C_") and active_trigger == "idle":
        blocked_reasons.append("C_requires_probing_trigger")
        near_miss_signals.append({"candidate": name, "failed_checks": ["needs_probe_trigger"]})
        return {"signals": [], "near_miss_signals": near_miss_signals, "blocked_reasons": blocked_reasons, "background_4h_direction": background_4h_direction, "state_1h": state_1h, "trigger_15m_state": active_trigger, "tai_heat_1h": heat_profile["tai_heat_1h"], "tai_heat_4h": heat_profile["tai_heat_4h"], "tai_budget_mode": heat_profile["tai_budget_mode"]}
    zone_low, zone_high = _trigger_context(direction, ctx_15m, latest_15m)
    trend_display_map = {"trend_drive_long": "bull", "trend_drive_short": "bear", "repair_long": "lean_bull", "repair_short": "lean_bear", "probe_long": "neutral", "probe_short": "neutral"}
    sig = _signal_dict(name, symbol, direction, _float(latest_15m.get("close")), trend_display_map.get(state_1h, "neutral"), "active", zone_low=zone_low, zone_high=zone_high, structure_basis=structure_basis, background_4h_direction=background_4h_direction, state_1h=state_1h, trigger_15m_state=active_trigger, heat_profile=heat_profile, candidate_score=state_score)
    signals.append(sig)
    return {"signals": signals, "near_miss_signals": near_miss_signals, "blocked_reasons": blocked_reasons, "background_4h_direction": background_4h_direction, "state_1h": state_1h, "trigger_15m_state": active_trigger, "tai_heat_1h": heat_profile["tai_heat_1h"], "tai_heat_4h": heat_profile["tai_heat_4h"], "tai_budget_mode": heat_profile["tai_budget_mode"]}
