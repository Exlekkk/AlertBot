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
        if score >= 4 and vol_ratio >= 1.05:
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
    if score >= 4 and vol_ratio >= 1.05:
        return "confirm_short"
    if score >= 2:
        return "repairing_short"
    if score >= 1:
        return "probing_short"
    return "idle"


def _state_candidate(
    direction: str,
    background_4h: str,
    latest_1h: dict,
    prev_1h: dict,
    ctx_1h: dict[str, Any],
    latest_15m: dict,
    prev_15m: dict,
    trigger_state: str,
) -> tuple[str, int, list[str]]:
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
            return "trend_drive_long", long_drive, [
                x for x, ok in [
                    ("smc_bos_up", bool(ctx_1h["bos_up"])),
                    ("ict_mss_up", bool(ctx_1h["mss_up"])),
                    ("support_zone", support_ctx),
                ] if ok
            ]
        if long_repair >= 3 and short_drive <= 2:
            return "repair_long", long_repair, [
                x for x, ok in [
                    ("support_zone", support_ctx),
                    ("trigger_repair", trigger_state in {"confirm_long", "repairing_long"}),
                    ("ema_support", _ema_alignment(latest_1h, "long") != "opposing"),
                ] if ok
            ]
        if long_probe >= 2:
            return "probe_long", long_probe, [
                x for x, ok in [
                    ("support_zone", support_ctx),
                    ("early_warning", bool(latest_15m.get("sss_bull_div") or latest_15m.get("sss_oversold_warning"))),
                    ("probing_trigger", trigger_state in {"probing_long", "repairing_long", "confirm_long"}),
                ] if ok
            ]
        return "range_neutral", max(long_drive, long_repair, long_probe), []

    if short_drive >= 4 and long_drive <= 1:
        return "trend_drive_short", short_drive, [
            x for x, ok in [
                ("smc_bos_down", bool(ctx_1h["bos_down"])),
                ("ict_mss_down", bool(ctx_1h["mss_down"])),
                ("resistance_zone", resist_ctx),
            ] if ok
        ]
    if short_repair >= 3 and long_drive <= 2:
        return "repair_short", short_repair, [
            x for x, ok in [
                ("resistance_zone", resist_ctx),
                ("trigger_repair", trigger_state in {"confirm_short", "repairing_short"}),
                ("ema_resistance", _ema_alignment(latest_1h, "short") != "opposing"),
            ] if ok
        ]
    if short_probe >= 2:
        return "probe_short", short_probe, [
            x for x, ok in [
                ("resistance_zone", resist_ctx),
                ("early_warning", bool(latest_15m.get("sss_bear_div") or latest_15m.get("sss_overbought_warning"))),
                ("probing_trigger", trigger_state in {"probing_short", "repairing_short", "confirm_short"}),
            ] if ok
        ]
    return "range_neutral", max(short_drive, short_repair, short_probe), []


def _choose_state(
    background_4h: str,
    latest_1h: dict,
    prev_1h: dict,
    ctx_1h: dict[str, Any],
    latest_15m: dict,
    prev_15m: dict,
    trigger_long: str,
    trigger_short: str,
) -> tuple[str, int, list[str]]:
    long_state, long_score, long_basis = _state_candidate(
        "long", background_4h, latest_1h, prev_1h, ctx_1h, latest_15m, prev_15m, trigger_long
    )
    short_state, short_score, short_basis = _state_candidate(
        "short", background_4h, latest_1h, prev_1h, ctx_1h, latest_15m, prev_15m, trigger_short
    )

    if max(long_score, short_score) <= 1:
        return "range_neutral", max(long_score, short_score), []
    if long_state != "range_neutral" and short_state != "range_neutral" and abs(long_score - short_score) <= 1:
        return "range_neutral", max(long_score, short_score), []
    if long_score > short_score:
        return long_state, long_score, long_basis
    if short_score > long_score:
        return short_state, short_score, short_basis
    return "range_neutral", max(long_score, short_score), []


