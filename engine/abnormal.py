from __future__ import annotations

from typing import Any


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _atr(k: dict) -> float:
    close = abs(_float(k.get("close")))
    return max(_float(k.get("atr")), close * 0.0012, 1e-9)


def _count_true(*conds: bool) -> int:
    return sum(bool(c) for c in conds)


def _price_above_stack(k: dict) -> bool:
    close = _float(k.get("close"))
    ema10 = _float(k.get("ema10"))
    ema20 = _float(k.get("ema20"))
    return close >= ema10 >= ema20


def _price_below_stack(k: dict) -> bool:
    close = _float(k.get("close"))
    ema10 = _float(k.get("ema10"))
    ema20 = _float(k.get("ema20"))
    return close <= ema10 <= ema20


def _momentum_up(k: dict) -> bool:
    return bool(k.get("cm_macd_above_signal")) and (
        bool(k.get("cm_hist_up")) or _float(k.get("sss_hist")) >= 0
    )


def _momentum_down(k: dict) -> bool:
    return (not bool(k.get("cm_macd_above_signal"))) and (
        bool(k.get("cm_hist_down")) or _float(k.get("sss_hist")) <= 0
    )


def _volume_ratio(k: dict) -> float:
    volume = _float(k.get("volume"))
    baseline = max(_float(k.get("vol_sma20")), 1e-9)
    return volume / baseline


def _trend_score(
    direction: str,
    k_1h: dict,
    k_4h: dict,
    k_1d: dict | None = None,
) -> int:
    if direction == "long":
        score = 0
        score += 2 if _price_above_stack(k_1h) else 0
        score += 1 if _float(k_1h.get("close")) >= _float(k_1h.get("ema20")) else 0
        score += 1 if _price_above_stack(k_4h) else 0
        score += 1 if _momentum_up(k_1h) else 0
        score += 1 if _momentum_up(k_4h) else 0
        if k_1d:
            score += 1 if _float(k_1d.get("close")) >= _float(k_1d.get("ema20")) else 0
        return score

    score = 0
    score += 2 if _price_below_stack(k_1h) else 0
    score += 1 if _float(k_1h.get("close")) <= _float(k_1h.get("ema20")) else 0
    score += 1 if _price_below_stack(k_4h) else 0
    score += 1 if _momentum_down(k_1h) else 0
    score += 1 if _momentum_down(k_4h) else 0
    if k_1d:
        score += 1 if _float(k_1d.get("close")) <= _float(k_1d.get("ema20")) else 0
    return score


def _trend_display(direction: str, score: int) -> str:
    if direction == "long":
        if score >= 6:
            return "bull"
        if score >= 3:
            return "lean_bull"
        return "neutral"
    if score >= 6:
        return "bear"
    if score >= 3:
        return "lean_bear"
    return "neutral"


def _normalize_zone(low: float, high: float) -> tuple[float, float]:
    low = float(low)
    high = float(high)
    return (round(min(low, high), 2), round(max(low, high), 2))


def _round5(value: float) -> int:
    return int(round(value / 5.0) * 5)


def _window_from_extension(extension_atr: float, vol_ratio: float) -> tuple[int, int]:
    start = 5 + max(0.0, 1.1 - min(vol_ratio, 3.0)) * 15 + max(0.0, extension_atr - 1.6) * 6
    end = 35 + max(0.0, extension_atr - 0.8) * 22 + max(0.0, 2.0 - min(vol_ratio, 3.0)) * 18
    start_i = max(5, min(60, _round5(start)))
    end_i = max(start_i + 15, min(180, _round5(end)))
    return start_i, end_i


def _signal_dict(
    signal: str,
    symbol: str,
    direction: str,
    price: float,
    trend_1h: str,
    structure_basis: list[str],
    zone_low: float,
    zone_high: float,
    breakout_level: float,
    abnormal_type: str,
    eta_min_minutes: int,
    eta_max_minutes: int,
) -> dict[str, Any]:
    return {
        "signal": signal,
        "symbol": symbol,
        "timeframe": "15m",
        "direction": direction,
        "priority": 4,
        "price": round(float(price), 2),
        "trend_1h": trend_1h,
        "status": "abnormal",
        "zone_low": round(float(zone_low), 2),
        "zone_high": round(float(zone_high), 2),
        "breakout_level": round(float(breakout_level), 2),
        "structure_basis": structure_basis,
        "abnormal_type": abnormal_type,
        "eta_min_minutes": int(eta_min_minutes),
        "eta_max_minutes": int(eta_max_minutes),
    }


def _recent_breakout_level_long(klines_15m: list[dict]) -> float:
    recent = klines_15m[-9:-1]
    return max(_float(k.get("high")) for k in recent)


def _recent_breakout_level_short(klines_15m: list[dict]) -> float:
    recent = klines_15m[-9:-1]
    return min(_float(k.get("low")) for k in recent)


