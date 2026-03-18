from __future__ import annotations

from collections import Counter
from typing import Any

from engine.structure import (
    detect_last_bos,
    detect_last_mss,
    detect_near_pivot_level,
    detect_recent_equal_levels,
    detect_recent_fvg_fill,
    detect_recent_liquidity_sweep,
    find_pivots,
    higher_highs_lows,
    latest_structure_event,
    lower_highs_lows,
)


SIGNAL_PRIORITY = {
    "A_LONG": 1,
    "A_SHORT": 1,
    "B_PULLBACK_LONG": 2,
    "B_PULLBACK_SHORT": 2,
    "C_LEFT_LONG": 3,
    "C_LEFT_SHORT": 3,
}


def _count_true(*conds: bool) -> int:
    return sum(bool(c) for c in conds)


def _cross_up(curr_a: float, curr_b: float, prev_a: float, prev_b: float) -> bool:
    return curr_a > curr_b and prev_a <= prev_b


def _cross_down(curr_a: float, curr_b: float, prev_a: float, prev_b: float) -> bool:
    return curr_a < curr_b and prev_a >= prev_b


def _atr(k: dict) -> float:
    return max(float(k.get("atr", 0.0) or 0.0), abs(float(k["close"])) * 0.0012)


def _close_position(k: dict) -> float:
    rng = max(float(k["high"]) - float(k["low"]), 1e-9)
    return (float(k["close"]) - float(k["low"])) / rng


def _price_above_stack(k: dict) -> bool:
    return float(k["close"]) >= float(k["ema10"]) >= float(k["ema20"])


def _price_below_stack(k: dict) -> bool:
    return float(k["close"]) <= float(k["ema10"]) <= float(k["ema20"])


def _momentum_up(k: dict) -> bool:
    return bool(k.get("cm_macd_above_signal")) and (bool(k.get("cm_hist_up")) or float(k.get("sss_hist", 0.0)) >= 0)


def _momentum_down(k: dict) -> bool:
    return (not bool(k.get("cm_macd_above_signal"))) and (bool(k.get("cm_hist_down")) or float(k.get("sss_hist", 0.0)) <= 0)


def _rar_supportive(k: dict, prev_k: dict) -> bool:
    return bool(k.get("rar_trend_strong")) or float(k.get("rar_spread", 0.0)) <= float(prev_k.get("rar_spread", 0.0))


def _eq_div_long(k: dict, prev_k: dict) -> bool:
    return bool(k.get("sss_bull_div")) or bool(k.get("sss_oversold_warning")) or _cross_up(
        float(k.get("sss_macd_line", 0.0)),
        float(k.get("sss_signal_line", 0.0)),
        float(prev_k.get("sss_macd_line", 0.0)),
        float(prev_k.get("sss_signal_line", 0.0)),
    )


def _eq_div_short(k: dict, prev_k: dict) -> bool:
    return bool(k.get("sss_bear_div")) or bool(k.get("sss_overbought_warning")) or _cross_down(
        float(k.get("sss_macd_line", 0.0)),
        float(k.get("sss_signal_line", 0.0)),
        float(prev_k.get("sss_macd_line", 0.0)),
        float(prev_k.get("sss_signal_line", 0.0)),
    )


def _long_overheat(k: dict, prev_k: dict) -> bool:
    return bool(k.get("sss_bear_div")) or (
        bool(k.get("sss_overbought_warning"))
        and float(k.get("sss_hist", 0.0)) <= float(prev_k.get("sss_hist", 0.0))
        and float(k.get("cm_hist", 0.0)) <= float(prev_k.get("cm_hist", 0.0))
    )


def _short_exhausted(k: dict, prev_k: dict) -> bool:
    return bool(k.get("sss_bull_div")) or (
        bool(k.get("sss_oversold_warning"))
        and float(k.get("sss_hist", 0.0)) >= float(prev_k.get("sss_hist", 0.0))
        and float(k.get("cm_hist", 0.0)) >= float(prev_k.get("cm_hist", 0.0))
    )