def _trigger_context(direction: str, latest_15m: dict) -> tuple[float | None, float | None]:
    close = _float(latest_15m.get("close"))
    atr = _atr(latest_15m)
    ema10 = _float(latest_15m.get("ema10"))
    ema20 = _float(latest_15m.get("ema20"))

    if direction == "long":
        low = min(close - atr * 0.20, ema10, ema20)
        high = max(close + atr * 0.10, ema10, ema20)
        return round(low, 2), round(high, 2)

    low = min(close - atr * 0.10, ema10, ema20)
    high = max(close + atr * 0.20, ema10, ema20)
    return round(low, 2), round(high, 2)


def _abc_confidence(
    signal_name: str,
    direction: str,
    background_4h: str,
    phase_context: str,
    trigger_quality: str,
    structure_basis: list[str],
) -> int:
    if signal_name.startswith("A_"):
        base = 74
    elif signal_name.startswith("B_"):
        base = 62
    else:
        base = 54

    if background_4h in {"bull", "bear"}:
        base += 6
    elif background_4h in {"lean_bull", "lean_bear"}:
        base += 2

    if phase_context in {"trend_drive_long", "trend_drive_short"}:
        base += 7
    elif phase_context in {"repair_long", "repair_short"}:
        base += 4
    elif phase_context in {"probe_long", "probe_short"}:
        base += 1

    if trigger_quality == "explosive":
        base += 5
    elif trigger_quality == "ready":
        base += 3
    elif trigger_quality == "watch":
        base += 1

    base += min(6, len(structure_basis) * 2)

    if signal_name.startswith("A_"):
        return max(60, min(89, base))
    if signal_name.startswith("B_"):
        return max(58, min(76, base))
    return max(50, min(70, base))


def _build_signal(
    signal: str,
    symbol: str,
    direction: str,
    priority: int,
    latest_15m: dict,
    state_1h: str,
    background_4h: str,
    trigger_15m_state: str,
    heat_profile: dict[str, Any],
    structure_basis: list[str],
    status: str,
    zone_low: float | None,
    zone_high: float | None,
    trigger_level: float | None = None,
    eta_min_minutes: int | None = None,
    eta_max_minutes: int | None = None,
) -> dict[str, Any]:
    if trigger_15m_state.startswith("confirm"):
        trigger_quality = "explosive"
    elif trigger_15m_state.startswith("repairing"):
        trigger_quality = "ready"
    else:
        trigger_quality = "watch"

    confidence = _abc_confidence(
        signal_name=signal,
        direction=direction,
        background_4h=background_4h,
        phase_context=state_1h,
        trigger_quality=trigger_quality,
        structure_basis=structure_basis,
    )

    return {
        "signal": signal,
        "symbol": symbol,
        "timeframe": "15m",
        "direction": direction,
        "priority": priority,
        "price": round(_float(latest_15m.get("close")), 2),
        "state_1h": state_1h,
        "background_4h_direction": background_4h,
        "trigger_15m_state": trigger_15m_state,
        "tai_budget_mode": heat_profile["tai_budget_mode"],
        "tai_heat_15m": heat_profile["tai_heat_15m"],
        "tai_heat_1h": heat_profile["tai_heat_1h"],
        "tai_heat_4h": heat_profile["tai_heat_4h"],
        "freeze_mode": heat_profile["freeze_mode"],
        "heat_restricted": heat_profile["tai_budget_mode"] == "restricted",
        "structure_basis": structure_basis,
        "status": status,
        "zone_low": zone_low,
        "zone_high": zone_high,
        "trigger_level": trigger_level,
        "eta_min_minutes": eta_min_minutes,
        "eta_max_minutes": eta_max_minutes,
        "confidence": confidence,
    }


