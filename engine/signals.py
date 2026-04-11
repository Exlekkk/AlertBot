
from __future__ import annotations

from typing import Any

from engine.structure import (
    detect_near_pivot_level,
    detect_recent_equal_levels,
    detect_recent_fvg_fill,
    detect_recent_liquidity_sweep,
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
    close = abs(_float(k.get("close"), 0.0))
    return max(_float(k.get("atr"), 0.0), close * 0.0012, 1e-9)


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

    ord_15m = _heat_order(heat_15m)
    ord_1h = _heat_order(heat_1h)
    ord_4h = _heat_order(heat_4h)
    avg_order = (ord_15m + ord_1h + ord_4h) / 3.0

    tai_1h = _float(k_1h.get("tai_value"), 0.0)
    tai_1h_p20 = _float(k_1h.get("tai_p20"), 0.0)
    icepoint_1h = tai_1h <= tai_1h_p20
    rising_15m = bool(k_15m.get("tai_rising"))
    rising_1h = bool(k_1h.get("tai_rising"))

    if icepoint_1h and ord_15m <= 1 and not (rising_15m or rising_1h):
        budget = "frozen"
    elif ord_1h <= 1 or avg_order <= 1.45 or (icepoint_1h and ord_15m <= 2):
        budget = "restricted"
    elif ord_1h >= 3 and avg_order >= 2.6:
        budget = "expanded"
    else:
        budget = "normal"

    return {
        "tai_heat_15m": heat_15m,
        "tai_heat_1h": heat_1h,
        "tai_heat_4h": heat_4h,
        "tai_budget_mode": budget,
        "freeze_mode": budget == "frozen",
        "icepoint_1h": icepoint_1h,
        "tai_rising_15m": rising_15m,
        "tai_rising_1h": rising_1h,
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
        if score >= 4 and vol_ratio >= 1.08:
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
    if score >= 4 and vol_ratio >= 1.08:
        return "confirm_short"
    if score >= 2:
        return "repairing_short"
    if score >= 1:
        return "probing_short"
    return "idle"


def _directional_context(direction: str, ctx_1h: dict[str, Any], ctx_15m: dict[str, Any]) -> tuple[bool, bool, bool]:
    if direction == "long":
        support = bool(
            ctx_1h["bull_fvg"] or ctx_1h["bull_sweep"] or ctx_1h["near_bull"] or ctx_1h["eql"]
            or ctx_15m["bull_fvg"] or ctx_15m["bull_sweep"] or ctx_15m["near_bull"] or ctx_15m["eql"]
        )
        resist = bool(
            ctx_1h["bear_fvg"] or ctx_1h["bear_sweep"] or ctx_1h["near_bear"] or ctx_1h["eqh"]
            or ctx_15m["bear_fvg"] or ctx_15m["bear_sweep"] or ctx_15m["near_bear"] or ctx_15m["eqh"]
        )
        structure = bool(ctx_1h["bos_up"] or ctx_1h["mss_up"] or ctx_15m["bos_up"] or ctx_15m["mss_up"])
        return support, resist, structure

    support = bool(
        ctx_1h["bear_fvg"] or ctx_1h["bear_sweep"] or ctx_1h["near_bear"] or ctx_1h["eqh"]
        or ctx_15m["bear_fvg"] or ctx_15m["bear_sweep"] or ctx_15m["near_bear"] or ctx_15m["eqh"]
    )
    resist = bool(
        ctx_1h["bull_fvg"] or ctx_1h["bull_sweep"] or ctx_1h["near_bull"] or ctx_1h["eql"]
        or ctx_15m["bull_fvg"] or ctx_15m["bull_sweep"] or ctx_15m["near_bull"] or ctx_15m["eql"]
    )
    structure = bool(ctx_1h["bos_down"] or ctx_1h["mss_down"] or ctx_15m["bos_down"] or ctx_15m["mss_down"])
    return support, resist, structure


def _failure_pressure(direction: str, latest_1h: dict, prev_1h: dict, ctx_1h: dict[str, Any], latest_15m: dict, prev_15m: dict, ctx_15m: dict[str, Any]) -> int:
    atr15 = _atr(latest_15m)
    close15 = _float(latest_15m.get("close"))
    prev_close15 = _float(prev_15m.get("close"))
    ema20_15 = _float(latest_15m.get("ema20"))

    if direction == "long":
        return _count(
            bool(ctx_15m["bear_sweep"] or ctx_15m["bos_down"] or ctx_15m["mss_down"]),
            bool(ctx_1h["bear_sweep"] or ctx_1h["bos_down"] or ctx_1h["mss_down"] or ctx_1h["eqh"]),
            _momentum_down(latest_15m, prev_15m),
            (not _momentum_up(latest_1h, prev_1h)) and _momentum_down(latest_1h, prev_1h),
            close15 < ema20_15,
            close15 < prev_close15,
            _upper_wick(latest_15m) >= atr15 * 0.18 and _body_ratio(latest_15m) < 0.55,
        )

    return _count(
        bool(ctx_15m["bull_sweep"] or ctx_15m["bos_up"] or ctx_15m["mss_up"]),
        bool(ctx_1h["bull_sweep"] or ctx_1h["bos_up"] or ctx_1h["mss_up"] or ctx_1h["eql"]),
        _momentum_up(latest_15m, prev_15m),
        (not _momentum_down(latest_1h, prev_1h)) and _momentum_up(latest_1h, prev_1h),
        close15 > ema20_15,
        close15 > prev_close15,
        _lower_wick(latest_15m) >= atr15 * 0.18 and _body_ratio(latest_15m) < 0.55,
    )


def _reversal_strength(direction: str, latest_1h: dict, prev_1h: dict, ctx_1h: dict[str, Any], latest_15m: dict, prev_15m: dict, ctx_15m: dict[str, Any], trigger_state: str) -> int:
    atr15 = _atr(latest_15m)
    if direction == "long":
        return _count(
            bool(ctx_15m["mss_up"] or ctx_15m["bos_up"]),
            bool(ctx_1h["mss_up"] or ctx_1h["bull_sweep"] or ctx_1h["eql"]),
            trigger_state == "confirm_long",
            _momentum_up(latest_15m, prev_15m),
            _momentum_up(latest_1h, prev_1h),
            _float(latest_15m.get("close")) > _float(latest_15m.get("ema20")) + atr15 * 0.05,
        )
    return _count(
        bool(ctx_15m["mss_down"] or ctx_15m["bos_down"]),
        bool(ctx_1h["mss_down"] or ctx_1h["bear_sweep"] or ctx_1h["eqh"]),
        trigger_state == "confirm_short",
        _momentum_down(latest_15m, prev_15m),
        _momentum_down(latest_1h, prev_1h),
        _float(latest_15m.get("close")) < _float(latest_15m.get("ema20")) - atr15 * 0.05,
    )


def _explosive_prep(direction: str, latest_1h: dict, latest_15m: dict, trigger_state: str, support_ctx: bool, heat_profile: dict[str, Any]) -> bool:
    if not support_ctx:
        return False

    heat_ok = bool(heat_profile["tai_rising_15m"] or heat_profile["tai_rising_1h"])
    if direction == "long":
        interpreter_ok = bool(latest_15m.get("fl_buy_signal") or latest_15m.get("sss_bull_div") or latest_15m.get("sss_oversold_warning"))
        return trigger_state in {"probing_long", "repairing_long", "confirm_long"} and (interpreter_ok or heat_ok)

    interpreter_ok = bool(latest_15m.get("fl_sell_signal") or latest_15m.get("sss_bear_div") or latest_15m.get("sss_overbought_warning"))
    return trigger_state in {"probing_short", "repairing_short", "confirm_short"} and (interpreter_ok or heat_ok)


def _directional_profile(
    direction: str,
    background_4h: str,
    latest_1h: dict,
    prev_1h: dict,
    ctx_1h: dict[str, Any],
    latest_15m: dict,
    prev_15m: dict,
    ctx_15m: dict[str, Any],
    trigger_state: str,
    heat_profile: dict[str, Any],
) -> dict[str, Any]:
    support_ctx, opposing_ctx, structure_ok = _directional_context(direction, ctx_1h, ctx_15m)
    failure = _failure_pressure(direction, latest_1h, prev_1h, ctx_1h, latest_15m, prev_15m, ctx_15m)
    reversal = _reversal_strength(direction, latest_1h, prev_1h, ctx_1h, latest_15m, prev_15m, ctx_15m, trigger_state)

    if direction == "long":
        bg_support = background_4h in {"bull", "lean_bull", "neutral"}
        bg_drive = background_4h in {"bull", "lean_bull"}
        momentum_1h = _momentum_up(latest_1h, prev_1h)
        momentum_15m = _momentum_up(latest_15m, prev_15m)
        ema_1h = _ema_alignment(latest_1h, "long")
        close_ok = _float(latest_15m.get("close")) >= _float(latest_15m.get("ema20"))
        interpreter = bool(latest_15m.get("fl_buy_signal") or latest_15m.get("sss_bull_div") or latest_15m.get("sss_oversold_warning"))
    else:
        bg_support = background_4h in {"bear", "lean_bear", "neutral"}
        bg_drive = background_4h in {"bear", "lean_bear"}
        momentum_1h = _momentum_down(latest_1h, prev_1h)
        momentum_15m = _momentum_down(latest_15m, prev_15m)
        ema_1h = _ema_alignment(latest_1h, "short")
        close_ok = _float(latest_15m.get("close")) <= _float(latest_15m.get("ema20"))
        interpreter = bool(latest_15m.get("fl_sell_signal") or latest_15m.get("sss_bear_div") or latest_15m.get("sss_overbought_warning"))

    drive_score = _count(
        bg_drive,
        structure_ok,
        ema_1h == "supportive",
        momentum_1h,
        momentum_15m,
        trigger_state.startswith("confirm_"),
        close_ok,
    ) - max(0, failure - 1)

    repair_score = _count(
        bg_support,
        support_ctx,
        ema_1h != "opposing",
        trigger_state in {f"repairing_{direction}", f"confirm_{direction}"},
        momentum_15m or interpreter,
        close_ok,
    ) - max(0, failure - 2)

    probe_score = _count(
        support_ctx,
        trigger_state in {f"probing_{direction}", f"repairing_{direction}", f"confirm_{direction}"},
        interpreter or heat_profile["tai_rising_15m"] or heat_profile["tai_rising_1h"],
        not opposing_ctx or reversal >= 2,
    ) - max(0, failure - 3)

    basis: list[str] = []
    if structure_ok:
        basis.append("structure")
    if support_ctx:
        basis.append("decision_zone")
    if ema_1h == "supportive":
        basis.append("ema_supportive")
    elif ema_1h == "mixed":
        basis.append("ema_mixed")
    if momentum_1h:
        basis.append("momo_1h")
    if momentum_15m:
        basis.append("momo_15m")
    if trigger_state.startswith("confirm_"):
        basis.append("trigger_confirm")
    elif trigger_state.startswith("repairing_"):
        basis.append("trigger_repair")
    elif trigger_state.startswith("probing_"):
        basis.append("trigger_probe")
    if interpreter:
        basis.append("interpreter")
    if heat_profile["tai_rising_15m"] or heat_profile["tai_rising_1h"]:
        basis.append("heat_rising")

    return {
        "direction": direction,
        "drive_score": drive_score,
        "repair_score": repair_score,
        "probe_score": probe_score,
        "failure_score": failure,
        "reversal_strength": reversal,
        "basis": basis,
        "explosive_prep": _explosive_prep(direction, latest_1h, latest_15m, trigger_state, support_ctx, heat_profile),
        "support_ctx": support_ctx,
        "opposing_ctx": opposing_ctx,
        "structure_ok": structure_ok,
    }


def _state_from_profile(direction: str, profile: dict[str, Any], trigger_state: str, heat_profile: dict[str, Any]) -> tuple[str, int]:
    drive = int(profile["drive_score"])
    repair = int(profile["repair_score"])
    probe = int(profile["probe_score"])
    failure = int(profile["failure_score"])

    budget = heat_profile["tai_budget_mode"]
    heat_1h = heat_profile["tai_heat_1h"]

    if drive >= 5 and trigger_state.startswith("confirm_") and failure <= 2 and not (budget in {"restricted", "frozen"} and heat_1h == "cold"):
        return f"trend_drive_{direction}", drive

    if repair >= 4 and failure <= 3 and not (budget == "frozen"):
        return f"repair_{direction}", repair

    if probe >= 3 and profile["explosive_prep"]:
        return f"probe_{direction}", probe

    return "range_neutral", max(drive, repair, probe)


def _select_main_state(
    long_state: tuple[str, int],
    short_state: tuple[str, int],
    long_profile: dict[str, Any],
    short_profile: dict[str, Any],
    heat_profile: dict[str, Any],
) -> tuple[str, int, str]:
    long_name, long_score = long_state
    short_name, short_score = short_state
    budget = heat_profile["tai_budget_mode"]

    if long_name == "range_neutral" and short_name == "range_neutral":
        return "range_neutral", 0, "no_locked_state"

    if long_name != "range_neutral" and short_name != "range_neutral":
        spread = abs(long_score - short_score)
        if budget in {"restricted", "frozen"}:
            # low heat: no easy direction switching or dual ownership
            if spread < 2 or max(long_profile["reversal_strength"], short_profile["reversal_strength"]) < 3:
                return "range_neutral", max(long_score, short_score), "dual_conflict_restricted"
        else:
            if spread <= 1:
                return "range_neutral", max(long_score, short_score), "dual_conflict_normal"

    if long_name == "range_neutral":
        return short_name, short_score, "short_only"
    if short_name == "range_neutral":
        return long_name, long_score, "long_only"

    if long_score > short_score:
        return long_name, long_score, "long_stronger"
    if short_score > long_score:
        return short_name, short_score, "short_stronger"

    return "range_neutral", max(long_score, short_score), "score_tie"


def _signal_from_state(state_1h: str) -> tuple[str | None, str | None]:
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


def _phase_rank_from_state(state_1h: str) -> int:
    if state_1h.startswith("trend_drive_"):
        return 3
    if state_1h.startswith("repair_"):
        return 2
    if state_1h.startswith("probe_"):
        return 1
    return 0


def _phase_anchor(symbol: str, state_1h: str, background_4h_direction: str, trigger_15m_state: str, heat_1h: str) -> str:
    trigger_bucket = "idle"
    if trigger_15m_state.startswith("confirm_"):
        trigger_bucket = "confirm"
    elif trigger_15m_state.startswith("repairing_"):
        trigger_bucket = "repair"
    elif trigger_15m_state.startswith("probing_"):
        trigger_bucket = "probe"
    return "|".join([symbol, state_1h, background_4h_direction, trigger_bucket, heat_1h])


def _signal_confidence(
    signal_name: str,
    state_1h: str,
    candidate_score: int,
    trigger_15m_state: str,
    structure_basis: list[str],
    heat_profile: dict[str, Any],
    background_4h_direction: str,
) -> int:
    phase_rank = _phase_rank_from_state(state_1h)
    score = {3: 70, 2: 63, 1: 54}.get(phase_rank, 50)
    score += min(8, max(0, candidate_score - 2) * 2)
    score += min(8, len(structure_basis) * 2)

    if trigger_15m_state.startswith("confirm_"):
        score += 5
    elif trigger_15m_state.startswith("repairing_"):
        score += 2
    elif trigger_15m_state == "idle":
        score -= 4

    if background_4h_direction in {"bull", "bear"}:
        score += 4
    elif background_4h_direction == "neutral":
        score -= 3

    budget = heat_profile["tai_budget_mode"]
    if budget == "restricted":
        score -= 6
    elif budget == "frozen":
        score -= 10

    score = max(45, min(88, score))
    return int(score)


def _signal_dict(
    *,
    name: str,
    symbol: str,
    direction: str,
    price: float,
    state_1h: str,
    zone_low: float,
    zone_high: float,
    structure_basis: list[str],
    background_4h_direction: str,
    trigger_15m_state: str,
    heat_profile: dict[str, Any],
    candidate_score: int,
    reversal_strength: int,
) -> dict[str, Any]:
    priority = SIGNAL_CLASS[name]
    phase_name = _phase_name_from_state(state_1h)
    phase_rank = _phase_rank_from_state(state_1h)
    heat_1h = heat_profile["tai_heat_1h"]

    if phase_rank == 3:
        eta_min, eta_max, cooldown_seconds = 15, 135, 40 * 60
    elif phase_rank == 2:
        eta_min, eta_max, cooldown_seconds = 25, 165, 45 * 60
    else:
        eta_min, eta_max, cooldown_seconds = 25, 180, 60 * 60

    return {
        "signal": name,
        "symbol": symbol,
        "timeframe": "15m",
        "priority": priority,
        "direction": direction,
        "price": price,
        "trend_1h": state_1h,
        "status": "active" if priority <= 2 else "early",
        "zone_low": round(zone_low, 2),
        "zone_high": round(zone_high, 2),
        "structure_basis": structure_basis,
        "eta_min_minutes": eta_min,
        "eta_max_minutes": eta_max,
        "cooldown_seconds": cooldown_seconds,
        "phase_rank": phase_rank,
        "stage_rank": phase_rank,
        "phase_name": phase_name,
        "phase_context": f"{state_1h}|{background_4h_direction}|{trigger_15m_state}|{heat_1h}",
        "phase_anchor": _phase_anchor(symbol, state_1h, background_4h_direction, trigger_15m_state, heat_1h),
        "trigger_state": trigger_15m_state,
        "background_4h_direction": background_4h_direction,
        "state_1h": state_1h,
        "trigger_15m_state": trigger_15m_state,
        "tai_heat_1h": heat_1h,
        "tai_heat_15m": heat_profile["tai_heat_15m"],
        "tai_heat_4h": heat_profile["tai_heat_4h"],
        "tai_budget_mode": heat_profile["tai_budget_mode"],
        "heat_restricted": heat_profile["tai_budget_mode"] in {"restricted", "frozen"},
        "freeze_mode": heat_profile["freeze_mode"],
        "h1_tai_bias": "support" if heat_1h in {"neutral", "warm", "hot"} else "flat",
        "h1_tai_slot": {"cold": "ice", "cool": "cool", "neutral": "mid", "warm": "warm", "hot": "hot"}.get(heat_1h, "mid"),
        "market_lock_key": f"{symbol}|15m",
        "reversal_strength": reversal_strength,
        "narrative_strength": candidate_score,
        "signature": f"{name}|{state_1h}|{direction}|{round(zone_low)}-{round(zone_high)}|{heat_1h}",
        "confidence_score": _signal_confidence(
            name, state_1h, candidate_score, trigger_15m_state, structure_basis, heat_profile, background_4h_direction
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

    heat_profile = _cross_tf_heat_profile(latest_15m, latest_1h, latest_4h)
    background_4h = _background_4h_direction(klines_4h)

    trigger_long = _trigger_15m_state("long", latest_15m, prev_15m, ctx_15m)
    trigger_short = _trigger_15m_state("short", latest_15m, prev_15m, ctx_15m)

    long_profile = _directional_profile(
        "long", background_4h, latest_1h, prev_1h, ctx_1h, latest_15m, prev_15m, ctx_15m, trigger_long, heat_profile
    )
    short_profile = _directional_profile(
        "short", background_4h, latest_1h, prev_1h, ctx_1h, latest_15m, prev_15m, ctx_15m, trigger_short, heat_profile
    )

    long_state = _state_from_profile("long", long_profile, trigger_long, heat_profile)
    short_state = _state_from_profile("short", short_profile, trigger_short, heat_profile)

    state_1h, candidate_score, selection_reason = _select_main_state(
        long_state, short_state, long_profile, short_profile, heat_profile
    )

    if state_1h == "range_neutral":
        blocked = [selection_reason]
        if heat_profile["tai_budget_mode"] in {"restricted", "frozen"}:
            blocked.append("budget_range_restricted")
        return {
            "signals": [],
            "near_miss_signals": [],
            "background_4h_direction": background_4h,
            "state_1h": "range_neutral",
            "trigger_15m_state": "idle",
            "tai_budget_mode": heat_profile["tai_budget_mode"],
            "tai_heat_1h": heat_profile["tai_heat_1h"],
            "tai_heat_4h": heat_profile["tai_heat_4h"],
            "blocked_reasons": blocked,
        }

    signal_name, direction = _signal_from_state(state_1h)
    selected_profile = long_profile if direction == "long" else short_profile
    selected_trigger = trigger_long if direction == "long" else trigger_short

    budget = heat_profile["tai_budget_mode"]
    blocked: list[str] = []

    # Budget is a reasoned filter, not a dead mute.
    if budget == "frozen":
        # In frozen mode only rare explosive-prep probe is publishable.
        if not (state_1h.startswith("probe_") and selected_profile["explosive_prep"] and selected_profile["reversal_strength"] <= 2):
            blocked.append("frozen_requires_probe_prep")
    elif budget == "restricted":
        # In restricted mode A/B require clear background lock; probe requires prep and no dual fight.
        if state_1h.startswith("trend_drive_") and candidate_score < 6:
            blocked.append("restricted_drive_not_locked")
        if state_1h.startswith("repair_") and (candidate_score < 5 or not selected_profile["support_ctx"]):
            blocked.append("restricted_repair_not_locked")
        if state_1h.startswith("probe_") and not selected_profile["explosive_prep"]:
            blocked.append("restricted_probe_without_prep")

    if blocked:
        return {
            "signals": [],
            "near_miss_signals": [],
            "background_4h_direction": background_4h,
            "state_1h": state_1h,
            "trigger_15m_state": selected_trigger,
            "tai_budget_mode": heat_profile["tai_budget_mode"],
            "tai_heat_1h": heat_profile["tai_heat_1h"],
            "tai_heat_4h": heat_profile["tai_heat_4h"],
            "blocked_reasons": blocked,
        }

    atr15 = _atr(latest_15m)
    price = round(_float(latest_15m.get("close")), 2)

    if direction == "long":
        zone_low = min(
            _float(latest_15m.get("ema10")),
            _float(latest_15m.get("ema20")),
            _float(latest_15m.get("close")) - atr15 * 0.22,
        )
        zone_high = max(
            _float(latest_15m.get("ema10")),
            _float(latest_15m.get("ema20")),
            _float(latest_15m.get("close")) + atr15 * 0.10,
        )
    else:
        zone_low = min(
            _float(latest_15m.get("ema10")),
            _float(latest_15m.get("ema20")),
            _float(latest_15m.get("close")) - atr15 * 0.10,
        )
        zone_high = max(
            _float(latest_15m.get("ema10")),
            _float(latest_15m.get("ema20")),
            _float(latest_15m.get("close")) + atr15 * 0.22,
        )

    signal = _signal_dict(
        name=signal_name,
        symbol=symbol,
        direction=direction,
        price=price,
        state_1h=state_1h,
        zone_low=zone_low,
        zone_high=zone_high,
        structure_basis=selected_profile["basis"],
        background_4h_direction=background_4h,
        trigger_15m_state=selected_trigger,
        heat_profile=heat_profile,
        candidate_score=candidate_score,
        reversal_strength=selected_profile["reversal_strength"],
    )

    return {
        "signals": [signal],
        "near_miss_signals": [],
        "background_4h_direction": background_4h,
        "state_1h": state_1h,
        "trigger_15m_state": selected_trigger,
        "tai_budget_mode": heat_profile["tai_budget_mode"],
        "tai_heat_1h": heat_profile["tai_heat_1h"],
        "tai_heat_4h": heat_profile["tai_heat_4h"],
        "blocked_reasons": [],
    }
