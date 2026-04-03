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


def _tai_budget_mode(heat: str) -> str:
    if heat in {"cold", "cool"}:
        return "restricted"
    if heat == "neutral":
        return "normal"
    return "expanded"


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
    if score >= 4 and vol_ratio >= 1.15:
        return f"confirm_{direction}"
    if score >= 2:
        return f"repairing_{direction}"
    if score >= 1:
        return f"probing_{direction}"
    return "idle"


def _state_candidate(direction: str, background_4h: str, latest_1h: dict, prev_1h: dict, ctx_1h: dict[str, Any], latest_15m: dict, prev_15m: dict, trigger_state: str) -> tuple[str, int, list[str]]:
    support_ctx = bool(ctx_1h["bull_fvg"] or ctx_1h["bull_sweep"] or ctx_1h["near_bull"] or ctx_1h["eql"])
    resist_ctx = bool(ctx_1h["bear_fvg"] or ctx_1h["bear_sweep"] or ctx_1h["near_bear"] or ctx_1h["eqh"])
    long_drive = _count(
        background_4h in {"bull", "lean_bull"},
        bool(ctx_1h["bos_up"] or ctx_1h["mss_up"]),
        _ema_alignment(latest_1h, "long") == "supportive",
        _momentum_up(latest_1h, prev_1h),
        trigger_state == "confirm_long",
    )
    short_drive = _count(
        background_4h in {"bear", "lean_bear"},
        bool(ctx_1h["bos_down"] or ctx_1h["mss_down"]),
        _ema_alignment(latest_1h, "short") == "supportive",
        _momentum_down(latest_1h, prev_1h),
        trigger_state == "confirm_short",
    )
    long_repair = _count(
        background_4h != "bear",
        support_ctx,
        _ema_alignment(latest_1h, "long") != "opposing",
        trigger_state in {"confirm_long", "repairing_long"},
        _float(latest_15m.get("close")) >= _float(prev_15m.get("close")),
    )
    short_repair = _count(
        background_4h != "bull",
        resist_ctx,
        _ema_alignment(latest_1h, "short") != "opposing",
        trigger_state in {"confirm_short", "repairing_short"},
        _float(latest_15m.get("close")) <= _float(prev_15m.get("close")),
    )
    long_probe = _count(
        support_ctx,
        trigger_state in {"confirm_long", "repairing_long", "probing_long"},
        bool(latest_15m.get("sss_bull_div") or latest_15m.get("sss_oversold_warning") or latest_15m.get("fl_buy_signal")),
    )
    short_probe = _count(
        resist_ctx,
        trigger_state in {"confirm_short", "repairing_short", "probing_short"},
        bool(latest_15m.get("sss_bear_div") or latest_15m.get("sss_overbought_warning") or latest_15m.get("fl_sell_signal")),
    )

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


def _choose_state(background_4h: str, latest_1h: dict, prev_1h: dict, ctx_1h: dict[str, Any], latest_15m: dict, prev_15m: dict, trigger_long: str, trigger_short: str) -> tuple[str, int, list[str], str]:
    long_state, long_score, long_basis = _state_candidate("long", background_4h, latest_1h, prev_1h, ctx_1h, latest_15m, prev_15m, trigger_long)
    short_state, short_score, short_basis = _state_candidate("short", background_4h, latest_1h, prev_1h, ctx_1h, latest_15m, prev_15m, trigger_short)
    heat_1h = _tai_heat(latest_1h)

    # Range-neutral is explicit when both sides are weak or conflict heavily.
    if max(long_score, short_score) <= 1:
        return "range_neutral", max(long_score, short_score), [], heat_1h
    if long_state != "range_neutral" and short_state != "range_neutral" and abs(long_score - short_score) <= 1:
        return "range_neutral", max(long_score, short_score), [], heat_1h
    if long_score > short_score:
        return long_state, long_score, long_basis, heat_1h
    if short_score > long_score:
        return short_state, short_score, short_basis, heat_1h
    return "range_neutral", max(long_score, short_score), [], heat_1h


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
    mapping = {
        "trend_drive_long": ("A_LONG", "long", 3),
        "trend_drive_short": ("A_SHORT", "short", 3),
        "repair_long": ("B_PULLBACK_LONG", "long", 2),
        "repair_short": ("B_PULLBACK_SHORT", "short", 2),
        "probe_long": ("C_LEFT_LONG", "long", 1),
        "probe_short": ("C_LEFT_SHORT", "short", 1),
    }
    return mapping.get(state_1h, (None, None, 0))


