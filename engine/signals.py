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

    tai_1h = _float(k_1h.get("tai_value"), 0.0)
    tai_1h_p20 = _float(k_1h.get("tai_p20"), 0.0)

    # 铁律：只有 1h TAI 真正跌到 p20 以下，frozen 才有触发资格
    frozen_eligible = tai_1h <= tai_1h_p20

    freeze_mode = False
    if frozen_eligible:
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


def _phase_name_from_state(state_1h: str) -> str:
    if state_1h.startswith("trend_drive_"):
        return "continuation"
    if state_1h.startswith("repair_"):
        return "repair"
    if state_1h.startswith("probe_"):
        return "early"
    return "none"


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
        if heat_1h in {"cool", "cold"}:
            return "flat"
        return "support"

    if state_1h.startswith("probe_"):
        if heat_1h in {"warm", "hot"}:
            return "support"
        return "flat"

    return "flat"


def _h1_tai_slot_from_heat(heat_1h: str) -> str:
    mapping = {
        "cold": "ice",
        "cool": "cool",
        "neutral": "mid",
        "warm": "warm",
        "hot": "hot",
    }
    return mapping.get(heat_1h, "mid")


def _phase_anchor(
    symbol: str,
    direction: str,
    state_1h: str,
    background_4h_direction: str,
    trigger_15m_state: str,
    heat_1h: str,
) -> str:
    phase_name = _phase_name_from_state(state_1h)

    trigger_bucket = "confirm"
    if trigger_15m_state.startswith("repairing_"):
        trigger_bucket = "repair"
    elif trigger_15m_state.startswith("probing_"):
        trigger_bucket = "probe"
    elif trigger_15m_state == "idle":
        trigger_bucket = "idle"

    return "|".join(
        [
            symbol,
            direction,
            phase_name,
            background_4h_direction,
            trigger_bucket,
            heat_1h,
        ]
    )


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

    if background_4h_direction in {"bull", "bear"}:
        score += 6
    elif background_4h_direction in {"lean_bull", "lean_bear"}:
        score += 3
    else:
        score -= 4

    if state_1h in {"trend_drive_long", "trend_drive_short"}:
        score += 7
    elif state_1h in {"repair_long", "repair_short"}:
        score += 4
    elif state_1h in {"probe_long", "probe_short"}:
        score += 1
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
    score += min(6, max(0, candidate_score - 2) * 2)

    budget = heat_profile["tai_budget_mode"]
    heat_1h = heat_profile["tai_heat_1h"]
    heat_4h = heat_profile["tai_heat_4h"]

    if budget == "restricted":
        score -= 8
    elif budget == "frozen":
        score -= 14

    if heat_1h in {"cold", "cool"} and heat_4h in {"cold", "cool"}:
        score -= 4

    if signal_name.startswith("A_"):
        score = max(64, min(86, score))
    elif signal_name.startswith("B_"):
        score = max(58, min(76, score))
    elif signal_name.startswith("C_"):
        score = max(50, min(64, score))
    else:
        score = max(48, min(62, score))

    return int(score)


def _signal_dict(
    name: str,
    symbol: str,
    direction: str,
    price: float,
    trend_1h: str,
    status: str,
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
    eta_map = {1: (15, 135), 2: (25, 165), 3: (25, 165)}
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
        "trend_1h": trend_1h,
        "status": "active" if rank <= 2 else "early",
        "zone_low": zone_low,
        "zone_high": zone_high,
        "structure_basis": structure_basis,
        "eta_min_minutes": eta_min,
        "eta_max_minutes": eta_max,
        "cooldown_seconds": {1: 45 * 60, 2: 35 * 60, 3: 25 * 60}.get(rank, 30 * 60),
        "phase_rank": rank,
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

    state_1h, candidate_score, state_basis = _choose_state(
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

    signal_name, direction = _state_to_signal(state_1h)
    if not signal_name or not direction:
        blocked = []
        if state_1h == "range_neutral":
            blocked.append("range_neutral")
            if heat_profile["tai_budget_mode"] == "restricted":
                blocked.append("heat_restricted_range_silence")
            if heat_profile["tai_budget_mode"] == "frozen":
                blocked.append("heat_frozen_range_silence")
        return {
            "signals": [],
            "near_miss_signals": [],
            "background_4h_direction": background_4h,
            "state_1h": state_1h,
            "trigger_15m_state": trigger_long if "long" in state_1h else trigger_short if "short" in state_1h else "idle",
            "tai_budget_mode": heat_profile["tai_budget_mode"],
            "tai_heat_1h": heat_profile["tai_heat_1h"],
            "tai_heat_4h": heat_profile["tai_heat_4h"],
            "blocked_reasons": blocked,
        }

    atr15 = _atr(latest_15m)
    if direction == "long":
        zone_low = min(
            _float(latest_15m.get("ema10")),
            _float(latest_15m.get("ema20")),
            _float(latest_15m.get("close")) - atr15 * 0.2,
        )
        zone_high = max(
            _float(latest_15m.get("ema10")),
            _float(latest_15m.get("ema20")),
            _float(latest_15m.get("close")) + atr15 * 0.08,
        )
        trigger_display = trigger_long
    else:
        zone_low = min(
            _float(latest_15m.get("ema10")),
            _float(latest_15m.get("ema20")),
            _float(latest_15m.get("close")) - atr15 * 0.08,
        )
        zone_high = max(
            _float(latest_15m.get("ema10")),
            _float(latest_15m.get("ema20")),
            _float(latest_15m.get("close")) + atr15 * 0.2,
        )
        trigger_display = trigger_short

    signal = _signal_dict(
        name=signal_name,
        symbol=symbol,
        direction=direction,
        price=round(_float(latest_15m.get("close")), 2),
        trend_1h=state_1h,
        status="active" if SIGNAL_CLASS[signal_name] <= 2 else "early",
        zone_low=round(zone_low, 2),
        zone_high=round(zone_high, 2),
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
