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


def _short_exhausted_hard(
    k: dict,
    prev_k: dict,
    *,
    support_hint: bool = False,
    deep_extension: bool = False,
    h1_exhausted: bool = False,
) -> bool:
    eq_signal = bool(k.get("sss_bull_div")) or bool(k.get("sss_oversold_warning"))
    momentum_rebound = float(k.get("sss_hist", 0.0)) >= float(prev_k.get("sss_hist", 0.0)) and float(
        k.get("cm_hist", 0.0)
    ) >= float(prev_k.get("cm_hist", 0.0))
    return _count_true(eq_signal, momentum_rebound, support_hint, deep_extension, h1_exhausted) >= 3


def _long_overheat_hard(
    k: dict,
    prev_k: dict,
    *,
    resistance_hint: bool = False,
    deep_extension: bool = False,
    h1_overheat: bool = False,
) -> bool:
    eq_signal = bool(k.get("sss_bear_div")) or bool(k.get("sss_overbought_warning"))
    momentum_rollover = float(k.get("sss_hist", 0.0)) <= float(prev_k.get("sss_hist", 0.0)) and float(
        k.get("cm_hist", 0.0)
    ) <= float(prev_k.get("cm_hist", 0.0))
    return _count_true(eq_signal, momentum_rollover, resistance_hint, deep_extension, h1_overheat) >= 3


def _a_distance_ok(
    direction: str,
    *,
    price: float,
    ema20: float,
    atr: float,
    momentum_ok: bool,
    hard_exhausted: bool,
    liquidity_hint: bool,
) -> bool:
    distance = abs(price - ema20) / max(atr, 1e-9)
    if distance <= 1.60:
        return True
    if distance <= 2.85 and momentum_ok and not hard_exhausted and not liquidity_hint:
        return True
    if distance <= 3.35 and direction == "short" and momentum_ok and not hard_exhausted:
        return True
    return False


def _reclaim_confirmation_ready(
    latest: dict,
    prev: dict,
    recent: list[dict],
    atr: float,
    base_ready: bool,
    stack_ok: bool,
    zone_hint: bool,
) -> bool:
    highs = [float(k["high"]) for k in recent[:-1]] or [float(prev["high"])]
    lows = [float(k["low"]) for k in recent[:-1]] or [float(prev["low"])]
    higher_low = float(latest["low"]) >= min(lows) - atr * 0.10
    broke_minor_high = float(latest["high"]) >= max(highs) - atr * 0.08
    return base_ready or (stack_ok and ((higher_low and float(latest["close"]) >= float(prev["close"])) or broke_minor_high or zone_hint))


def _reject_confirmation_ready(
    latest: dict,
    prev: dict,
    recent: list[dict],
    atr: float,
    base_ready: bool,
    stack_ok: bool,
    zone_hint: bool,
) -> bool:
    highs = [float(k["high"]) for k in recent[:-1]] or [float(prev["high"])]
    lows = [float(k["low"]) for k in recent[:-1]] or [float(prev["low"])]
    lower_high = float(latest["high"]) <= max(highs) + atr * 0.10
    broke_minor_low = float(latest["low"]) <= min(lows) + atr * 0.08
    return base_ready or (stack_ok and ((lower_high and float(latest["close"]) <= float(prev["close"])) or broke_minor_low or zone_hint))


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