def _trend_value(label: str, direction: str) -> int:
    table = {
        "bull": 2,
        "lean_bull": 1,
        "neutral": 0,
        "lean_bear": -1,
        "bear": -2,
    }
    value = table.get(label, 0)
    return value if direction == "long" else -value


# 4h/1h 仅做方向过滤，不允许辅助指标越级替代结构。
def classify_trend(klines: list[dict], structure_len: int = 12) -> str:
    if len(klines) < max(structure_len, 25):
        return "neutral"

    pivot_highs, pivot_lows = find_pivots(klines)
    bos = detect_last_bos(klines, pivot_highs, pivot_lows)
    mss = detect_last_mss(klines, pivot_highs, pivot_lows)
    k = klines[-1]

    bullish_structure = bos == "up" or mss == "up" or higher_highs_lows(klines, structure_len)
    bearish_structure = bos == "down" or mss == "down" or lower_highs_lows(klines, structure_len)

    if _price_above_stack(k) and bullish_structure and _momentum_up(k):
        if float(k["close"]) > float(k["ema120"]) and float(k["close"]) > float(k["ema169"]):
            return "bull"
        return "lean_bull"

    if _price_below_stack(k) and bearish_structure and _momentum_down(k):
        if float(k["close"]) < float(k["ema120"]) and float(k["close"]) < float(k["ema169"]):
            return "bear"
        return "lean_bear"

    if bullish_structure and float(k["close"]) >= float(k["ema20"]):
        return "lean_bull"
    if bearish_structure and float(k["close"]) <= float(k["ema20"]):
        return "lean_bear"
    return "neutral"


def _direction_regime_score(
    direction: str,
    trend_1d: str,
    trend_4h: str,
    trend_1h: str,
    k_4h: dict,
    p_4h: dict,
    k_1h: dict,
    p_1h: dict,
) -> int:
    score = 0
    score += _trend_value(trend_4h, direction) * 2
    score += _trend_value(trend_1h, direction) * 2
    score += _trend_value(trend_1d, direction)

    if direction == "long":
        score += 1 if float(k_1h["close"]) >= float(k_1h["ema20"]) else 0
        score += 1 if float(k_4h["close"]) >= float(k_4h["ema20"]) else 0
        score += 1 if _momentum_up(k_1h) else 0
        score += 1 if _momentum_up(k_4h) else 0
        score -= 2 if _long_overheat(k_1h, p_1h) else 0
        score -= 2 if _long_overheat(k_4h, p_4h) else 0
    else:
        score += 1 if float(k_1h["close"]) <= float(k_1h["ema20"]) else 0
        score += 1 if float(k_4h["close"]) <= float(k_4h["ema20"]) else 0
        score += 1 if _momentum_down(k_1h) else 0
        score += 1 if _momentum_down(k_4h) else 0
        score -= 2 if _short_exhausted(k_1h, p_1h) else 0
        score -= 2 if _short_exhausted(k_4h, p_4h) else 0

    return score


def _trend_display(direction: str, score: int) -> str:
    if direction == "long":
        if score >= 6:
            return "bull"
        if score >= 2:
            return "lean_bull"
        return "neutral"
    if score >= 6:
        return "bear"
    if score >= 2:
        return "lean_bear"
    return "neutral"


def _evaluate_branch(
    name: str,
    checks: dict[str, bool],
    near_miss_signals: list[dict[str, Any]],
    blocked_counter: Counter,
) -> bool:
    failed = [check_name for check_name, ok in checks.items() if not ok]
    if not failed:
        return True

    detail = {"candidate": name, "failed_checks": failed}
    if len(failed) <= 2:
        near_miss_signals.append(detail)
    else:
        for reason in failed:
            blocked_counter[f"{name}:{reason}"] += 1
    return False