def _signal_dict(name: str, symbol: str, direction: str, price: float, trend_1h: str, status: str, *, zone_low: float | None, zone_high: float | None, structure_basis: list[str], background_4h_direction: str, state_1h: str, trigger_15m_state: str, tai_heat_1h: str, tai_heat_15m: str, tai_budget_mode: str, candidate_score: int) -> dict[str, Any]:
    rank = SIGNAL_CLASS[name]
    eta_map = {1: (15, 135), 2: (25, 165), 3: (25, 165)}
    eta_min, eta_max = eta_map.get(rank, (20, 120))
    segment_id = f"{symbol}|15m|{state_1h}|{direction}|{tai_heat_1h}"
    return {
        "signal": name,
        "symbol": symbol,
        "timeframe": "15m",
        "priority": rank,
        "direction": direction,
        "price": price,
        "trend_1h": trend_1h,
        "status": "active" if rank <= 2 else "early",
        "zone_low": zone_low,
        "zone_high": zone_high,
        "structure_basis": structure_basis,
        "eta_min_minutes": eta_min,
        "eta_max_minutes": eta_max,
        "cooldown_seconds": {1: 45 * 60, 2: 35 * 60, 3: 25 * 60}.get(rank, 30 * 60),
        "phase_rank": rank,
        "phase_name": state_1h,
        "phase_context": f"{background_4h_direction}|{trigger_15m_state}|{tai_heat_1h}",
        "trigger_state": trigger_15m_state,
        "bg_bias": background_4h_direction,
        "signature": f"{name}|{direction}|{round(zone_low or price)}-{round(zone_high or price)}|{tai_heat_1h}",
        "background_4h_direction": background_4h_direction,
        "state_1h": state_1h,
        "trigger_15m_state": trigger_15m_state,
        "tai_heat_1h": tai_heat_1h,
        "tai_heat_15m": tai_heat_15m,
        "tai_budget_mode": tai_budget_mode,
        "heat_restricted": tai_budget_mode == "restricted",
        "segment_id": segment_id,
        "candidate_score": candidate_score,
    }