def _float_safe(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _round5(value: float) -> int:
    return int(round(value / 5.0) * 5)


def _clamp_minutes(value: float, low: int, high: int) -> int:
    return max(low, min(high, _round5(value)))


def _normalize_window(start_min: float, end_min: float, floor_start: int, ceil_end: int, min_gap: int = 25) -> tuple[int, int]:
    start = _clamp_minutes(start_min, floor_start, ceil_end - min_gap)
    end = _clamp_minutes(max(end_min, start + min_gap), start + min_gap, ceil_end)
    return start, end


def _volume_ratio(k: dict) -> float:
    volume = _float_safe(k.get("volume"), 0.0)
    baseline = max(_float_safe(k.get("vol_sma20"), 0.0), 1e-9)
    return volume / baseline if baseline > 0 else 1.0


def _distance_in_atr(price: float, anchor: float, atr: float) -> float:
    return abs(price - anchor) / max(atr, 1e-9)


def _zone_distance_in_atr(price: float, zone_low: float | None, zone_high: float | None, atr: float) -> float:
    if zone_low is None or zone_high is None:
        return 0.0
    low = min(float(zone_low), float(zone_high))
    high = max(float(zone_low), float(zone_high))
    if low <= price <= high:
        return 0.0
    if price < low:
        return (low - price) / max(atr, 1e-9)
    return (price - high) / max(atr, 1e-9)


def _event_age(last_index: int, event: dict[str, Any] | None, fallback: int = 8) -> int:
    if not event:
        return fallback
    trigger_index = int(event.get("trigger_index", last_index))
    return max(0, last_index - trigger_index)


def _basis_age(last_index: int, *events: dict[str, Any] | None) -> int:
    ages: list[int] = []
    for event in events:
        if not event:
            continue
        if "bars_ago" in event:
            ages.append(int(event["bars_ago"]))
        elif "trigger_index" in event:
            ages.append(max(0, last_index - int(event["trigger_index"])))
        elif "second_index" in event:
            ages.append(max(0, last_index - int(event["second_index"])))
        elif "index" in event:
            ages.append(max(0, last_index - int(event["index"])))
    return min(ages) if ages else 8


def _estimate_a_window(
    direction: str,
    latest: dict,
    prev: dict,
    regime_score: int,
    bos_event: dict[str, Any] | None,
    last_index: int,
) -> tuple[int, int]:
    atr = _atr(latest)
    price = float(latest["close"])
    vol_ratio = _volume_ratio(latest)
    ema10_dist = _distance_in_atr(price, float(latest["ema10"]), atr)
    ema20_dist = _distance_in_atr(price, float(latest["ema20"]), atr)
    bos_age = _event_age(last_index, bos_event, fallback=7)
    recent_drive = abs(price - float(prev["close"])) / max(atr, 1e-9)

    if direction == "long":
        momentum_score = _count_true(
            _momentum_up(latest),
            bool(latest.get("cm_hist_up")),
            float(latest.get("sss_hist", 0.0)) >= float(prev.get("sss_hist", 0.0)),
            bool(latest.get("tai_rising")),
            bool(latest.get("rar_trend_strong")),
        )
    else:
        momentum_score = _count_true(
            _momentum_down(latest),
            bool(latest.get("cm_hist_down")),
            float(latest.get("sss_hist", 0.0)) <= float(prev.get("sss_hist", 0.0)),
            not bool(latest.get("tai_rising")),
            bool(latest.get("rar_trend_strong")),
        )

    start = (
        15
        + ema10_dist * 7.5
        + bos_age * 7.0
        + max(0.0, 1.0 - vol_ratio) * 16.0
        - max(0.0, vol_ratio - 1.0) * 11.0
        - momentum_score * 4.5
        - max(0, regime_score - 4) * 2.5
        - recent_drive * 4.0
    )
    end = (
        135
        + ema20_dist * 26.0
        + bos_age * 16.0
        + max(0.0, 1.0 - vol_ratio) * 42.0
        - max(0.0, vol_ratio - 1.0) * 18.0
        - momentum_score * 8.0
        - max(0, regime_score - 4) * 5.0
        - recent_drive * 8.0
    )
    return _normalize_window(start, end, floor_start=10, ceil_end=210)


def _estimate_b_window(
    direction: str,
    latest: dict,
    prev: dict,
    regime_score: int,
    zone_low: float | None,
    zone_high: float | None,
    basis_count: int,
    basis_age: int,
    reclaim_or_reject_ready: bool,
    near_ema10: bool,
) -> tuple[int, int]:
    atr = _atr(latest)
    price = float(latest["close"])
    vol_ratio = _volume_ratio(latest)
    zone_distance = _zone_distance_in_atr(price, zone_low, zone_high, atr)
    ema20_dist = _distance_in_atr(price, float(latest["ema20"]), atr)

    if direction == "long":
        momentum_score = _count_true(
            _momentum_up(latest),
            bool(latest.get("fl_buy_signal")) or float(latest.get("fl_trend", 0.0)) >= 0,
            bool(latest.get("tai_rising")),
            float(latest.get("sss_hist", 0.0)) >= float(prev.get("sss_hist", 0.0)),
        )
    else:
        momentum_score = _count_true(
            _momentum_down(latest),
            bool(latest.get("fl_sell_signal")) or float(latest.get("fl_trend", 0.0)) <= 0,
            not bool(latest.get("tai_rising")),
            float(latest.get("sss_hist", 0.0)) <= float(prev.get("sss_hist", 0.0)),
        )

    start = (
        20
        + zone_distance * 12.0
        + ema20_dist * 4.0
        + basis_age * 9.0
        + max(0.0, 1.0 - vol_ratio) * 15.0
        - max(0.0, vol_ratio - 1.0) * 8.0
        - basis_count * 5.5
        - momentum_score * 4.0
        - (7.0 if reclaim_or_reject_ready else 0.0)
        - (6.0 if near_ema10 else 0.0)
        - max(0, regime_score - 2) * 2.0
    )
    end = (
        190
        + zone_distance * 36.0
        + basis_age * 22.0
        + max(0.0, 1.0 - vol_ratio) * 48.0
        - max(0.0, vol_ratio - 1.0) * 18.0
        - basis_count * 10.0
        - momentum_score * 8.0
        - (14.0 if reclaim_or_reject_ready else 0.0)
        - (10.0 if near_ema10 else 0.0)
        - max(0, regime_score - 2) * 4.0
    )
    return _normalize_window(start, end, floor_start=15, ceil_end=300)


def _estimate_c_window(
    direction: str,
    latest: dict,
    prev: dict,
    regime_score: int,
    anchor_price: float | None,
    basis_count: int,
    basis_age: int,
    confirmation_score: int,
) -> tuple[int, int]:
    atr = _atr(latest)
    price = float(latest["close"])
    vol_ratio = _volume_ratio(latest)
    anchor_distance = _distance_in_atr(price, anchor_price, atr) if anchor_price is not None else 0.85

    start = (
        35
        + anchor_distance * 10.0
        + basis_age * 11.0
        + max(0.0, 1.0 - vol_ratio) * 18.0
        - max(0.0, vol_ratio - 1.0) * 7.0
        - basis_count * 4.5
        - confirmation_score * 4.5
        - max(0, regime_score) * 2.0
    )
    end = (
        245
        + anchor_distance * 30.0
        + basis_age * 24.0
        + max(0.0, 1.0 - vol_ratio) * 52.0
        - max(0.0, vol_ratio - 1.0) * 16.0
        - basis_count * 10.0
        - confirmation_score * 9.0
        - max(0, regime_score) * 5.0
    )
    return _normalize_window(start, end, floor_start=25, ceil_end=360)


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


def _classify_tf_phase(
    direction: str,
    trend_label: str,
    latest: dict,
    prev: dict,
    *,
    bos_event: dict[str, Any] | None,
    mss_event: dict[str, Any] | None,
    support_fvg_fill: dict[str, Any] | None,
    resistance_fvg_fill: dict[str, Any] | None,
    support_sweep: dict[str, Any] | None,
    resistance_sweep: dict[str, Any] | None,
    near_support: dict[str, Any] | None,
    near_resistance: dict[str, Any] | None,
    eql: dict[str, Any] | None,
    eqh: dict[str, Any] | None,
) -> str:
    close_pos = _close_position(latest)

    if direction == "long":
        trend_ok = trend_label in {"bull", "lean_bull"}
        structure_ok = bool(bos_event or mss_event)
        stack_ok = float(latest["close"]) >= float(latest["ema20"]) and float(latest["ema10"]) >= float(latest["ema20"])
        momentum_ok = _momentum_up(latest)
        support_working = _count_true(bool(near_support), bool(support_sweep), bool(eql), bool(support_fvg_fill))
        overhead_pressure = _count_true(bool(near_resistance), bool(resistance_sweep), bool(eqh), bool(resistance_fvg_fill))
        reclaiming_back_down = _count_true(
            float(latest["close"]) < float(latest["ema10"]),
            float(latest["close"]) < float(prev["close"]),
            close_pos < 0.48,
        )
        if trend_ok and structure_ok and stack_ok and momentum_ok and overhead_pressure == 0 and reclaiming_back_down == 0:
            return "continuation"
        if trend_ok and _count_true(structure_ok, stack_ok, momentum_ok, support_working >= 1) >= 2:
            return "mixed"
        return "counter"

    trend_ok = trend_label in {"bear", "lean_bear"}
    structure_ok = bool(bos_event or mss_event)
    stack_ok = float(latest["close"]) <= float(latest["ema20"]) and float(latest["ema10"]) <= float(latest["ema20"])
    momentum_ok = _momentum_down(latest)
    support_absorption = _count_true(bool(near_support), bool(support_sweep), bool(eql), bool(support_fvg_fill))
    overhead_pressure = _count_true(bool(near_resistance), bool(resistance_sweep), bool(eqh), bool(resistance_fvg_fill))
    reclaiming_back_up = _count_true(
        float(latest["close"]) > float(latest["ema10"]),
        float(latest["close"]) > float(prev["close"]),
        close_pos > 0.52,
    )
    if trend_ok and structure_ok and stack_ok and momentum_ok and support_absorption == 0 and reclaiming_back_up == 0:
        return "continuation"
    if trend_ok and _count_true(structure_ok, stack_ok, momentum_ok, overhead_pressure >= 1) >= 2:
        return "mixed"
    return "counter"


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
    eta_min_minutes: int | None = None,
    eta_max_minutes: int | None = None,
) -> dict[str, Any]:
    basis = structure_basis or []
    zone_low_v = zone_low if zone_low is not None else price
    zone_high_v = zone_high if zone_high is not None else price
    zone_key = f"{_round5(zone_low_v)}-{_round5(zone_high_v)}"
    basis_key = ",".join(sorted(basis)) if basis else "na"
    signature = f"{name}:{direction}:{zone_key}:{basis_key}"
    cooldown_seconds = {1: 45 * 60, 2: 30 * 60, 3: 25 * 60}.get(SIGNAL_PRIORITY[name], 30 * 60)
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
        "structure_basis": basis,
        "eta_min_minutes": eta_min_minutes,
        "eta_max_minutes": eta_max_minutes,
        "signature": signature,
        "cooldown_seconds": cooldown_seconds,
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
    last_index_15m = len(klines_15m) - 1

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

    h1_equal_levels = detect_recent_equal_levels(klines_1h)
    h1_eqh = h1_equal_levels.get("eqh")
    h1_eql = h1_equal_levels.get("eql")
    h1_bull_fvg_fill = detect_recent_fvg_fill(klines_1h, "bull")
    h1_bear_fvg_fill = detect_recent_fvg_fill(klines_1h, "bear")
    h1_bull_sweep = detect_recent_liquidity_sweep(klines_1h, "bull")
    h1_bear_sweep = detect_recent_liquidity_sweep(klines_1h, "bear")
    h1_near_bull_pivot = detect_near_pivot_level(klines_1h, "bull")
    h1_near_bear_pivot = detect_near_pivot_level(klines_1h, "bear")
    h1_last_bos_up = latest_structure_event(klines_1h, direction="up", kinds=("bos",), max_bars_ago=6)
    h1_last_bos_down = latest_structure_event(klines_1h, direction="down", kinds=("bos",), max_bars_ago=6)
    h1_last_mss_up = latest_structure_event(klines_1h, direction="up", kinds=("mss",), max_bars_ago=8)
    h1_last_mss_down = latest_structure_event(klines_1h, direction="down", kinds=("mss",), max_bars_ago=8)

    h4_equal_levels = detect_recent_equal_levels(klines_4h)
    h4_eqh = h4_equal_levels.get("eqh")
    h4_eql = h4_equal_levels.get("eql")
    h4_bull_fvg_fill = detect_recent_fvg_fill(klines_4h, "bull")
    h4_bear_fvg_fill = detect_recent_fvg_fill(klines_4h, "bear")
    h4_bull_sweep = detect_recent_liquidity_sweep(klines_4h, "bull")
    h4_bear_sweep = detect_recent_liquidity_sweep(klines_4h, "bear")
    h4_near_bull_pivot = detect_near_pivot_level(klines_4h, "bull")
    h4_near_bear_pivot = detect_near_pivot_level(klines_4h, "bear")
    h4_last_bos_up = latest_structure_event(klines_4h, direction="up", kinds=("bos",), max_bars_ago=4)
    h4_last_bos_down = latest_structure_event(klines_4h, direction="down", kinds=("bos",), max_bars_ago=4)
    h4_last_mss_up = latest_structure_event(klines_4h, direction="up", kinds=("mss",), max_bars_ago=6)
    h4_last_mss_down = latest_structure_event(klines_4h, direction="down", kinds=("mss",), max_bars_ago=6)

    h1_long_phase = _classify_tf_phase(
        "long",
        trend_1h,
        k_1h,
        p_1h,
        bos_event=h1_last_bos_up,
        mss_event=h1_last_mss_up,
        support_fvg_fill=h1_bull_fvg_fill,
        resistance_fvg_fill=h1_bear_fvg_fill,
        support_sweep=h1_bull_sweep,
        resistance_sweep=h1_bear_sweep,
        near_support=h1_near_bull_pivot,
        near_resistance=h1_near_bear_pivot,
        eql=h1_eql,
        eqh=h1_eqh,
    )
    h1_short_phase = _classify_tf_phase(
        "short",
        trend_1h,
        k_1h,
        p_1h,
        bos_event=h1_last_bos_down,
        mss_event=h1_last_mss_down,
        support_fvg_fill=h1_bull_fvg_fill,
        resistance_fvg_fill=h1_bear_fvg_fill,
        support_sweep=h1_bull_sweep,
        resistance_sweep=h1_bear_sweep,
        near_support=h1_near_bull_pivot,
        near_resistance=h1_near_bear_pivot,
        eql=h1_eql,
        eqh=h1_eqh,
    )
    h4_long_phase = _classify_tf_phase(
        "long",
        trend_4h,
        k_4h,
        p_4h,
        bos_event=h4_last_bos_up,
        mss_event=h4_last_mss_up,
        support_fvg_fill=h4_bull_fvg_fill,
        resistance_fvg_fill=h4_bear_fvg_fill,
        support_sweep=h4_bull_sweep,
        resistance_sweep=h4_bear_sweep,
        near_support=h4_near_bull_pivot,
        near_resistance=h4_near_bear_pivot,
        eql=h4_eql,
        eqh=h4_eqh,
    )
    h4_short_phase = _classify_tf_phase(
        "short",
        trend_4h,
        k_4h,
        p_4h,
        bos_event=h4_last_bos_down,
        mss_event=h4_last_mss_down,
        support_fvg_fill=h4_bull_fvg_fill,
        resistance_fvg_fill=h4_bear_fvg_fill,
        support_sweep=h4_bull_sweep,
        resistance_sweep=h4_bear_sweep,
        near_support=h4_near_bull_pivot,
        near_resistance=h4_near_bear_pivot,
        eql=h4_eql,
        eqh=h4_eqh,
    )

    bullish_stack = _price_above_stack(latest)
    bearish_stack = _price_below_stack(latest)
    momentum_up = _momentum_up(latest)
    momentum_down = _momentum_down(latest)
    rar_support = _rar_supportive(latest, prev)
    eq_long = _eq_div_long(latest, prev)
    eq_short = _eq_div_short(latest, prev)

    long_liquidity_hint = bool(bear_sweep) or bool(near_bear_pivot) or bool(eqh)
    short_liquidity_hint = bool(bull_sweep) or bool(near_bull_pivot) or bool(eql)
    long_overheat_hard = _long_overheat_hard(
        latest,
        prev,
        resistance_hint=long_liquidity_hint,
        deep_extension=(price - float(latest["ema20"])) >= atr * 2.20,
        h1_overheat=_long_overheat(k_1h, p_1h),
    )
    short_exhausted_hard = _short_exhausted_hard(
        latest,
        prev,
        support_hint=short_liquidity_hint,
        deep_extension=(float(latest["ema20"]) - price) >= atr * 2.20,
        h1_exhausted=_short_exhausted(k_1h, p_1h),
    )
    a_long_distance_ok = _a_distance_ok(
        "long",
        price=price,
        ema20=float(latest["ema20"]),
        atr=atr,
        momentum_ok=momentum_up,
        hard_exhausted=long_overheat_hard,
        liquidity_hint=long_liquidity_hint,
    )
    a_short_distance_ok = _a_distance_ok(
        "short",
        price=price,
        ema20=float(latest["ema20"]),
        atr=atr,
        momentum_ok=momentum_down,
        hard_exhausted=short_exhausted_hard,
        liquidity_hint=short_liquidity_hint,
    )

    close_pos = _close_position(latest)
    long_reclaim = price >= float(latest["ema10"]) and (price > float(prev["close"]) or close_pos >= 0.52)
    short_reject = price <= float(latest["ema10"]) and (price < float(prev["close"]) or close_pos <= 0.48)
    near_ema10 = abs(price - float(latest["ema10"])) <= atr * 1.20

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

    a_long_basis = ["h4_continuation", "h1_continuation"]
    if last_bos_up:
        a_long_basis.append("bos_up_15m")
    if last_mss_up:
        a_long_basis.append("mss_up_15m")

    a_short_basis = ["h4_continuation", "h1_continuation"]
    if last_bos_down:
        a_short_basis.append("bos_down_15m")
    if last_mss_down:
        a_short_basis.append("mss_down_15m")

    b_long_reclaim_ready = _reclaim_confirmation_ready(
        latest,
        prev,
        klines_15m[-4:],
        atr,
        long_reclaim,
        bullish_stack or price >= float(latest["ema10"]),
        bool(bull_fvg_fill) or bool(bull_sweep) or bool(last_mss_up),
    )
    b_short_reject_ready = _reject_confirmation_ready(
        latest,
        prev,
        klines_15m[-4:],
        atr,
        short_reject,
        bearish_stack or price <= float(latest["ema10"]),
        bool(bear_fvg_fill) or bool(bear_sweep) or bool(last_mss_down),
    )

    b_long_htf_allowed = h4_long_phase != "counter" and h1_long_phase != "counter" and long_regime_score >= 0
    b_short_htf_allowed = h4_short_phase != "counter" and h1_short_phase != "counter" and short_regime_score >= 0

    signals: list[dict[str, Any]] = []
    near_miss_signals: list[dict[str, Any]] = []
    blocked_counter: Counter = Counter()

    a_long_checks = {
        "htf_phase_long": h4_long_phase == "continuation" and h1_long_phase == "continuation",
        "recent_bos_up": bool(last_bos_up),
        "price_above_ema_stack": bullish_stack,
        "momentum_supportive": momentum_up,
        "rar_not_weak": rar_support,
        "not_eq_overheat_long": not long_overheat_hard,
        "not_too_far_from_ema20": a_long_distance_ok,
    }
    if _evaluate_branch("A_LONG", a_long_checks, near_miss_signals, blocked_counter):
        eta_min, eta_max = _estimate_a_window("long", latest, prev, long_regime_score, last_bos_up, last_index_15m)
        signals.append(
            _signal_dict(
                "A_LONG",
                symbol,
                "long",
                price,
                trend_display_long,
                "active",
                structure_basis=a_long_basis,
                eta_min_minutes=eta_min,
                eta_max_minutes=eta_max,
            )
        )

    a_short_checks = {
        "htf_phase_short": h4_short_phase == "continuation" and h1_short_phase == "continuation",
        "recent_bos_down": bool(last_bos_down),
        "price_below_ema_stack": bearish_stack,
        "momentum_supportive": momentum_down,
        "rar_not_weak": rar_support,
        "not_eq_exhausted_short": not short_exhausted_hard,
        "not_too_far_from_ema20": a_short_distance_ok,
    }
    if _evaluate_branch("A_SHORT", a_short_checks, near_miss_signals, blocked_counter):
        eta_min, eta_max = _estimate_a_window("short", latest, prev, short_regime_score, last_bos_down, last_index_15m)
        signals.append(
            _signal_dict(
                "A_SHORT",
                symbol,
                "short",
                price,
                trend_display_short,
                "active",
                structure_basis=a_short_basis,
                eta_min_minutes=eta_min,
                eta_max_minutes=eta_max,
            )
        )

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
        "htf_phase_long": b_long_htf_allowed,
        "smc_ict_basis_long": bool(b_long_basis),
        "reclaim_confirmation": b_long_reclaim_ready,
        "ema_structure_intact": price >= float(latest["ema20"]) or float(latest["ema10"]) >= float(latest["ema20"]),
        "momentum_not_opposed": _count_true(momentum_up, bool(latest.get("fl_buy_signal")), bool(latest.get("tai_rising"))) >= 1,
        "not_eq_overheat_long": not long_overheat_hard,
        "near_working_area": near_ema10 or bool(bull_fvg_fill) or bool(bull_sweep),
    }
    if _evaluate_branch("B_PULLBACK_LONG", b_long_checks, near_miss_signals, blocked_counter):
        b_long_age = _basis_age(last_index_15m, bull_fvg_fill, bull_sweep, last_mss_up, eql)
        eta_min, eta_max = _estimate_b_window(
            "long",
            latest,
            prev,
            long_regime_score,
            b_long_zone_low,
            b_long_zone_high,
            len(b_long_basis),
            b_long_age,
            b_long_reclaim_ready,
            near_ema10,
        )
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
                eta_min_minutes=eta_min,
                eta_max_minutes=eta_max,
            )
        )

    b_short_checks = {
        "htf_phase_short": b_short_htf_allowed,
        "smc_ict_basis_short": bool(b_short_basis),
        "reject_confirmation": b_short_reject_ready,
        "ema_structure_intact": price <= float(latest["ema20"]) or float(latest["ema10"]) <= float(latest["ema20"]),
        "momentum_not_opposed": _count_true(momentum_down, bool(latest.get("fl_sell_signal")), bool(latest.get("tai_rising")) is False) >= 1,
        "not_eq_exhausted_short": not short_exhausted_hard,
        "near_working_area": near_ema10 or bool(bear_fvg_fill) or bool(bear_sweep),
    }
    if _evaluate_branch("B_PULLBACK_SHORT", b_short_checks, near_miss_signals, blocked_counter):
        b_short_age = _basis_age(last_index_15m, bear_fvg_fill, bear_sweep, last_mss_down, eqh)
        eta_min, eta_max = _estimate_b_window(
            "short",
            latest,
            prev,
            short_regime_score,
            b_short_zone_low,
            b_short_zone_high,
            len(b_short_basis),
            b_short_age,
            b_short_reject_ready,
            near_ema10,
        )
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
                eta_min_minutes=eta_min,
                eta_max_minutes=eta_max,
            )
        )

    c_long_checks = {
        "htf_c_long_allowed": long_regime_score >= -1 and trend_4h != "bear",
        "ict_smc_early_basis": len(c_long_basis) >= 2,
        "eq_divergence_long": eq_long,
        "early_confirmation_long": _count_true(momentum_up, rar_support, price >= float(prev["close"]), bool(latest.get("tai_rising"))) >= 2,
        "not_eq_overheat_long": not long_overheat_hard,
    }
    if _evaluate_branch("C_LEFT_LONG", c_long_checks, near_miss_signals, blocked_counter):
        c_long_anchor_candidates = [
            _float_safe((bull_sweep or {}).get("level"), 0.0) if bull_sweep else None,
            _float_safe((near_bull_pivot or {}).get("price"), 0.0) if near_bull_pivot else None,
            _float_safe((eql or {}).get("price"), 0.0) if eql else None,
        ]
        c_long_anchor = next((v for v in c_long_anchor_candidates if v is not None), None)
        c_long_age = _basis_age(last_index_15m, bull_sweep, near_bull_pivot, last_mss_up, eql)
        c_long_confirm = _count_true(eq_long, momentum_up, rar_support, price >= float(prev["close"]), bool(latest.get("tai_rising")))
        eta_min, eta_max = _estimate_c_window("long", latest, prev, long_regime_score, c_long_anchor, len(c_long_basis), c_long_age, c_long_confirm)
        signals.append(
            _signal_dict(
                "C_LEFT_LONG",
                symbol,
                "long",
                price,
                trend_display_long,
                "early",
                structure_basis=c_long_basis,
                eta_min_minutes=eta_min,
                eta_max_minutes=eta_max,
            )
        )

    c_short_checks = {
        "htf_c_short_allowed": short_regime_score >= -1 and trend_4h != "bull",
        "ict_smc_early_basis": len(c_short_basis) >= 2,
        "eq_divergence_short": eq_short,
        "early_confirmation_short": _count_true(momentum_down, rar_support, price <= float(prev["close"]), bool(latest.get("tai_rising")) is False) >= 2,
        "not_eq_exhausted_short": not short_exhausted_hard,
    }
    if _evaluate_branch("C_LEFT_SHORT", c_short_checks, near_miss_signals, blocked_counter):
        c_short_anchor_candidates = [
            _float_safe((bear_sweep or {}).get("level"), 0.0) if bear_sweep else None,
            _float_safe((near_bear_pivot or {}).get("price"), 0.0) if near_bear_pivot else None,
            _float_safe((eqh or {}).get("price"), 0.0) if eqh else None,
        ]
        c_short_anchor = next((v for v in c_short_anchor_candidates if v is not None), None)
        c_short_age = _basis_age(last_index_15m, bear_sweep, near_bear_pivot, last_mss_down, eqh)
        c_short_confirm = _count_true(eq_short, momentum_down, rar_support, price <= float(prev["close"]), bool(latest.get("tai_rising")) is False)
        eta_min, eta_max = _estimate_c_window("short", latest, prev, short_regime_score, c_short_anchor, len(c_short_basis), c_short_age, c_short_confirm)
        signals.append(
            _signal_dict(
                "C_LEFT_SHORT",
                symbol,
                "short",
                price,
                trend_display_short,
                "early",
                structure_basis=c_short_basis,
                eta_min_minutes=eta_min,
                eta_max_minutes=eta_max,
            )
        )

    return {
        "signals": _pick_best_per_direction(signals),
        "near_miss_signals": near_miss_signals,
        "blocked_reasons": dict(blocked_counter),
    }