def detect_abnormal_signals(
    symbol: str,
    klines_1d: list[dict],
    klines_4h: list[dict],
    klines_1h: list[dict],
    klines_15m: list[dict],
) -> list[dict[str, Any]]:
    """
    X 类重构：
    - X 独立于 ABC，不做优先级覆盖
    - 1h >= 10000 进入 force-X 异动域
    - 支持最近 1 小时（4 根 15m）内的插针、双边扫流动性、首根起爆/起跌
    - force-X 下不再要求 stack/momentum/htf 同时全过，只保留最小必要过滤
    """
    if min(len(klines_15m), len(klines_1h), len(klines_4h), len(klines_1d)) < 12:
        return []

    latest = klines_15m[-1]
    prev = klines_15m[-2]
    latest_1h = klines_1h[-1]
    latest_4h = klines_4h[-1]
    latest_1d = klines_1d[-1]
    recent_4 = klines_15m[-4:]

    price = _float(latest.get('close'))
    atr = _atr(latest)
    vol_ratio = _volume_ratio(latest)
    volume_15m = _float(latest.get('volume'))
    volume_1h = _float(latest_1h.get('volume'))

    volume_gate_15m = volume_15m >= 8000
    volume_gate_1h = volume_1h >= 10000
    volume_expansion = volume_gate_15m or volume_gate_1h

    trend_score_long = _trend_score('long', latest_1h, latest_4h, latest_1d)
    trend_score_short = _trend_score('short', latest_1h, latest_4h, latest_1d)
    trend_display_long = _trend_display('long', trend_score_long)
    trend_display_short = _trend_display('short', trend_score_short)

    recent_high = _recent_breakout_level_long(klines_15m)
    recent_low = _recent_breakout_level_short(klines_15m)

    ema10 = _float(latest.get('ema10'))
    ema20 = _float(latest.get('ema20'))
    close = _float(latest.get('close'))
    high = _float(latest.get('high'))
    low = _float(latest.get('low'))
    open_ = _float(latest.get('open'))
    prev_close = _float(prev.get('close'))

    extension_long_atr = max(0.0, (close - ema20) / max(atr, 1e-9))
    extension_short_atr = max(0.0, (ema20 - close) / max(atr, 1e-9))

    # 当前 15m 形态
    candle_range = max(high - low, 1e-9)
    body = abs(close - open_)
    body_ratio = body / candle_range
    upper_wick = max(0.0, high - max(open_, close))
    lower_wick = max(0.0, min(open_, close) - low)
    upper_wick_ratio = upper_wick / candle_range
    lower_wick_ratio = lower_wick / candle_range
    prev_high = _float(prev.get('high'))
    prev_low = _float(prev.get('low'))
    range_ratio = candle_range / max(_atr(latest), 1e-9)

    breakout_cross_up = prev_close < recent_high and close > recent_high
    breakout_cross_down = prev_close > recent_low and close < recent_low
    fresh_break_up = max(prev_high, open_) <= recent_high + atr * 0.10
    fresh_break_down = min(prev_low, open_) >= recent_low - atr * 0.10
    impulse_up = breakout_cross_up and fresh_break_up and body_ratio >= 0.50 and range_ratio >= 1.05
    impulse_down = breakout_cross_down and fresh_break_down and body_ratio >= 0.50 and range_ratio >= 1.05

    # 最近 1 小时聚合形态
    hour_open = _float(recent_4[0].get('open'))
    hour_close = _float(recent_4[-1].get('close'))
    hour_high = max(_float(k.get('high')) for k in recent_4)
    hour_low = min(_float(k.get('low')) for k in recent_4)
    hour_range = max(hour_high - hour_low, 1e-9)
    hour_body = abs(hour_close - hour_open)
    hour_upper_wick = max(0.0, hour_high - max(hour_open, hour_close))
    hour_lower_wick = max(0.0, min(hour_open, hour_close) - hour_low)
    hour_upper_wick_ratio = hour_upper_wick / hour_range
    hour_lower_wick_ratio = hour_lower_wick / hour_range
    hour_break_up = hour_high >= recent_high + atr * 0.05 and hour_close >= recent_high - atr * 0.10
    hour_break_down = hour_low <= recent_low - atr * 0.05 and hour_close <= recent_low + atr * 0.10
    hour_pin_short = hour_high >= recent_high + atr * 0.05 and hour_close <= recent_high + atr * 0.12 and hour_upper_wick_ratio >= 0.35
    hour_pin_long = hour_low <= recent_low - atr * 0.05 and hour_close >= recent_low - atr * 0.12 and hour_lower_wick_ratio >= 0.35
    dual_sided_sweep = hour_high >= recent_high + atr * 0.05 and hour_low <= recent_low - atr * 0.05 and hour_range >= atr * 1.25
    dual_bias_short = dual_sided_sweep and hour_upper_wick_ratio >= hour_lower_wick_ratio * 1.03
    dual_bias_long = dual_sided_sweep and hour_lower_wick_ratio >= hour_upper_wick_ratio * 1.03

    stack_up = _price_above_stack(latest)
    stack_down = _price_below_stack(latest)
    momentum_up = _momentum_up(latest) or _momentum_up(latest_1h)
    momentum_down = _momentum_down(latest) or _momentum_down(latest_1h)

    h1_bullish = _float(latest_1h.get('close')) >= _float(latest_1h.get('ema10')) >= _float(latest_1h.get('ema20'))
    h1_bearish = _float(latest_1h.get('close')) <= _float(latest_1h.get('ema10')) <= _float(latest_1h.get('ema20'))

    long_force = volume_gate_1h and (impulse_up or hour_break_up or hour_pin_long or dual_bias_long)
    short_force = volume_gate_1h and (impulse_down or hour_break_down or hour_pin_short or dual_bias_short)

    signals: list[dict[str, Any]] = []

    # LONG X
    if long_force or (volume_gate_15m and (impulse_up or hour_pin_long or dual_bias_long)):
        long_checks = _count_true(
            volume_expansion,
            impulse_up or hour_break_up or hour_pin_long or dual_bias_long,
            stack_up or h1_bullish or close >= ema20,
            momentum_up or bool(latest.get('fl_buy_signal')) or bool(latest.get('tai_rising')),
            trend_score_long >= 1,
            extension_long_atr <= 5.5,
        )
        if long_force or long_checks >= 4:
            breakout_level = recent_high if (impulse_up or hour_break_up) else hour_low
            zone_low = max(min(ema10, close), breakout_level - atr * 0.35)
            zone_high = max(close, recent_high + atr * 0.18)
            zone_low, zone_high = _normalize_zone(zone_low, zone_high)
            eta_min, eta_max = _window_from_extension(extension_long_atr, max(vol_ratio, 1.6))
            basis: list[str] = []
            if volume_gate_1h:
                basis.append('h1_volume_force_x')
            elif volume_gate_15m:
                basis.append('m15_volume_spike')
            if impulse_up or hour_break_up:
                basis.append('impulse_breakout_up')
            if hour_pin_long or lower_wick_ratio >= 0.35:
                basis.append('wick_rejection_down')
            if dual_bias_long:
                basis.append('dual_sided_sweep_long')
            abnormal_type = '1h放量起爆 / 可能空头回补'
            if hour_pin_long and not (impulse_up or hour_break_up):
                abnormal_type = '放量下插针扫流动性 / 可能诱空反抽'
            elif dual_bias_long and not (impulse_up or hour_break_up):
                abnormal_type = '上下插针异动 / 偏多回拉'
            signals.append(_signal_dict('X_BREAKOUT_LONG', symbol, 'long', price, trend_display_long, basis or ['abnormal_long'], zone_low, zone_high, breakout_level, abnormal_type, eta_min, eta_max))

    # SHORT X
    if short_force or (volume_gate_15m and (impulse_down or hour_pin_short or dual_bias_short)):
        short_checks = _count_true(
            volume_expansion,
            impulse_down or hour_break_down or hour_pin_short or dual_bias_short,
            stack_down or h1_bearish or close <= ema20,
            momentum_down or bool(latest.get('fl_sell_signal')) or (bool(latest.get('tai_rising')) is False),
            trend_score_short >= 1,
            extension_short_atr <= 5.5,
        )
        if short_force or short_checks >= 4:
            breakout_level = recent_low if (impulse_down or hour_break_down) else hour_high
            zone_low = min(close, recent_low - atr * 0.18)
            zone_high = min(max(ema10, close), breakout_level + atr * 0.35)
            zone_low, zone_high = _normalize_zone(zone_low, zone_high)
            eta_min, eta_max = _window_from_extension(extension_short_atr, max(vol_ratio, 1.6))
            basis: list[str] = []
            if volume_gate_1h:
                basis.append('h1_volume_force_x')
            elif volume_gate_15m:
                basis.append('m15_volume_spike')
            if impulse_down or hour_break_down:
                basis.append('impulse_breakdown_down')
            if hour_pin_short or upper_wick_ratio >= 0.35:
                basis.append('wick_rejection_up')
            if dual_bias_short:
                basis.append('dual_sided_sweep_short')
            abnormal_type = '1h放量起跌 / 可能多头踩踏'
            if hour_pin_short and not (impulse_down or hour_break_down):
                abnormal_type = '放量上插针扫流动性 / 可能诱多回落'
            elif dual_bias_short and not (impulse_down or hour_break_down):
                abnormal_type = '上下插针异动 / 偏空回落'
            signals.append(_signal_dict('X_BREAKOUT_SHORT', symbol, 'short', price, trend_display_short, basis or ['abnormal_short'], zone_low, zone_high, breakout_level, abnormal_type, eta_min, eta_max))

    if len(signals) <= 1:
        return signals

    # 若同一小时双向都触发，仅保留当前更强的一边，但不压 ABC（scanner 仍独立处理）
    def _score(sig: dict[str, Any]) -> tuple[int, int, int]:
        basis = set(sig.get('structure_basis', []))
        force = 1 if 'h1_volume_force_x' in basis else 0
        trend = trend_score_long if sig.get('direction') == 'long' else trend_score_short
        hour_dir = 1 if hour_close > hour_open and sig.get('direction') == 'long' else 0
        hour_dir = 1 if hour_close < hour_open and sig.get('direction') == 'short' else hour_dir
        return (force, trend, hour_dir)

    best = max(signals, key=_score)
    return [best]
