from __future__ import annotations

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


def _round_by_step(value: float, step: float) -> int:
    base = max(step, 1.0)
    return int(round(value / base) * base)


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
    zone_step = 15.0 if name.startswith("C_") else 5.0
    zone_key = f"{_round_by_step(zone_low_v, zone_step)}-{_round_by_step(zone_high_v, zone_step)}"
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






def _tai_zero_threshold(k: dict, tai_series: list[float] | None = None) -> float:
    p20 = _float_safe(k.get("tai_p20"), 0.0)
    if p20 <= 0:
        return 0.0
    p05 = _float_safe(k.get("tai_p05"), 0.0)
    if p05 > 0:
        lower_anchor = p05
    else:
        series = [v for v in (tai_series or []) if v > 0]
        rolling_min = min(series) if series else 0.0
        lower_anchor = rolling_min if rolling_min > 0 else _float_safe(k.get("tai_p10"), p20)
    lower_anchor = min(lower_anchor, p20)
    return lower_anchor + 0.30 * (p20 - lower_anchor)


def _tai_zero_point(k: dict, tai_series: list[float] | None = None) -> bool:
    tai = _float_safe(k.get("tai_value"), 0.0)
    threshold = _tai_zero_threshold(k, tai_series=tai_series)
    return threshold > 0 and tai <= threshold