def _pick_best_per_direction(signals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    best_by_direction: dict[str, dict[str, Any]] = {}
    for signal in signals:
        previous = best_by_direction.get(signal["direction"])
        if not previous or signal["priority"] < previous["priority"]:
            best_by_direction[signal["direction"]] = signal
    return sorted(best_by_direction.values(), key=lambda s: s["priority"])


def _signal_dict(
    name: str,
    symbol: str,
    direction: str,
    price: float,
    trend_display: str,
    status: str,
    zone_low: float | None = None,
    zone_high: float | None = None,
    structure_basis: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "signal": name,
        "symbol": symbol,
        "timeframe": "15m",
        "priority": SIGNAL_PRIORITY[name],
        "direction": direction,
        "price": price,
        "trend_1h": trend_display,
        "status": status,
        "zone_low": zone_low,
        "zone_high": zone_high,
        "structure_basis": structure_basis or [],
    }


def detect_signals(
    symbol: str,
    klines_1d: list[dict],
    klines_4h: list[dict],
    klines_1h: list[dict],
    klines_15m: list[dict],
) -> dict[str, Any]:
    trend_1d = classify_trend(klines_1d, structure_len=10)
    trend_4h = classify_trend(klines_4h, structure_len=12)
    trend_1h = classify_trend(klines_1h, structure_len=12)

    k_4h, p_4h = klines_4h[-1], klines_4h[-2]
    k_1h, p_1h = klines_1h[-1], klines_1h[-2]
    latest, prev = klines_15m[-1], klines_15m[-2]
    atr = _atr(latest)
    price = float(latest["close"])

    long_regime_score = _direction_regime_score("long", trend_1d, trend_4h, trend_1h, k_4h, p_4h, k_1h, p_1h)
    short_regime_score = _direction_regime_score("short", trend_1d, trend_4h, trend_1h, k_4h, p_4h, k_1h, p_1h)
    trend_display_long = _trend_display("long", long_regime_score)
    trend_display_short = _trend_display("short", short_regime_score)

    last_bos_up = latest_structure_event(klines_15m, direction="up", kinds=("bos",), max_bars_ago=6)
    last_bos_down = latest_structure_event(klines_15m, direction="down", kinds=("bos",), max_bars_ago=6)
    last_mss_up = latest_structure_event(klines_15m, direction="up", kinds=("mss",), max_bars_ago=8)
    last_mss_down = latest_structure_event(klines_15m, direction="down", kinds=("mss",), max_bars_ago=8)

    equal_levels = detect_recent_equal_levels(klines_15m)
    eqh = equal_levels.get("eqh")
    eql = equal_levels.get("eql")

    bull_fvg_fill = detect_recent_fvg_fill(klines_15m, "bull")
    bear_fvg_fill = detect_recent_fvg_fill(klines_15m, "bear")
    bull_sweep = detect_recent_liquidity_sweep(klines_15m, "bull")
    bear_sweep = detect_recent_liquidity_sweep(klines_15m, "bear")
    near_bull_pivot = detect_near_pivot_level(klines_15m, "bull")
    near_bear_pivot = detect_near_pivot_level(klines_15m, "bear")

    bullish_stack = _price_above_stack(latest)
    bearish_stack = _price_below_stack(latest)
    momentum_up = _momentum_up(latest)
    momentum_down = _momentum_down(latest)
    rar_support = _rar_supportive(latest, prev)
    eq_long = _eq_div_long(latest, prev)
    eq_short = _eq_div_short(latest, prev)
    long_overheat = _long_overheat(latest, prev) or _long_overheat(k_1h, p_1h)
    short_exhausted = _short_exhausted(latest, prev) or _short_exhausted(k_1h, p_1h)

    close_pos = _close_position(latest)
    long_reclaim = price >= float(latest["ema10"]) and (price > float(prev["close"]) or close_pos >= 0.52)
    short_reject = price <= float(latest["ema10"]) and (price < float(prev["close"]) or close_pos <= 0.48)
    near_ema10 = abs(price - float(latest["ema10"])) <= atr * 1.20
    not_far_from_ema20 = abs(price - float(latest["ema20"])) <= atr * 1.60

    eqh_then_bos_short = bool(eqh and last_bos_down and int(last_bos_down["trigger_index"]) >= int(eqh["second_index"]))
    eql_then_bos_long = bool(eql and last_bos_up and int(last_bos_up["trigger_index"]) >= int(eql["second_index"]))

    b_long_basis: list[str] = []
    if eql_then_bos_long:
        b_long_basis.append("eql_then_bos")
    if bull_fvg_fill:
        b_long_basis.append("bullish_fvg_fill")
    if bull_sweep:
        b_long_basis.append("sellside_sweep")
    if last_mss_up:
        b_long_basis.append("mss_up")

    b_short_basis: list[str] = []
    if eqh_then_bos_short:
        b_short_basis.append("eqh_then_bos")
    if bear_fvg_fill:
        b_short_basis.append("bearish_fvg_fill")
    if bear_sweep:
        b_short_basis.append("buyside_sweep")
    if last_mss_down:
        b_short_basis.append("mss_down")

    c_long_basis: list[str] = []
    if eq_long:
        c_long_basis.append("eq_div_long")
    if bull_sweep:
        c_long_basis.append("sellside_sweep")
    if near_bull_pivot:
        c_long_basis.append("near_support")
    if last_mss_up:
        c_long_basis.append("mss_up")

    c_short_basis: list[str] = []
    if eq_short:
        c_short_basis.append("eq_div_short")
    if bear_sweep:
        c_short_basis.append("buyside_sweep")
    if near_bear_pivot:
        c_short_basis.append("near_resistance")
    if last_mss_down:
        c_short_basis.append("mss_down")

    signals: list[dict[str, Any]] = []
    near_miss_signals: list[dict[str, Any]] = []
    blocked_counter: Counter = Counter()

    a_long_checks = {
        "htf_bias_long": long_regime_score >= 4 and short_regime_score < 7,
        "recent_bos_up": bool(last_bos_up),
        "price_above_ema_stack": bullish_stack,
        "momentum_supportive": momentum_up,
        "rar_not_weak": rar_support,
        "not_eq_overheat_long": not long_overheat,
        "not_too_far_from_ema20": not_far_from_ema20,
    }
    if _evaluate_branch("A_LONG", a_long_checks, near_miss_signals, blocked_counter):
        signals.append(_signal_dict("A_LONG", symbol, "long", price, trend_display_long, "active"))

    a_short_checks = {
        "htf_bias_short": short_regime_score >= 4 and long_regime_score < 7,
        "recent_bos_down": bool(last_bos_down),
        "price_below_ema_stack": bearish_stack,
        "momentum_supportive": momentum_down,
        "rar_not_weak": rar_support,
        "not_eq_exhausted_short": not short_exhausted,
        "not_too_far_from_ema20": not_far_from_ema20,
    }
    if _evaluate_branch("A_SHORT", a_short_checks, near_miss_signals, blocked_counter):
        signals.append(_signal_dict("A_SHORT", symbol, "short", price, trend_display_short, "active"))

    b_long_zone_low = None
    b_long_zone_high = None
    if bull_fvg_fill:
        b_long_zone_low = float(bull_fvg_fill["zone_low"])
        b_long_zone_high = float(bull_fvg_fill["zone_high"])
    elif bull_sweep:
        b_long_zone_low = float(bull_sweep["level"]) - atr * 0.10
        b_long_zone_high = float(latest["ema20"])

    b_short_zone_low = None
    b_short_zone_high = None
    if bear_fvg_fill:
        b_short_zone_low = float(bear_fvg_fill["zone_low"])
        b_short_zone_high = float(bear_fvg_fill["zone_high"])
    elif bear_sweep:
        b_short_zone_low = float(latest["ema20"])
        b_short_zone_high = float(bear_sweep["level"]) + atr * 0.10

    b_long_checks = {
        "htf_b_long_allowed": long_regime_score >= 1 and short_regime_score < 8,
        "smc_ict_basis_long": bool(b_long_basis),
        "reclaim_confirmation": long_reclaim,
        "ema_structure_intact": price >= float(latest["ema20"]) or float(latest["ema10"]) >= float(latest["ema20"]),
        "momentum_not_opposed": _count_true(momentum_up, bool(latest.get("fl_buy_signal")), bool(latest.get("tai_rising"))) >= 1,
        "not_eq_overheat_long": not long_overheat,
        "near_working_area": near_ema10 or bool(bull_fvg_fill) or bool(bull_sweep),
    }
    if _evaluate_branch("B_PULLBACK_LONG", b_long_checks, near_miss_signals, blocked_counter):
        signals.append(
            _signal_dict(
                "B_PULLBACK_LONG",
                symbol,
                "long",
                price,
                trend_display_long,
                "active",
                zone_low=b_long_zone_low,
                zone_high=b_long_zone_high,
                structure_basis=b_long_basis,
            )
        )

    b_short_checks = {
        "htf_b_short_allowed": short_regime_score >= 1 and long_regime_score < 8,
        "smc_ict_basis_short": bool(b_short_basis),
        "reject_confirmation": short_reject,
        "ema_structure_intact": price <= float(latest["ema20"]) or float(latest["ema10"]) <= float(latest["ema20"]),
        "momentum_not_opposed": _count_true(momentum_down, bool(latest.get("fl_sell_signal")), bool(latest.get("tai_rising")) is False) >= 1,
        "not_eq_exhausted_short": not short_exhausted,
        "near_working_area": near_ema10 or bool(bear_fvg_fill) or bool(bear_sweep),
    }
    if _evaluate_branch("B_PULLBACK_SHORT", b_short_checks, near_miss_signals, blocked_counter):
        signals.append(
            _signal_dict(
                "B_PULLBACK_SHORT",
                symbol,
                "short",
                price,
                trend_display_short,
                "active",
                zone_low=b_short_zone_low,
                zone_high=b_short_zone_high,
                structure_basis=b_short_basis,
            )
        )

    c_long_checks = {
        "htf_c_long_allowed": long_regime_score >= -1 and trend_4h != "bear",
        "ict_smc_early_basis": len(c_long_basis) >= 2,
        "eq_divergence_long": eq_long,
        "early_confirmation_long": _count_true(momentum_up, rar_support, price >= float(prev["close"]), bool(latest.get("tai_rising"))) >= 2,
        "not_eq_overheat_long": not long_overheat,
    }
    if _evaluate_branch("C_LEFT_LONG", c_long_checks, near_miss_signals, blocked_counter):
        signals.append(
            _signal_dict(
                "C_LEFT_LONG",
                symbol,
                "long",
                price,
                trend_display_long,
                "early",
                structure_basis=c_long_basis,
            )
        )

    c_short_checks = {
        "htf_c_short_allowed": short_regime_score >= -1 and trend_4h != "bull",
        "ict_smc_early_basis": len(c_short_basis) >= 2,
        "eq_divergence_short": eq_short,
        "early_confirmation_short": _count_true(momentum_down, rar_support, price <= float(prev["close"]), bool(latest.get("tai_rising")) is False) >= 2,
        "not_eq_exhausted_short": not short_exhausted,
    }
    if _evaluate_branch("C_LEFT_SHORT", c_short_checks, near_miss_signals, blocked_counter):
        signals.append(
            _signal_dict(
                "C_LEFT_SHORT",
                symbol,
                "short",
                price,
                trend_display_short,
                "early",
                structure_basis=c_short_basis,
            )
        )

    return {
        "signals": _pick_best_per_direction(signals),
        "near_miss_signals": near_miss_signals,
        "blocked_reasons": dict(blocked_counter),
    }
