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


# 这里只用于信号类型标识与下游展示，不再做 A > B > C 互斥筛选。
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


def _estimate_x_window(
    direction: str,
    latest: dict,
    prev: dict,
    trigger_level: float | None,
    regime_score: int,
) -> tuple[int, int]:
    atr = _atr(latest)
    price = float(latest["close"])
    vol_ratio = _volume_ratio(latest)
    trigger_distance = _distance_in_atr(price, trigger_level, atr) if trigger_level is not None else 0.45
    impulse = abs(price - float(prev["close"])) / max(atr, 1e-9)
    if direction == "long":
        momentum_score = _count_true(
            _momentum_up(latest),
            bool(latest.get("cm_hist_up")),
            bool(latest.get("tai_rising")),
            float(latest.get("sss_hist", 0.0)) >= float(prev.get("sss_hist", 0.0)),
        )
    else:
        momentum_score = _count_true(
            _momentum_down(latest),
            bool(latest.get("cm_hist_down")),
            not bool(latest.get("tai_rising")),
            float(latest.get("sss_hist", 0.0)) <= float(prev.get("sss_hist", 0.0)),
        )

    start = (
        5
        + trigger_distance * 6.0
        + max(0.0, 2.0 - vol_ratio) * 8.0
        - max(0.0, vol_ratio - 2.0) * 4.0
        - impulse * 4.5
        - momentum_score * 3.0
        - max(0, regime_score) * 1.0
    )
    end = (
        95
        + trigger_distance * 18.0
        + max(0.0, 2.0 - vol_ratio) * 20.0
        - max(0.0, vol_ratio - 2.0) * 10.0
        - impulse * 7.0
        - momentum_score * 5.0
        - max(0, regime_score) * 2.0
    )
    return _normalize_window(start, end, floor_start=5, ceil_end=120)


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
    trigger_level: float | None = None,
) -> dict[str, Any]:
    basis = structure_basis or []
    zone_low_v = zone_low if zone_low is not None else price
    zone_high_v = zone_high if zone_high is not None else price
    zone_key = f"{_round5(zone_low_v)}-{_round5(zone_high_v)}"
    basis_key = ",".join(sorted(basis)) if basis else "na"
    signature = f"{name}:{direction}:{zone_key}:{basis_key}"
    cooldown_seconds = {1: 45 * 60, 2: 30 * 60, 3: 25 * 60, 4: 20 * 60}.get(SIGNAL_CLASS[name], 30 * 60)
    return {
        "signal": name,
        "symbol": symbol,
        "timeframe": "15m",
        "priority": SIGNAL_CLASS[name],
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



def _stage_rank(signal_name: str) -> int:
    if signal_name.startswith("A_"):
        return 3
    if signal_name.startswith("B_"):
        return 2
    if signal_name.startswith("C_"):
        return 1
    return 0


def _background_context_4h(
    trend_4h: str,
    k_4h: dict,
    p_4h: dict,
    *,
    bos_up: dict[str, Any] | None,
    bos_down: dict[str, Any] | None,
    mss_up: dict[str, Any] | None,
    mss_down: dict[str, Any] | None,
    bull_fvg_fill: dict[str, Any] | None,
    bear_fvg_fill: dict[str, Any] | None,
    bull_sweep: dict[str, Any] | None,
    bear_sweep: dict[str, Any] | None,
    eql: dict[str, Any] | None,
    eqh: dict[str, Any] | None,
) -> dict[str, Any]:
    atr = _atr(k_4h)
    close = float(k_4h["close"])
    ema20 = float(k_4h["ema20"])

    resistance_hint = bool(near for near in (bear_sweep, bear_fvg_fill, eqh))
    support_hint = bool(near for near in (bull_sweep, bull_fvg_fill, eql))

    long_overheat = _long_overheat_hard(
        k_4h,
        p_4h,
        resistance_hint=resistance_hint,
        deep_extension=(close - ema20) >= atr * 2.3,
        h1_overheat=False,
    )
    short_exhausted = _short_exhausted_hard(
        k_4h,
        p_4h,
        support_hint=support_hint,
        deep_extension=(ema20 - close) >= atr * 2.3,
        h1_exhausted=False,
    )

    long_score = _count_true(
        trend_4h in {"bull", "lean_bull"},
        _price_above_stack(k_4h),
        close >= ema20,
        _momentum_up(k_4h),
        bool(bos_up or mss_up),
        not long_overheat,
    )
    short_score = _count_true(
        trend_4h in {"bear", "lean_bear"},
        _price_below_stack(k_4h),
        close <= ema20,
        _momentum_down(k_4h),
        bool(bos_down or mss_down),
        not short_exhausted,
    )

    if short_score >= long_score + 2 and short_score >= 4:
        direction = "short"
    elif long_score >= short_score + 2 and long_score >= 4:
        direction = "long"
    else:
        direction = "neutral"

    return {
        "direction": direction,
        "long_score": long_score,
        "short_score": short_score,
        "hard_counter_long": direction == "short" and short_score >= 5,
        "hard_counter_short": direction == "long" and long_score >= 5,
        "trend_label": trend_4h,
    }


def _h1_state(
    direction: str,
    trend_1h: str,
    k_1h: dict,
    p_1h: dict,
    *,
    bos_event: dict[str, Any] | None,
    mss_event: dict[str, Any] | None,
    bull_fvg_fill: dict[str, Any] | None,
    bear_fvg_fill: dict[str, Any] | None,
    bull_sweep: dict[str, Any] | None,
    bear_sweep: dict[str, Any] | None,
    near_bull_pivot: dict[str, Any] | None,
    near_bear_pivot: dict[str, Any] | None,
    eql: dict[str, Any] | None,
    eqh: dict[str, Any] | None,
    background: dict[str, Any],
) -> dict[str, Any]:
    atr = _atr(k_1h)
    close = float(k_1h["close"])
    ema10 = float(k_1h["ema10"])
    ema20 = float(k_1h["ema20"])
    prev_close = float(p_1h["close"])

    if direction == "long":
        overheat_hard = _long_overheat_hard(
            k_1h,
            p_1h,
            resistance_hint=bool(near_bear_pivot or bear_sweep or eqh),
            deep_extension=(close - ema20) >= atr * 2.2,
            h1_overheat=False,
        )
        continuation_score = _count_true(
            trend_1h in {"bull", "lean_bull"},
            _price_above_stack(k_1h),
            close >= ema20,
            _momentum_up(k_1h),
            bool(bos_event or mss_event),
            not overheat_hard,
        )
        repair_score = _count_true(
            bool(mss_event),
            bool(bull_fvg_fill or bull_sweep or near_bull_pivot or eql),
            close >= ema10 or close >= ema20 - atr * 0.30,
            _momentum_up(k_1h) or bool(k_1h.get("tai_rising")) or bool(k_1h.get("cm_hist_up")),
            _eq_div_long(k_1h, p_1h) or _rar_supportive(k_1h, p_1h) or close >= prev_close,
            not overheat_hard,
        )
        early_score = _count_true(
            bool(bull_sweep or near_bull_pivot or bull_fvg_fill or eql or mss_event),
            _eq_div_long(k_1h, p_1h) or bool(k_1h.get("sss_oversold_warning")),
            _rar_supportive(k_1h, p_1h) or bool(k_1h.get("tai_rising")) or close >= prev_close,
        )
        bias_score = max(continuation_score + 1, repair_score, early_score)
        bias_score += 1 if background["direction"] == "long" else 0
        bias_score -= 2 if background["hard_counter_long"] else 0
        if continuation_score >= 5 and not background["hard_counter_long"]:
            phase = "continuation"
        elif repair_score >= 4 and not background["hard_counter_long"]:
            phase = "repair"
        elif early_score >= 3 and (background["direction"] != "short" or repair_score >= 5):
            phase = "early"
        else:
            phase = "blocked"
        return {
            "direction": "long",
            "phase": phase,
            "bias_score": bias_score,
            "continuation_score": continuation_score,
            "repair_score": repair_score,
            "early_score": early_score,
            "blocked_by_background": background["hard_counter_long"],
        }

    exhausted_hard = _short_exhausted_hard(
        k_1h,
        p_1h,
        support_hint=bool(near_bull_pivot or bull_sweep or eql),
        deep_extension=(ema20 - close) >= atr * 2.2,
        h1_exhausted=False,
    )
    continuation_score = _count_true(
        trend_1h in {"bear", "lean_bear"},
        _price_below_stack(k_1h),
        close <= ema20,
        _momentum_down(k_1h),
        bool(bos_event or mss_event),
        not exhausted_hard,
    )
    repair_score = _count_true(
        bool(mss_event),
        bool(bear_fvg_fill or bear_sweep or near_bear_pivot or eqh),
        close <= ema10 or close <= ema20 + atr * 0.30,
        _momentum_down(k_1h) or (not bool(k_1h.get("tai_rising"))) or bool(k_1h.get("cm_hist_down")),
        _eq_div_short(k_1h, p_1h) or _rar_supportive(k_1h, p_1h) or close <= prev_close,
        not exhausted_hard,
    )
    early_score = _count_true(
        bool(bear_sweep or near_bear_pivot or bear_fvg_fill or eqh or mss_event),
        _eq_div_short(k_1h, p_1h) or bool(k_1h.get("sss_overbought_warning")),
        _rar_supportive(k_1h, p_1h) or (not bool(k_1h.get("tai_rising"))) or close <= prev_close,
    )
    bias_score = max(continuation_score + 1, repair_score, early_score)
    bias_score += 1 if background["direction"] == "short" else 0
    bias_score -= 2 if background["hard_counter_short"] else 0
    if continuation_score >= 5 and not background["hard_counter_short"]:
        phase = "continuation"
    elif repair_score >= 4 and not background["hard_counter_short"]:
        phase = "repair"
    elif early_score >= 3 and (background["direction"] != "long" or repair_score >= 5):
        phase = "early"
    else:
        phase = "blocked"
    return {
        "direction": "short",
        "phase": phase,
        "bias_score": bias_score,
        "continuation_score": continuation_score,
        "repair_score": repair_score,
        "early_score": early_score,
        "blocked_by_background": background["hard_counter_short"],
    }


def _pick_active_h1_state(long_state: dict[str, Any], short_state: dict[str, Any]) -> dict[str, Any]:
    if long_state["phase"] != "blocked" and long_state["bias_score"] >= short_state["bias_score"] + 2:
        return long_state
    if short_state["phase"] != "blocked" and short_state["bias_score"] >= long_state["bias_score"] + 2:
        return short_state

    if long_state["phase"] == "repair" and short_state["phase"] != "continuation" and long_state["bias_score"] >= short_state["bias_score"] + 1:
        return long_state
    if short_state["phase"] == "repair" and long_state["phase"] != "continuation" and short_state["bias_score"] >= long_state["bias_score"] + 1:
        return short_state

    if long_state["phase"] == "early" and short_state["phase"] == "blocked":
        return long_state
    if short_state["phase"] == "early" and long_state["phase"] == "blocked":
        return short_state

    return {"direction": "neutral", "phase": "blocked", "bias_score": 0}


def _build_c_zone(direction: str, price: float, atr: float, anchor: float | None, ema20: float) -> tuple[float, float]:
    base = anchor if anchor is not None else ema20
    if direction == "long":
        return (min(base - atr * 0.35, ema20 - atr * 0.10), max(price, ema20 + atr * 0.20))
    return (min(price, ema20 - atr * 0.20), max(base + atr * 0.35, ema20 + atr * 0.10))


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

    # 15m structure
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

    # 1h structure
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

    # 4h structure
    h4_equal_levels = detect_recent_equal_levels(klines_4h)
    h4_eqh = h4_equal_levels.get("eqh")
    h4_eql = h4_equal_levels.get("eql")
    h4_bull_fvg_fill = detect_recent_fvg_fill(klines_4h, "bull")
    h4_bear_fvg_fill = detect_recent_fvg_fill(klines_4h, "bear")
    h4_bull_sweep = detect_recent_liquidity_sweep(klines_4h, "bull")
    h4_bear_sweep = detect_recent_liquidity_sweep(klines_4h, "bear")
    h4_last_bos_up = latest_structure_event(klines_4h, direction="up", kinds=("bos",), max_bars_ago=4)
    h4_last_bos_down = latest_structure_event(klines_4h, direction="down", kinds=("bos",), max_bars_ago=4)
    h4_last_mss_up = latest_structure_event(klines_4h, direction="up", kinds=("mss",), max_bars_ago=6)
    h4_last_mss_down = latest_structure_event(klines_4h, direction="down", kinds=("mss",), max_bars_ago=6)

    background = _background_context_4h(
        trend_4h,
        k_4h,
        p_4h,
        bos_up=h4_last_bos_up,
        bos_down=h4_last_bos_down,
        mss_up=h4_last_mss_up,
        mss_down=h4_last_mss_down,
        bull_fvg_fill=h4_bull_fvg_fill,
        bear_fvg_fill=h4_bear_fvg_fill,
        bull_sweep=h4_bull_sweep,
        bear_sweep=h4_bear_sweep,
        eql=h4_eql,
        eqh=h4_eqh,
    )

    long_state = _h1_state(
        "long",
        trend_1h,
        k_1h,
        p_1h,
        bos_event=h1_last_bos_up,
        mss_event=h1_last_mss_up,
        bull_fvg_fill=h1_bull_fvg_fill,
        bear_fvg_fill=h1_bear_fvg_fill,
        bull_sweep=h1_bull_sweep,
        bear_sweep=h1_bear_sweep,
        near_bull_pivot=h1_near_bull_pivot,
        near_bear_pivot=h1_near_bear_pivot,
        eql=h1_eql,
        eqh=h1_eqh,
        background=background,
    )
    short_state = _h1_state(
        "short",
        trend_1h,
        k_1h,
        p_1h,
        bos_event=h1_last_bos_down,
        mss_event=h1_last_mss_down,
        bull_fvg_fill=h1_bull_fvg_fill,
        bear_fvg_fill=h1_bear_fvg_fill,
        bull_sweep=h1_bull_sweep,
        bear_sweep=h1_bear_sweep,
        near_bull_pivot=h1_near_bull_pivot,
        near_bear_pivot=h1_near_bear_pivot,
        eql=h1_eql,
        eqh=h1_eqh,
        background=background,
    )
    active_state = _pick_active_h1_state(long_state, short_state)

    near_miss_signals: list[dict[str, Any]] = []
    blocked_counter: Counter = Counter()
    signals: list[dict[str, Any]] = []

    if active_state["direction"] == "neutral":
        return {
            "signals": [],
            "near_miss_signals": [{"candidate": "NO_STAGE", "failed_checks": ["h1_bias_not_locked"]}],
            "blocked_reasons": {"NO_STAGE:h1_bias_not_locked": 1},
        }

    direction = active_state["direction"]
    trend_display = trend_display_long if direction == "long" else trend_display_short
    regime_score = long_regime_score if direction == "long" else short_regime_score
    latest_trend_score = long_regime_score if direction == "long" else short_regime_score
    vol_ratio_15m = _volume_ratio(latest)
    close_pos = _close_position(latest)

    if direction == "long":
        eq_div = _eq_div_long(latest, prev)
        hard_block = _long_overheat_hard(
            latest,
            prev,
            resistance_hint=bool(near_bear_pivot or bear_sweep or eqh),
            deep_extension=(price - float(latest["ema20"])) >= atr * 2.2,
            h1_overheat=active_state["phase"] == "blocked",
        )
        a_basis = [item for item in ("h1_long_continuation", "m15_bos_up" if last_bos_up else None, "m15_mss_up" if last_mss_up else None) if item]
        b_basis = [
            item for item in (
                "h1_long_repair",
                "bullish_fvg_fill" if bull_fvg_fill else None,
                "sellside_sweep" if bull_sweep else None,
                "near_support" if near_bull_pivot else None,
                "eql" if eql else None,
                "mss_up" if last_mss_up else None,
            ) if item
        ]
        c_basis = [
            item for item in (
                "left_long_watch",
                "eq_div_long" if eq_div else None,
                "sellside_sweep" if bull_sweep else None,
                "near_support" if near_bull_pivot else None,
                "eql" if eql else None,
                "mss_up" if last_mss_up else None,
            ) if item
        ]

        b_zone_low = None
        b_zone_high = None
        if bull_fvg_fill:
            b_zone_low = float(bull_fvg_fill["zone_low"])
            b_zone_high = float(bull_fvg_fill["zone_high"])
        elif bull_sweep:
            b_zone_low = float(bull_sweep["level"]) - atr * 0.10
            b_zone_high = float(latest["ema20"])
        elif near_bull_pivot:
            b_zone_low = float(near_bull_pivot["price"]) - atr * 0.10
            b_zone_high = float(latest["ema20"])

        reclaim_ready = _reclaim_confirmation_ready(
            latest,
            prev,
            klines_15m[-4:],
            atr,
            price >= float(latest["ema10"]) and (price > float(prev["close"]) or close_pos >= 0.52),
            _price_above_stack(latest) or price >= float(latest["ema10"]),
            bool(bull_fvg_fill or bull_sweep or near_bull_pivot or last_mss_up),
        )
        a_ready = _count_true(
            _price_above_stack(latest) or (price >= float(latest["ema10"]) and float(latest["ema10"]) >= float(latest["ema20"])),
            _momentum_up(latest),
            bool(last_bos_up or last_mss_up),
            vol_ratio_15m >= 0.90 or bool(latest.get("tai_rising")) or bool(latest.get("fl_buy_signal")),
            not hard_block,
        ) >= 4
        b_ready = _count_true(
            bool(b_basis) >= 1,
            reclaim_ready,
            price >= float(latest["ema20"]) or float(latest["ema10"]) >= float(latest["ema20"]),
            _momentum_up(latest) or bool(latest.get("tai_rising")) or bool(latest.get("fl_buy_signal")),
            not hard_block,
        ) >= 4
        c_ready = _count_true(
            bool(c_basis) >= 2,
            eq_div or bool(last_mss_up),
            _rar_supportive(latest, prev) or bool(latest.get("tai_rising")) or price >= float(prev["close"]),
            not background["hard_counter_long"],
        ) >= 3

        if active_state["phase"] == "continuation":
            checks = {
                "bg_not_hard_counter": not background["hard_counter_long"],
                "h1_continuation_locked": active_state["continuation_score"] >= 5,
                "m15_trigger_ready": a_ready,
                "not_overheated": not hard_block,
            }
            if _evaluate_branch("A_LONG", checks, near_miss_signals, blocked_counter):
                eta_min, eta_max = _estimate_a_window("long", latest, prev, regime_score, last_bos_up or last_mss_up, last_index_15m)
                sig = _signal_dict("A_LONG", symbol, "long", price, trend_display, "active", structure_basis=a_basis, eta_min_minutes=eta_min, eta_max_minutes=eta_max)
                sig["phase_group"] = "long_continuation"
                signals.append(sig)
        elif active_state["phase"] == "repair":
            checks = {
                "bg_not_hard_counter": not background["hard_counter_long"],
                "h1_repair_locked": active_state["repair_score"] >= 4,
                "m15_reclaim_ready": b_ready,
                "not_overheated": not hard_block,
            }
            if _evaluate_branch("B_PULLBACK_LONG", checks, near_miss_signals, blocked_counter):
                b_age = _basis_age(last_index_15m, bull_fvg_fill, bull_sweep, near_bull_pivot, last_mss_up, eql)
                eta_min, eta_max = _estimate_b_window("long", latest, prev, regime_score, b_zone_low, b_zone_high, len(b_basis), b_age, reclaim_ready, abs(price - float(latest["ema10"])) <= atr * 1.20)
                sig = _signal_dict("B_PULLBACK_LONG", symbol, "long", price, trend_display, "active", zone_low=b_zone_low, zone_high=b_zone_high, structure_basis=b_basis, eta_min_minutes=eta_min, eta_max_minutes=eta_max)
                sig["phase_group"] = "long_repair"
                signals.append(sig)
            elif c_ready:
                anchor = next((v for v in [float((bull_sweep or {}).get("level", 0.0)) if bull_sweep else None, float((near_bull_pivot or {}).get("price", 0.0)) if near_bull_pivot else None, float((eql or {}).get("price", 0.0)) if eql else None] if v is not None), None)
                c_zone_low, c_zone_high = _build_c_zone("long", price, atr, anchor, float(latest["ema20"]))
                c_age = _basis_age(last_index_15m, bull_sweep, near_bull_pivot, last_mss_up, eql)
                c_confirm = _count_true(eq_div, _momentum_up(latest), _rar_supportive(latest, prev), price >= float(prev["close"]), bool(latest.get("tai_rising")))
                eta_min, eta_max = _estimate_c_window("long", latest, prev, regime_score, anchor, len(c_basis), c_age, c_confirm)
                sig = _signal_dict("C_LEFT_LONG", symbol, "long", price, trend_display, "early", zone_low=c_zone_low, zone_high=c_zone_high, structure_basis=c_basis, eta_min_minutes=eta_min, eta_max_minutes=eta_max)
                sig["phase_group"] = "long_repair"
                signals.append(sig)
            else:
                _evaluate_branch("B_PULLBACK_LONG", {
                    "bg_not_hard_counter": not background["hard_counter_long"],
                    "h1_repair_locked": active_state["repair_score"] >= 4,
                    "m15_reclaim_ready": b_ready,
                    "left_watch_ready": c_ready,
                }, near_miss_signals, blocked_counter)
        else:
            checks = {
                "bg_not_hard_counter": not background["hard_counter_long"],
                "left_basis_ready": len(c_basis) >= 2,
                "left_confirm_ready": c_ready,
            }
            if _evaluate_branch("C_LEFT_LONG", checks, near_miss_signals, blocked_counter):
                anchor = next((v for v in [float((bull_sweep or {}).get("level", 0.0)) if bull_sweep else None, float((near_bull_pivot or {}).get("price", 0.0)) if near_bull_pivot else None, float((eql or {}).get("price", 0.0)) if eql else None] if v is not None), None)
                c_zone_low, c_zone_high = _build_c_zone("long", price, atr, anchor, float(latest["ema20"]))
                c_age = _basis_age(last_index_15m, bull_sweep, near_bull_pivot, last_mss_up, eql)
                c_confirm = _count_true(eq_div, _momentum_up(latest), _rar_supportive(latest, prev), price >= float(prev["close"]), bool(latest.get("tai_rising")))
                eta_min, eta_max = _estimate_c_window("long", latest, prev, regime_score, anchor, len(c_basis), c_age, c_confirm)
                sig = _signal_dict("C_LEFT_LONG", symbol, "long", price, trend_display, "early", zone_low=c_zone_low, zone_high=c_zone_high, structure_basis=c_basis, eta_min_minutes=eta_min, eta_max_minutes=eta_max)
                sig["phase_group"] = "long_early"
                signals.append(sig)
    else:
        eq_div = _eq_div_short(latest, prev)
        hard_block = _short_exhausted_hard(
            latest,
            prev,
            support_hint=bool(near_bull_pivot or bull_sweep or eql),
            deep_extension=(float(latest["ema20"]) - price) >= atr * 2.2,
            h1_exhausted=active_state["phase"] == "blocked",
        )
        a_basis = [item for item in ("h1_short_continuation", "m15_bos_down" if last_bos_down else None, "m15_mss_down" if last_mss_down else None) if item]
        b_basis = [
            item for item in (
                "h1_short_repair",
                "bearish_fvg_fill" if bear_fvg_fill else None,
                "buyside_sweep" if bear_sweep else None,
                "near_resistance" if near_bear_pivot else None,
                "eqh" if eqh else None,
                "mss_down" if last_mss_down else None,
            ) if item
        ]
        c_basis = [
            item for item in (
                "left_short_watch",
                "eq_div_short" if eq_div else None,
                "buyside_sweep" if bear_sweep else None,
                "near_resistance" if near_bear_pivot else None,
                "eqh" if eqh else None,
                "mss_down" if last_mss_down else None,
            ) if item
        ]

        b_zone_low = None
        b_zone_high = None
        if bear_fvg_fill:
            b_zone_low = float(bear_fvg_fill["zone_low"])
            b_zone_high = float(bear_fvg_fill["zone_high"])
        elif bear_sweep:
            b_zone_low = float(latest["ema20"])
            b_zone_high = float(bear_sweep["level"]) + atr * 0.10
        elif near_bear_pivot:
            b_zone_low = float(latest["ema20"])
            b_zone_high = float(near_bear_pivot["price"]) + atr * 0.10

        reject_ready = _reject_confirmation_ready(
            latest,
            prev,
            klines_15m[-4:],
            atr,
            price <= float(latest["ema10"]) and (price < float(prev["close"]) or close_pos <= 0.48),
            _price_below_stack(latest) or price <= float(latest["ema10"]),
            bool(bear_fvg_fill or bear_sweep or near_bear_pivot or last_mss_down),
        )
        a_ready = _count_true(
            _price_below_stack(latest) or (price <= float(latest["ema10"]) and float(latest["ema10"]) <= float(latest["ema20"])),
            _momentum_down(latest),
            bool(last_bos_down or last_mss_down),
            vol_ratio_15m >= 0.90 or (not bool(latest.get("tai_rising"))) or bool(latest.get("fl_sell_signal")),
            not hard_block,
        ) >= 4
        b_ready = _count_true(
            bool(b_basis) >= 1,
            reject_ready,
            price <= float(latest["ema20"]) or float(latest["ema10"]) <= float(latest["ema20"]),
            _momentum_down(latest) or (not bool(latest.get("tai_rising"))) or bool(latest.get("fl_sell_signal")),
            not hard_block,
        ) >= 4
        c_ready = _count_true(
            bool(c_basis) >= 2,
            eq_div or bool(last_mss_down),
            _rar_supportive(latest, prev) or (not bool(latest.get("tai_rising"))) or price <= float(prev["close"]),
            not background["hard_counter_short"],
        ) >= 3

        if active_state["phase"] == "continuation":
            checks = {
                "bg_not_hard_counter": not background["hard_counter_short"],
                "h1_continuation_locked": active_state["continuation_score"] >= 5,
                "m15_trigger_ready": a_ready,
                "not_exhausted": not hard_block,
            }
            if _evaluate_branch("A_SHORT", checks, near_miss_signals, blocked_counter):
                eta_min, eta_max = _estimate_a_window("short", latest, prev, regime_score, last_bos_down or last_mss_down, last_index_15m)
                sig = _signal_dict("A_SHORT", symbol, "short", price, trend_display, "active", structure_basis=a_basis, eta_min_minutes=eta_min, eta_max_minutes=eta_max)
                sig["phase_group"] = "short_continuation"
                signals.append(sig)
        elif active_state["phase"] == "repair":
            checks = {
                "bg_not_hard_counter": not background["hard_counter_short"],
                "h1_repair_locked": active_state["repair_score"] >= 4,
                "m15_reject_ready": b_ready,
                "not_exhausted": not hard_block,
            }
            if _evaluate_branch("B_PULLBACK_SHORT", checks, near_miss_signals, blocked_counter):
                b_age = _basis_age(last_index_15m, bear_fvg_fill, bear_sweep, near_bear_pivot, last_mss_down, eqh)
                eta_min, eta_max = _estimate_b_window("short", latest, prev, regime_score, b_zone_low, b_zone_high, len(b_basis), b_age, reject_ready, abs(price - float(latest["ema10"])) <= atr * 1.20)
                sig = _signal_dict("B_PULLBACK_SHORT", symbol, "short", price, trend_display, "active", zone_low=b_zone_low, zone_high=b_zone_high, structure_basis=b_basis, eta_min_minutes=eta_min, eta_max_minutes=eta_max)
                sig["phase_group"] = "short_repair"
                signals.append(sig)
            elif c_ready:
                anchor = next((v for v in [float((bear_sweep or {}).get("level", 0.0)) if bear_sweep else None, float((near_bear_pivot or {}).get("price", 0.0)) if near_bear_pivot else None, float((eqh or {}).get("price", 0.0)) if eqh else None] if v is not None), None)
                c_zone_low, c_zone_high = _build_c_zone("short", price, atr, anchor, float(latest["ema20"]))
                c_age = _basis_age(last_index_15m, bear_sweep, near_bear_pivot, last_mss_down, eqh)
                c_confirm = _count_true(eq_div, _momentum_down(latest), _rar_supportive(latest, prev), price <= float(prev["close"]), not bool(latest.get("tai_rising")))
                eta_min, eta_max = _estimate_c_window("short", latest, prev, regime_score, anchor, len(c_basis), c_age, c_confirm)
                sig = _signal_dict("C_LEFT_SHORT", symbol, "short", price, trend_display, "early", zone_low=c_zone_low, zone_high=c_zone_high, structure_basis=c_basis, eta_min_minutes=eta_min, eta_max_minutes=eta_max)
                sig["phase_group"] = "short_repair"
                signals.append(sig)
            else:
                _evaluate_branch("B_PULLBACK_SHORT", {
                    "bg_not_hard_counter": not background["hard_counter_short"],
                    "h1_repair_locked": active_state["repair_score"] >= 4,
                    "m15_reject_ready": b_ready,
                    "left_watch_ready": c_ready,
                }, near_miss_signals, blocked_counter)
        else:
            checks = {
                "bg_not_hard_counter": not background["hard_counter_short"],
                "left_basis_ready": len(c_basis) >= 2,
                "left_confirm_ready": c_ready,
            }
            if _evaluate_branch("C_LEFT_SHORT", checks, near_miss_signals, blocked_counter):
                anchor = next((v for v in [float((bear_sweep or {}).get("level", 0.0)) if bear_sweep else None, float((near_bear_pivot or {}).get("price", 0.0)) if near_bear_pivot else None, float((eqh or {}).get("price", 0.0)) if eqh else None] if v is not None), None)
                c_zone_low, c_zone_high = _build_c_zone("short", price, atr, anchor, float(latest["ema20"]))
                c_age = _basis_age(last_index_15m, bear_sweep, near_bear_pivot, last_mss_down, eqh)
                c_confirm = _count_true(eq_div, _momentum_down(latest), _rar_supportive(latest, prev), price <= float(prev["close"]), not bool(latest.get("tai_rising")))
                eta_min, eta_max = _estimate_c_window("short", latest, prev, regime_score, anchor, len(c_basis), c_age, c_confirm)
                sig = _signal_dict("C_LEFT_SHORT", symbol, "short", price, trend_display, "early", zone_low=c_zone_low, zone_high=c_zone_high, structure_basis=c_basis, eta_min_minutes=eta_min, eta_max_minutes=eta_max)
                sig["phase_group"] = "short_early"
                signals.append(sig)

    return {
        "signals": signals[:1],
        "near_miss_signals": near_miss_signals,
        "blocked_reasons": dict(blocked_counter),
    }