def detect_signals(symbol: str, klines_1d: list[dict], klines_4h: list[dict], klines_1h: list[dict], klines_15m: list[dict]) -> dict[str, Any]:
    latest_4h, prev_4h = klines_4h[-1], klines_4h[-2]
    latest_1h, prev_1h = klines_1h[-1], klines_1h[-2]
    latest_15m, prev_15m = klines_15m[-1], klines_15m[-2]

    ctx_1h = _structure_context(klines_1h)
    ctx_15m = _structure_context(klines_15m)
    background_4h_direction = _background_4h_direction(klines_4h)
    trigger_long = _trigger_15m_state("long", latest_15m, prev_15m, ctx_15m)
    trigger_short = _trigger_15m_state("short", latest_15m, prev_15m, ctx_15m)
    state_1h, state_score, structure_basis, tai_heat_1h = _choose_state(
        background_4h_direction, latest_1h, prev_1h, ctx_1h, latest_15m, prev_15m, trigger_long, trigger_short
    )
    tai_heat_15m = _tai_heat(latest_15m)
    tai_budget_mode = _tai_budget_mode(tai_heat_1h)

    name, direction, _ = _state_to_signal(state_1h)
    signals: list[dict[str, Any]] = []
    near_miss_signals: list[dict[str, Any]] = []
    blocked_reasons: list[str] = []

    if state_1h == "range_neutral":
        blocked_reasons.append("range_neutral")
        if tai_budget_mode == "restricted":
            blocked_reasons.append("heat_restricted")
        # allow only rare high-quality C from probing 15m context
        if tai_budget_mode != "restricted":
            if trigger_long == "probing_long" and bool(ctx_15m["near_bull"] or ctx_15m["bull_fvg"] or ctx_15m["eql"]):
                zl, zh = _trigger_context("long", ctx_15m, latest_15m)
                signals.append(
                    _signal_dict(
                        "C_LEFT_LONG", symbol, "long", _float(latest_15m.get("close")), "neutral", "early",
                        zone_low=zl, zone_high=zh, structure_basis=["range_probe", "support_zone"],
                        background_4h_direction=background_4h_direction, state_1h=state_1h,
                        trigger_15m_state=trigger_long, tai_heat_1h=tai_heat_1h, tai_heat_15m=tai_heat_15m,
                        tai_budget_mode=tai_budget_mode, candidate_score=2,
                    )
                )
            elif trigger_short == "probing_short" and bool(ctx_15m["near_bear"] or ctx_15m["bear_fvg"] or ctx_15m["eqh"]):
                zl, zh = _trigger_context("short", ctx_15m, latest_15m)
                signals.append(
                    _signal_dict(
                        "C_LEFT_SHORT", symbol, "short", _float(latest_15m.get("close")), "neutral", "early",
                        zone_low=zl, zone_high=zh, structure_basis=["range_probe", "resistance_zone"],
                        background_4h_direction=background_4h_direction, state_1h=state_1h,
                        trigger_15m_state=trigger_short, tai_heat_1h=tai_heat_1h, tai_heat_15m=tai_heat_15m,
                        tai_budget_mode=tai_budget_mode, candidate_score=2,
                    )
                )
        return {
            "signals": signals,
            "near_miss_signals": near_miss_signals,
            "blocked_reasons": blocked_reasons,
            "background_4h_direction": background_4h_direction,
            "state_1h": state_1h,
            "trigger_15m_state": "idle",
            "tai_heat_1h": tai_heat_1h,
        }

    # heat restriction: stricter A/B/C gating
    if tai_budget_mode == "restricted":
        if state_1h.startswith("trend_drive"):
            blocked_reasons.append("restricted_heat_blocks_A")
            if state_score < 5:
                near_miss_signals.append({"candidate": name, "failed_checks": ["restricted_heat", "insufficient_drive_score"]})
                return {
                    "signals": [], "near_miss_signals": near_miss_signals, "blocked_reasons": blocked_reasons,
                    "background_4h_direction": background_4h_direction, "state_1h": state_1h,
                    "trigger_15m_state": trigger_long if direction == "long" else trigger_short, "tai_heat_1h": tai_heat_1h,
                }
        elif state_1h.startswith("repair"):
            blocked_reasons.append("restricted_heat_tightens_B")
            if state_score < 4:
                near_miss_signals.append({"candidate": name, "failed_checks": ["restricted_heat", "insufficient_repair_score"]})
                return {
                    "signals": [], "near_miss_signals": near_miss_signals, "blocked_reasons": blocked_reasons,
                    "background_4h_direction": background_4h_direction, "state_1h": state_1h,
                    "trigger_15m_state": trigger_long if direction == "long" else trigger_short, "tai_heat_1h": tai_heat_1h,
                }
        elif state_score < 3:
            blocked_reasons.append("restricted_heat_tightens_C")
            near_miss_signals.append({"candidate": name, "failed_checks": ["restricted_heat", "insufficient_probe_score"]})
            return {
                "signals": [], "near_miss_signals": near_miss_signals, "blocked_reasons": blocked_reasons,
                "background_4h_direction": background_4h_direction, "state_1h": state_1h,
                "trigger_15m_state": trigger_long if direction == "long" else trigger_short, "tai_heat_1h": tai_heat_1h,
            }

    if not name:
        blocked_reasons.append("no_state_mapping")
        return {
            "signals": [], "near_miss_signals": near_miss_signals, "blocked_reasons": blocked_reasons,
            "background_4h_direction": background_4h_direction, "state_1h": state_1h,
            "trigger_15m_state": trigger_long if direction == "long" else trigger_short, "tai_heat_1h": tai_heat_1h,
        }

    zone_low, zone_high = _trigger_context(direction, ctx_15m, latest_15m)
    trend_display_map = {
        "trend_drive_long": "bull",
        "trend_drive_short": "bear",
        "repair_long": "lean_bull",
        "repair_short": "lean_bear",
        "probe_long": "neutral",
        "probe_short": "neutral",
    }
    sig = _signal_dict(
        name,
        symbol,
        direction,
        _float(latest_15m.get("close")),
        trend_display_map.get(state_1h, "neutral"),
        "active",
        zone_low=zone_low,
        zone_high=zone_high,
        structure_basis=structure_basis,
        background_4h_direction=background_4h_direction,
        state_1h=state_1h,
        trigger_15m_state=trigger_long if direction == "long" else trigger_short,
        tai_heat_1h=tai_heat_1h,
        tai_heat_15m=tai_heat_15m,
        tai_budget_mode=tai_budget_mode,
        candidate_score=state_score,
    )
    signals.append(sig)
    return {
        "signals": signals,
        "near_miss_signals": near_miss_signals,
        "blocked_reasons": blocked_reasons,
        "background_4h_direction": background_4h_direction,
        "state_1h": state_1h,
        "trigger_15m_state": trigger_long if direction == "long" else trigger_short,
        "tai_heat_1h": tai_heat_1h,
    }