def _phase_1h(
    direction: str,
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
    if direction == "long":
        structure_drive = bool(bos_event or mss_event)
        stack_ok = float(latest["close"]) >= float(latest["ema20"]) and float(latest["ema10"]) >= float(latest["ema20"])
        working_area = _count_true(bool(near_support), bool(support_sweep), bool(eql), bool(support_fvg_fill)) >= 1
        reclaiming = _count_true(float(latest["close"]) >= float(latest["ema10"]), float(latest["close"]) >= float(prev["close"]), _momentum_up(latest)) >= 2
        overhead_pressure = _count_true(bool(near_resistance), bool(resistance_sweep), bool(eqh), bool(resistance_fvg_fill)) >= 2
        continuation_ready = _count_true(structure_drive, stack_ok, _momentum_up(latest), not overhead_pressure) >= 3
        repair_ready = _count_true(structure_drive, working_area, reclaiming, stack_ok) >= 2
        if continuation_ready:
            return "continuation"
        if repair_ready:
            return "repair"
        if working_area or bool(support_sweep or eql):
            return "early"
        return "none"

    structure_drive = bool(bos_event or mss_event)
    stack_ok = float(latest["close"]) <= float(latest["ema20"]) and float(latest["ema10"]) <= float(latest["ema20"])
    working_area = _count_true(bool(near_resistance), bool(resistance_sweep), bool(eqh), bool(resistance_fvg_fill)) >= 1
    reclaiming = _count_true(float(latest["close"]) <= float(latest["ema10"]), float(latest["close"]) <= float(prev["close"]), _momentum_down(latest)) >= 2
    support_pressure = _count_true(bool(near_support), bool(support_sweep), bool(eql), bool(support_fvg_fill)) >= 2
    continuation_ready = _count_true(structure_drive, stack_ok, _momentum_down(latest), not support_pressure) >= 3
    repair_ready = _count_true(structure_drive, working_area, reclaiming, stack_ok) >= 2
    if continuation_ready:
        return "continuation"
    if repair_ready:
        return "repair"
    if working_area or bool(resistance_sweep or eqh):
        return "early"
    return "none"


def _bg_4h(
    direction: str,
    trend_4h: str,
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
    supportive_trend = trend_4h in {"bull", "lean_bull"} if direction == "long" else trend_4h in {"bear", "lean_bear"}
    if direction == "long":
        counter_pressure = _count_true(
            not supportive_trend,
            _momentum_down(latest),
            float(latest["close"]) < float(latest["ema20"]),
            bool(near_resistance or resistance_sweep or eqh or resistance_fvg_fill),
        )
        support_marks = _count_true(
            supportive_trend,
            bool(bos_event or mss_event),
            float(latest["close"]) >= float(latest["ema20"]),
            _momentum_up(latest),
            bool(near_support or support_sweep or eql or support_fvg_fill),
        )
    else:
        counter_pressure = _count_true(
            not supportive_trend,
            _momentum_up(latest),
            float(latest["close"]) > float(latest["ema20"]),
            bool(near_support or support_sweep or eql or support_fvg_fill),
        )
        support_marks = _count_true(
            supportive_trend,
            bool(bos_event or mss_event),
            float(latest["close"]) <= float(latest["ema20"]),
            _momentum_down(latest),
            bool(near_resistance or resistance_sweep or eqh or resistance_fvg_fill),
        )
    if counter_pressure >= 3:
        return "hard_counter"
    if support_marks >= 3:
        return "supportive"
    return "neutral"


def _trigger_15m(
    direction: str,
    latest: dict,
    prev: dict,
    *,
    bos_event: dict | None,
    mss_event: dict | None,
    reclaim_event: dict | None,
    reject_event: dict | None,
    sweep_event: dict | None,
) -> str:
    close = _float_safe(latest.get("close"))
    prev_close = _float_safe(prev.get("close"))
    vol_ratio = _volume_ratio(latest)
    wick_reject = _close_position(latest) >= 0.65 if direction == "long" else _close_position(latest) <= 0.35
    if direction == "long":
        score = _count_true(
            bool(bos_event or mss_event),
            close >= prev_close,
            _momentum_up(latest),
            bool(reclaim_event),
            bool(sweep_event),
            wick_reject,
            vol_ratio >= 1.05,
        )
    else:
        score = _count_true(
            bool(bos_event or mss_event),
            close <= prev_close,
            _momentum_down(latest),
            bool(reject_event),
            bool(sweep_event),
            wick_reject,
            vol_ratio >= 1.05,
        )
    if score >= 5 and vol_ratio >= 1.20:
        return "explosive"
    if score >= 3:
        return "ready"
    if score >= 1:
        return "weak"
    return "none"


def _h1_ignition_long(k_1h: dict, latest_15m: dict, recent_high: float) -> bool:
    volume = _float_safe(k_1h.get("volume"), 0.0)
    vsma = max(_float_safe(k_1h.get("vol_sma20"), 0.0), 1.0)
    return volume >= 10000 and (volume / vsma >= 1.25) and (
        _float_safe(k_1h.get("high")) >= recent_high or bool(latest_15m.get("tai_rising")) or _momentum_up(latest_15m)
    )


def _h1_ignition_short(k_1h: dict, latest_15m: dict, recent_low: float) -> bool:
    volume = _float_safe(k_1h.get("volume"), 0.0)
    vsma = max(_float_safe(k_1h.get("vol_sma20"), 0.0), 1.0)
    return volume >= 10000 and (volume / vsma >= 1.25) and (
        _float_safe(k_1h.get("low")) <= recent_low or (not bool(latest_15m.get("tai_rising"))) or _momentum_down(latest_15m)
    )


def _phase_rank(signal_name: str) -> int:
    if signal_name.startswith("A_"):
        return 3
    if signal_name.startswith("B_"):
        return 2
    if signal_name.startswith("C_"):
        return 1
    return 0


def _phase_context(direction: str, h1_phase: str, bg_bias: str, zone_low: float | None, zone_high: float | None) -> str:
    low = _round5(zone_low or 0.0)
    high = _round5(zone_high or 0.0)
    return f"{direction}|{h1_phase}|{bg_bias}|{low}-{high}"


def build_a_long_candidate(
    *,
    symbol: str,
    price: float,
    trend_display: str,
    phase_1h: str,
    bg_4h: str,
    trigger_15m: str,
    tai_zero: bool,
    zone_low: float | None,
    zone_high: float | None,
    structure_basis: list[str],
    eta_min: int,
    eta_max: int,
) -> dict[str, Any] | None:
    if phase_1h != "continuation" or trigger_15m not in {"ready", "explosive"} or bg_4h == "hard_counter" or tai_zero:
        return None
    zone_low_v = zone_low if zone_low is not None else price
    zone_high_v = zone_high if zone_high is not None else price
    context = _phase_context("long", phase_1h, bg_4h, zone_low_v, zone_high_v)
    sig = _signal_dict(
        "A_LONG", symbol, "long", price, trend_display, "active",
        zone_low=zone_low_v, zone_high=zone_high_v, structure_basis=structure_basis,
        eta_min_minutes=max(10, eta_min - 10), eta_max_minutes=max(45, eta_max - 30),
    )
    sig.update({"phase_name": phase_1h, "phase_context": context, "phase_rank": 3, "bg_bias": bg_4h, "trigger_state": trigger_15m, "tai_zero": tai_zero, "atr": max(abs(price) * 0.0012, 1.0)})
    return sig


def build_a_short_candidate(
    *,
    symbol: str,
    price: float,
    trend_display: str,
    phase_1h: str,
    bg_4h: str,
    trigger_15m: str,
    tai_zero: bool,
    zone_low: float | None,
    zone_high: float | None,
    structure_basis: list[str],
    eta_min: int,
    eta_max: int,
) -> dict[str, Any] | None:
    if phase_1h != "continuation" or trigger_15m not in {"ready", "explosive"} or bg_4h == "hard_counter" or tai_zero:
        return None
    zone_low_v = zone_low if zone_low is not None else price
    zone_high_v = zone_high if zone_high is not None else price
    context = _phase_context("short", phase_1h, bg_4h, zone_low_v, zone_high_v)
    sig = _signal_dict(
        "A_SHORT", symbol, "short", price, trend_display, "active",
        zone_low=zone_low_v, zone_high=zone_high_v, structure_basis=structure_basis,
        eta_min_minutes=max(10, eta_min - 10), eta_max_minutes=max(45, eta_max - 30),
    )
    sig.update({"phase_name": phase_1h, "phase_context": context, "phase_rank": 3, "bg_bias": bg_4h, "trigger_state": trigger_15m, "tai_zero": tai_zero, "atr": max(abs(price) * 0.0012, 1.0)})
    return sig


def build_b_candidate(
    *,
    symbol: str,
    direction: str,
    price: float,
    trend_display: str,
    phase_1h: str,
    bg_bias: str,
    tai_zero: bool,
    trigger_15m: str,
    zone_low: float | None,
    zone_high: float | None,
    structure_basis: list[str],
    eta_min: int,
    eta_max: int,
) -> dict[str, Any] | None:
    if phase_1h != "repair" or trigger_15m not in {"ready", "explosive"} or bg_bias == "hard_counter" or tai_zero:
        return None
    zone_low_v = zone_low if zone_low is not None else price
    zone_high_v = zone_high if zone_high is not None else price
    context = _phase_context(direction, phase_1h, bg_bias, zone_low_v, zone_high_v)
    sig = _signal_dict(
        "B_PULLBACK_LONG" if direction == "long" else "B_PULLBACK_SHORT",
        symbol, direction, price, trend_display, "active",
        zone_low=zone_low_v, zone_high=zone_high_v, structure_basis=structure_basis,
        eta_min_minutes=eta_min, eta_max_minutes=eta_max,
    )
    sig.update({"phase_name": phase_1h, "phase_context": context, "phase_rank": 2, "bg_bias": bg_bias, "trigger_state": trigger_15m, "tai_zero": tai_zero, "atr": max(abs(price) * 0.0012, 1.0)})
    return sig


def build_c_candidate(
    *,
    symbol: str,
    direction: str,
    price: float,
    trend_display: str,
    phase_1h: str,
    bg_bias: str,
    tai_zero: bool,
    trigger_15m: str,
    zone_low: float | None,
    zone_high: float | None,
    structure_basis: list[str],
    eta_min: int,
    eta_max: int,
) -> dict[str, Any] | None:
    if phase_1h != "early" or trigger_15m not in {"weak", "ready", "explosive"} or tai_zero:
        return None
    zone_low_v = zone_low if zone_low is not None else price
    zone_high_v = zone_high if zone_high is not None else price
    context = _phase_context(direction, phase_1h, bg_bias, zone_low_v, zone_high_v)
    sig = _signal_dict(
        "C_LEFT_LONG" if direction == "long" else "C_LEFT_SHORT",
        symbol, direction, price, trend_display, "watch",
        zone_low=zone_low_v, zone_high=zone_high_v, structure_basis=structure_basis,
        eta_min_minutes=eta_min, eta_max_minutes=eta_max,
    )
    sig.update({"phase_name": phase_1h, "phase_context": context, "phase_rank": 1, "bg_bias": bg_bias, "trigger_state": trigger_15m, "tai_zero": tai_zero, "atr": max(abs(price) * 0.0012, 1.0)})
    return sig


def resolve_directional_signal(
    *,
    direction: str,
    symbol: str,
    price: float,
    trend_display: str,
    phase_1h: str,
    bg_4h: str,
    trigger_15m: str,
    tai_zero: bool,
    zone_low: float | None,
    zone_high: float | None,
    structure_basis: list[str],
    eta_min: int,
    eta_max: int,
) -> dict[str, Any] | None:
    if direction == "long":
        if phase_1h == "continuation":
            return build_a_long_candidate(symbol=symbol, price=price, trend_display=trend_display, phase_1h=phase_1h, bg_4h=bg_4h, trigger_15m=trigger_15m, tai_zero=tai_zero, zone_low=zone_low, zone_high=zone_high, structure_basis=structure_basis, eta_min=eta_min, eta_max=eta_max)
    else:
        if phase_1h == "continuation":
            return build_a_short_candidate(symbol=symbol, price=price, trend_display=trend_display, phase_1h=phase_1h, bg_4h=bg_4h, trigger_15m=trigger_15m, tai_zero=tai_zero, zone_low=zone_low, zone_high=zone_high, structure_basis=structure_basis, eta_min=eta_min, eta_max=eta_max)
    if phase_1h == "repair":
        return build_b_candidate(symbol=symbol, direction=direction, price=price, trend_display=trend_display, phase_1h=phase_1h, bg_bias=bg_4h, tai_zero=tai_zero, trigger_15m=trigger_15m, zone_low=zone_low, zone_high=zone_high, structure_basis=structure_basis, eta_min=eta_min, eta_max=eta_max)
    if phase_1h == "early":
        return build_c_candidate(symbol=symbol, direction=direction, price=price, trend_display=trend_display, phase_1h=phase_1h, bg_bias=bg_4h, tai_zero=tai_zero, trigger_15m=trigger_15m, zone_low=zone_low, zone_high=zone_high, structure_basis=structure_basis, eta_min=eta_min, eta_max=eta_max)
    return None


def _phase_strength(signal: dict[str, Any] | None) -> int:
    if not signal:
        return 0
    return {"continuation": 3, "repair": 2, "early": 1}.get(signal.get("phase_name", "none"), 0)


def _trigger_strength(signal: dict[str, Any] | None) -> int:
    if not signal:
        return 0
    return {"explosive": 3, "ready": 2, "weak": 1, "none": 0}.get(signal.get("trigger_state", "none"), 0)


def _bg_strength(signal: dict[str, Any] | None) -> int:
    if not signal:
        return 0
    return {"supportive": 2, "neutral": 1, "hard_counter": 0}.get(signal.get("bg_bias", "neutral"), 1)


def _signal_strength(signal: dict[str, Any] | None) -> int:
    if not signal:
        return -999
    tai_score = -2 if bool(signal.get("tai_zero")) else 1
    return _phase_strength(signal) * 5 + _trigger_strength(signal) * 3 + _bg_strength(signal) * 2 + tai_score


def resolve_symbol_signal(long_signal: dict[str, Any] | None, short_signal: dict[str, Any] | None) -> dict[str, Any] | None:
    if long_signal and not short_signal:
        return long_signal
    if short_signal and not long_signal:
        return short_signal
    if not long_signal and not short_signal:
        return None
    if _phase_strength(long_signal) == 3 and _phase_strength(short_signal) == 1:
        return long_signal
    if _phase_strength(short_signal) == 3 and _phase_strength(long_signal) == 1:
        return short_signal
    long_strength = _signal_strength(long_signal)
    short_strength = _signal_strength(short_signal)
    if long_strength - short_strength >= 2:
        return long_signal
    if short_strength - long_strength >= 2:
        return short_signal
    return None


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
    price = float(latest["close"])

    long_regime_score = _direction_regime_score("long", trend_1d, trend_4h, trend_1h, k_4h, p_4h, k_1h, p_1h)
    short_regime_score = _direction_regime_score("short", trend_1d, trend_4h, trend_1h, k_4h, p_4h, k_1h, p_1h)
    trend_display_long = _trend_display("long", long_regime_score)
    trend_display_short = _trend_display("short", short_regime_score)

    last_bos_up = latest_structure_event(klines_15m, direction="up", kinds=("bos",), max_bars_ago=8)
    last_bos_down = latest_structure_event(klines_15m, direction="down", kinds=("bos",), max_bars_ago=8)
    last_mss_up = latest_structure_event(klines_15m, direction="up", kinds=("mss",), max_bars_ago=10)
    last_mss_down = latest_structure_event(klines_15m, direction="down", kinds=("mss",), max_bars_ago=10)

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

    h1_long_phase = _phase_1h("long", k_1h, p_1h, bos_event=h1_last_bos_up, mss_event=h1_last_mss_up, support_fvg_fill=h1_bull_fvg_fill, resistance_fvg_fill=h1_bear_fvg_fill, support_sweep=h1_bull_sweep, resistance_sweep=h1_bear_sweep, near_support=h1_near_bull_pivot, near_resistance=h1_near_bear_pivot, eql=h1_eql, eqh=h1_eqh)
    h1_short_phase = _phase_1h("short", k_1h, p_1h, bos_event=h1_last_bos_down, mss_event=h1_last_mss_down, support_fvg_fill=h1_bull_fvg_fill, resistance_fvg_fill=h1_bear_fvg_fill, support_sweep=h1_bull_sweep, resistance_sweep=h1_bear_sweep, near_support=h1_near_bull_pivot, near_resistance=h1_near_bear_pivot, eql=h1_eql, eqh=h1_eqh)

    tai_series_1h = [_float_safe(k.get("tai_value"), 0.0) for k in klines_1h[-20:]]
    tai_zero = _tai_zero_point(k_1h, tai_series=tai_series_1h)
    recent_high_8 = max(float(k["high"]) for k in klines_15m[-9:-1])
    recent_low_8 = min(float(k["low"]) for k in klines_15m[-9:-1])
    long_ignition = _h1_ignition_long(k_1h, latest, recent_high_8)
    short_ignition = _h1_ignition_short(k_1h, latest, recent_low_8)

    near_miss_signals: list[dict[str, Any]] = []
    signals: list[dict[str, Any]] = []

    long_bg = _bg_4h("long", trend_4h, k_4h, p_4h, bos_event=h4_last_bos_up, mss_event=h4_last_mss_up, support_fvg_fill=h4_bull_fvg_fill, resistance_fvg_fill=h4_bear_fvg_fill, support_sweep=h4_bull_sweep, resistance_sweep=h4_bear_sweep, near_support=h4_near_bull_pivot, near_resistance=h4_near_bear_pivot, eql=h4_eql, eqh=h4_eqh)
    long_trigger = _trigger_15m("long", latest, prev, bos_event=last_bos_up, mss_event=last_mss_up, reclaim_event=bull_fvg_fill, reject_event=bear_fvg_fill, sweep_event=bull_sweep)
    long_basis = [x for x, ok in [
        ("mss_up", bool(last_mss_up or h1_last_mss_up)),
        ("bos_up", bool(last_bos_up or h1_last_bos_up)),
        ("bullish_fvg_fill", bool(bull_fvg_fill or h1_bull_fvg_fill)),
        ("sweep_low", bool(bull_sweep or h1_bull_sweep or eql or h1_eql)),
    ] if ok]
    long_zone_low = min(float(latest["ema10"]), float(latest["ema20"]), float(latest.get("low")))
    long_zone_high = max(float(latest["close"]), recent_high_8, float(latest["ema10"]))
    long_signal = resolve_directional_signal(
        direction="long", symbol=symbol, price=price, trend_display=trend_display_long,
        phase_1h=h1_long_phase, bg_4h=long_bg, trigger_15m=long_trigger,
        tai_zero=tai_zero and not long_ignition, zone_low=long_zone_low, zone_high=long_zone_high,
        structure_basis=long_basis, eta_min=25, eta_max=165,
    )
    if not long_signal:
        cand = "A_LONG" if h1_long_phase == "continuation" else ("B_PULLBACK_LONG" if h1_long_phase == "repair" else ("C_LEFT_LONG" if h1_long_phase == "early" else "NONE_LONG"))
        failed: list[str] = []
        if tai_zero and not long_ignition:
            failed.append("tai_zero_zone")
        if long_bg == "hard_counter" and h1_long_phase in {"continuation", "repair"}:
            failed.append("bg_not_hard_counter")
        if h1_long_phase in {"continuation", "repair"} and long_trigger not in {"ready", "explosive"}:
            failed.append("m15_trigger_ready")
        if h1_long_phase == "early" and long_trigger == "none":
            failed.append("m15_trigger_weak")
        if failed and len(failed) <= 2:
            near_miss_signals.append({"candidate": cand, "failed_checks": failed})

    short_bg = _bg_4h("short", trend_4h, k_4h, p_4h, bos_event=h4_last_bos_down, mss_event=h4_last_mss_down, support_fvg_fill=h4_bull_fvg_fill, resistance_fvg_fill=h4_bear_fvg_fill, support_sweep=h4_bull_sweep, resistance_sweep=h4_bear_sweep, near_support=h4_near_bull_pivot, near_resistance=h4_near_bear_pivot, eql=h4_eql, eqh=h4_eqh)
    short_trigger = _trigger_15m("short", latest, prev, bos_event=last_bos_down, mss_event=last_mss_down, reclaim_event=bull_fvg_fill, reject_event=bear_fvg_fill, sweep_event=bear_sweep)
    short_basis = [x for x, ok in [
        ("mss_down", bool(last_mss_down or h1_last_mss_down)),
        ("bos_down", bool(last_bos_down or h1_last_bos_down)),
        ("bearish_fvg_fill", bool(bear_fvg_fill or h1_bear_fvg_fill)),
        ("sweep_high", bool(bear_sweep or h1_bear_sweep or eqh or h1_eqh)),
    ] if ok]
    short_zone_low = min(float(latest["close"]), recent_low_8, float(latest["ema10"]))
    short_zone_high = max(float(latest["ema10"]), float(latest["ema20"]), float(latest.get("high")))
    short_signal = resolve_directional_signal(
        direction="short", symbol=symbol, price=price, trend_display=trend_display_short,
        phase_1h=h1_short_phase, bg_4h=short_bg, trigger_15m=short_trigger,
        tai_zero=tai_zero and not short_ignition, zone_low=short_zone_low, zone_high=short_zone_high,
        structure_basis=short_basis, eta_min=25, eta_max=165,
    )
    if not short_signal:
        cand = "A_SHORT" if h1_short_phase == "continuation" else ("B_PULLBACK_SHORT" if h1_short_phase == "repair" else ("C_LEFT_SHORT" if h1_short_phase == "early" else "NONE_SHORT"))
        failed = []
        if tai_zero and not short_ignition:
            failed.append("tai_zero_zone")
        if short_bg == "hard_counter" and h1_short_phase in {"continuation", "repair"}:
            failed.append("bg_not_hard_counter")
        if h1_short_phase in {"continuation", "repair"} and short_trigger not in {"ready", "explosive"}:
            failed.append("m15_trigger_ready")
        if h1_short_phase == "early" and short_trigger == "none":
            failed.append("m15_trigger_weak")
        if failed and len(failed) <= 2:
            near_miss_signals.append({"candidate": cand, "failed_checks": failed})

    final_signal = resolve_symbol_signal(long_signal, short_signal)
    signals = [final_signal] if final_signal else []
    return {"signals": signals, "near_miss_signals": near_miss_signals, "blocked_reasons": {}}