def _near_miss(signal_name: str, failed_checks: list[str], reasons: list[str]) -> dict[str, Any]:
    return {
        "candidate": signal_name,
        "failed_checks": failed_checks,
        "blocked_reasons": reasons,
    }


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

    latest_4h, prev_4h = klines_4h[-1], klines_4h[-2]
    latest_1h, prev_1h = klines_1h[-1], klines_1h[-2]
    latest_15m, prev_15m = klines_15m[-1], klines_15m[-2]

    ctx_1h = _structure_context(klines_1h)
    ctx_15m = _structure_context(klines_15m)

    background_4h = _background_4h_direction(klines_4h)
    trigger_long = _trigger_15m_state("long", latest_15m, prev_15m, ctx_15m)
    trigger_short = _trigger_15m_state("short", latest_15m, prev_15m, ctx_15m)
    state_1h, state_score, state_basis = _choose_state(
        background_4h,
        latest_1h,
        prev_1h,
        ctx_1h,
        latest_15m,
        prev_15m,
        trigger_long,
        trigger_short,
    )
    heat_profile = _cross_tf_heat_profile(latest_15m, latest_1h, latest_4h)

    signals: list[dict[str, Any]] = []
    near_miss_signals: list[dict[str, Any]] = []
    blocked_reasons: list[str] = []

    long_zone = _trigger_context("long", latest_15m)
    short_zone = _trigger_context("short", latest_15m)

    trigger_display = trigger_long if "long" in state_1h else trigger_short if "short" in state_1h else "idle"

    if heat_profile["freeze_mode"]:
        blocked_reasons.append("heat_freeze")

    if state_1h == "range_neutral":
        blocked_reasons.append("range_neutral")
        if heat_profile["tai_budget_mode"] == "restricted":
            blocked_reasons.append("heat_restricted_range_silence")
        return {
            "signals": [],
            "near_miss_signals": [],
            "background_4h_direction": background_4h,
            "state_1h": state_1h,
            "trigger_15m_state": trigger_display,
            "tai_budget_mode": heat_profile["tai_budget_mode"],
            "tai_heat_1h": heat_profile["tai_heat_1h"],
            "tai_heat_4h": heat_profile["tai_heat_4h"],
            "blocked_reasons": blocked_reasons,
        }

    # A signals: only with proper confirm
    if state_1h == "trend_drive_long":
        if trigger_long == "confirm_long":
            signals.append(
                _build_signal(
                    signal="A_LONG",
                    symbol=symbol,
                    direction="long",
                    priority=1,
                    latest_15m=latest_15m,
                    state_1h=state_1h,
                    background_4h=background_4h,
                    trigger_15m_state=trigger_long,
                    heat_profile=heat_profile,
                    structure_basis=state_basis,
                    status="active",
                    zone_low=long_zone[0],
                    zone_high=long_zone[1],
                    trigger_level=_float(latest_15m.get("high")),
                    eta_min_minutes=5,
                    eta_max_minutes=30,
                )
            )
        else:
            blocked_reasons.append("A_requires_confirm_trigger")
            near_miss_signals.append(_near_miss("A_LONG", ["needs_confirm_trigger"], blocked_reasons.copy()))

    if state_1h == "trend_drive_short":
        if trigger_short == "confirm_short":
            signals.append(
                _build_signal(
                    signal="A_SHORT",
                    symbol=symbol,
                    direction="short",
                    priority=1,
                    latest_15m=latest_15m,
                    state_1h=state_1h,
                    background_4h=background_4h,
                    trigger_15m_state=trigger_short,
                    heat_profile=heat_profile,
                    structure_basis=state_basis,
                    status="active",
                    zone_low=short_zone[0],
                    zone_high=short_zone[1],
                    trigger_level=_float(latest_15m.get("low")),
                    eta_min_minutes=5,
                    eta_max_minutes=30,
                )
            )
        else:
            blocked_reasons.append("A_requires_confirm_trigger")
            near_miss_signals.append(_near_miss("A_SHORT", ["needs_confirm_trigger"], blocked_reasons.copy()))

    # B signals: relaxed from hard confirm -> allow repairing trigger in restricted mode when structure is already repair
    if state_1h == "repair_long":
        allow_b_long = trigger_long in {"confirm_long", "repairing_long"}
        if allow_b_long:
            signals.append(
                _build_signal(
                    signal="B_PULLBACK_LONG",
                    symbol=symbol,
                    direction="long",
                    priority=2,
                    latest_15m=latest_15m,
                    state_1h=state_1h,
                    background_4h=background_4h,
                    trigger_15m_state=trigger_long,
                    heat_profile=heat_profile,
                    structure_basis=state_basis,
                    status="active" if trigger_long == "confirm_long" else "early",
                    zone_low=long_zone[0],
                    zone_high=long_zone[1],
                    trigger_level=_float(latest_15m.get("close")),
                    eta_min_minutes=15,
                    eta_max_minutes=120,
                )
            )
        else:
            blocked_reasons.append("B_requires_confirm_trigger")
            near_miss_signals.append(_near_miss("B_PULLBACK_LONG", ["needs_confirm_trigger"], blocked_reasons.copy()))

    if state_1h == "repair_short":
        allow_b_short = trigger_short in {"confirm_short", "repairing_short"}
        if allow_b_short:
            signals.append(
                _build_signal(
                    signal="B_PULLBACK_SHORT",
                    symbol=symbol,
                    direction="short",
                    priority=2,
                    latest_15m=latest_15m,
                    state_1h=state_1h,
                    background_4h=background_4h,
                    trigger_15m_state=trigger_short,
                    heat_profile=heat_profile,
                    structure_basis=state_basis,
                    status="active" if trigger_short == "confirm_short" else "early",
                    zone_low=short_zone[0],
                    zone_high=short_zone[1],
                    trigger_level=_float(latest_15m.get("close")),
                    eta_min_minutes=15,
                    eta_max_minutes=120,
                )
            )
        else:
            blocked_reasons.append("B_requires_confirm_trigger")
            near_miss_signals.append(_near_miss("B_PULLBACK_SHORT", ["needs_confirm_trigger"], blocked_reasons.copy()))

    # C signals
    if state_1h == "probe_long":
        signals.append(
            _build_signal(
                signal="C_LEFT_LONG",
                symbol=symbol,
                direction="long",
                priority=3,
                latest_15m=latest_15m,
                state_1h=state_1h,
                background_4h=background_4h,
                trigger_15m_state=trigger_long,
                heat_profile=heat_profile,
                structure_basis=state_basis,
                status="early",
                zone_low=long_zone[0],
                zone_high=long_zone[1],
                trigger_level=_float(latest_15m.get("close")),
                eta_min_minutes=60,
                eta_max_minutes=360,
            )
        )

    if state_1h == "probe_short":
        signals.append(
            _build_signal(
                signal="C_LEFT_SHORT",
                symbol=symbol,
                direction="short",
                priority=3,
                latest_15m=latest_15m,
                state_1h=state_1h,
                background_4h=background_4h,
                trigger_15m_state=trigger_short,
                heat_profile=heat_profile,
                structure_basis=state_basis,
                status="early",
                zone_low=short_zone[0],
                zone_high=short_zone[1],
                trigger_level=_float(latest_15m.get("close")),
                eta_min_minutes=60,
                eta_max_minutes=360,
            )
        )

    if not signals and not blocked_reasons:
        blocked_reasons.append("no_actionable_signal")

    # keep only best directional narrative if multiple ABC appear
    if len(signals) > 1:
        signals.sort(
            key=lambda s: (
                -int(s.get("priority", 99)),
                -int(s.get("confidence", 0)),
            )
        )
        top = signals[0]
        signals = [s for s in signals if s["direction"] == top["direction"]]
        signals.sort(key=lambda s: (int(s.get("priority", 99)), -int(s.get("confidence", 0))))

    return {
        "signals": signals,
        "near_miss_signals": near_miss_signals,
        "background_4h_direction": background_4h,
        "state_1h": state_1h,
        "trigger_15m_state": trigger_display,
        "tai_budget_mode": heat_profile["tai_budget_mode"],
        "tai_heat_1h": heat_profile["tai_heat_1h"],
        "tai_heat_4h": heat_profile["tai_heat_4h"],
        "blocked_reasons": blocked_reasons,
    }
