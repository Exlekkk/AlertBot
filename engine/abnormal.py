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
    X类异动信号：
    - 15m >= 8000 或 1h >= 10000，进入异动强监控
    - 保留首根实体起爆/起跌
    - 新增插针 / 上下扫流动性路径，避免 pin bar 被漏掉
    - 4h 仍只做硬逆风过滤，不改 ABC 主框架
    """
    if min(len(klines_15m), len(klines_1h), len(klines_4h), len(klines_1d)) < 12:
        return []

    latest = klines_15m[-1]
    prev = klines_15m[-2]
    latest_1h = klines_1h[-1]
    latest_4h = klines_4h[-1]
    latest_1d = klines_1d[-1]

    price = _float(latest.get("close"))
    atr = _atr(latest)
    vol_ratio = _volume_ratio(latest)
    volume_15m = _float(latest.get("volume"))
    volume_1h = _float(latest_1h.get("volume"))

    # 用户定死的量门槛：15m 超 8k / 1h 超 10k，进入 X 异动域
    volume_gate_15m = volume_15m >= 8000
    volume_gate_1h = volume_1h >= 10000
    volume_expansion = volume_gate_15m or volume_gate_1h

    trend_score_long = _trend_score("long", latest_1h, latest_4h, latest_1d)
    trend_score_short = _trend_score("short", latest_1h, latest_4h, latest_1d)
    trend_display_long = _trend_display("long", trend_score_long)
    trend_display_short = _trend_display("short", trend_score_short)

    recent_high = _recent_breakout_level_long(klines_15m)
    recent_low = _recent_breakout_level_short(klines_15m)

    ema10 = _float(latest.get("ema10"))
    ema20 = _float(latest.get("ema20"))
    prev_close = _float(prev.get("close"))
    close = _float(latest.get("close"))
    high = _float(latest.get("high"))
    low = _float(latest.get("low"))
    open_ = _float(latest.get("open"))

    extension_long_atr = max(0.0, (close - ema20) / max(atr, 1e-9))
    extension_short_atr = max(0.0, (ema20 - close) / max(atr, 1e-9))

    body = abs(close - open_)
    candle_range = max(high - low, 1e-9)
    body_ratio = body / candle_range
    prev_high = _float(prev.get("high"))
    prev_low = _float(prev.get("low"))
    range_ratio = candle_range / max(_atr(latest), 1e-9)

    upper_wick = max(0.0, high - max(open_, close))
    lower_wick = max(0.0, min(open_, close) - low)
    upper_wick_ratio = upper_wick / candle_range
    lower_wick_ratio = lower_wick / candle_range

    breakout_cross_up = prev_close < recent_high and close > recent_high
    breakout_cross_down = prev_close > recent_low and close < recent_low
    fresh_break_up = max(prev_high, open_) <= recent_high + atr * 0.10
    fresh_break_down = min(prev_low, open_) >= recent_low - atr * 0.10
    impulse_up = breakout_cross_up and fresh_break_up and body_ratio >= 0.58 and range_ratio >= 1.15
    impulse_down = breakout_cross_down and fresh_break_down and body_ratio >= 0.58 and range_ratio >= 1.15

    # 插针 / 扫流动性路径
    sweep_high = high >= recent_high + atr * 0.05
    sweep_low = low <= recent_low - atr * 0.05
    close_back_below_high = close <= recent_high + atr * 0.15
    close_back_above_low = close >= recent_low - atr * 0.15

    pin_reject_short = sweep_high and close_back_below_high and upper_wick_ratio >= 0.46 and range_ratio >= 1.08
    pin_reject_long = sweep_low and close_back_above_low and lower_wick_ratio >= 0.46 and range_ratio >= 1.08

    dual_sided_sweep = sweep_high and sweep_low and range_ratio >= 1.28
    dual_bias_short = dual_sided_sweep and upper_wick_ratio >= lower_wick_ratio * 1.05
    dual_bias_long = dual_sided_sweep and lower_wick_ratio >= upper_wick_ratio * 1.05

    stack_up = _price_above_stack(latest)
    stack_down = _price_below_stack(latest)
    momentum_up = _momentum_up(latest)
    momentum_down = _momentum_down(latest)

    signals: list[dict[str, Any]] = []

    long_checks = {
        "volume_expansion": volume_expansion,
        "impulse_or_pin": impulse_up or pin_reject_long or dual_bias_long,
        "stack_or_reclaim": stack_up or (close >= ema20 and ema10 >= ema20),
        "momentum_confirm": momentum_up or bool(latest.get("fl_buy_signal")) or bool(latest.get("tai_rising")),
        "not_too_extended": extension_long_atr <= 4.8,
        "htf_not_hard_counter": trend_score_long >= 2,
    }
    long_force = volume_gate_1h and (impulse_up or pin_reject_long or dual_bias_long)
    if (
        (long_force and _count_true(*long_checks.values()) >= 4)
        or (_count_true(*long_checks.values()) >= 5 and long_checks["volume_expansion"] and long_checks["impulse_or_pin"])
    ):
        breakout_level = recent_high if impulse_up else low
        zone_low = max(min(ema10, close), breakout_level - atr * 0.35)
        zone_high = max(close, recent_high + atr * 0.18)
        zone_low, zone_high = _normalize_zone(zone_low, zone_high)
        eta_min, eta_max = _window_from_extension(extension_long_atr, max(vol_ratio, 1.6))
        basis: list[str] = []
        if volume_gate_1h:
            basis.append("h1_volume_force_x")
        elif volume_gate_15m:
            basis.append("m15_volume_spike")
        if impulse_up:
            basis.append("first_impulse_breakout_up")
        if pin_reject_long:
            basis.append("wick_rejection_down")
        if dual_bias_long:
            basis.append("dual_sided_sweep_long")
        if momentum_up:
            basis.append("momentum_up")
        if trend_score_long >= 4:
            basis.append("h1_repairing_up")

        abnormal_type = "首根放量起爆 / 可能空头回补"
        if pin_reject_long and not impulse_up:
            abnormal_type = "放量下插针扫流动性 / 可能诱空反抽"
        elif dual_bias_long and not impulse_up:
            abnormal_type = "上下插针异动 / 偏多回拉"

        signals.append(
            _signal_dict(
                "X_BREAKOUT_LONG",
                symbol,
                "long",
                price,
                trend_display_long,
                basis or ["abnormal_long"],
                zone_low,
                zone_high,
                breakout_level,
                abnormal_type,
                eta_min,
                eta_max,
            )
        )

    short_checks = {
        "volume_expansion": volume_expansion,
        "impulse_or_pin": impulse_down or pin_reject_short or dual_bias_short,
        "stack_or_reject": stack_down or (close <= ema20 and ema10 <= ema20),
        "momentum_confirm": momentum_down or bool(latest.get("fl_sell_signal")) or (bool(latest.get("tai_rising")) is False),
        "not_too_extended": extension_short_atr <= 4.8,
        "htf_not_hard_counter": trend_score_short >= 2,
    }
    short_force = volume_gate_1h and (impulse_down or pin_reject_short or dual_bias_short)
    if (
        (short_force and _count_true(*short_checks.values()) >= 4)
        or (_count_true(*short_checks.values()) >= 5 and short_checks["volume_expansion"] and short_checks["impulse_or_pin"])
    ):
        breakout_level = recent_low if impulse_down else high
        zone_low = min(close, recent_low - atr * 0.18)
        zone_high = min(max(ema10, close), breakout_level + atr * 0.35)
        zone_low, zone_high = _normalize_zone(zone_low, zone_high)
        eta_min, eta_max = _window_from_extension(extension_short_atr, max(vol_ratio, 1.6))
        basis: list[str] = []
        if volume_gate_1h:
            basis.append("h1_volume_force_x")
        elif volume_gate_15m:
            basis.append("m15_volume_spike")
        if impulse_down:
            basis.append("first_impulse_breakdown_down")
        if pin_reject_short:
            basis.append("wick_rejection_up")
        if dual_bias_short:
            basis.append("dual_sided_sweep_short")
        if momentum_down:
            basis.append("momentum_down")
        if trend_score_short >= 4:
            basis.append("h1_repairing_down")

        abnormal_type = "首根放量起跌 / 可能多头踩踏"
        if pin_reject_short and not impulse_down:
            abnormal_type = "放量上插针扫流动性 / 可能诱多回落"
        elif dual_bias_short and not impulse_down:
            abnormal_type = "上下插针异动 / 偏空回落"

        signals.append(
            _signal_dict(
                "X_BREAKOUT_SHORT",
                symbol,
                "short",
                price,
                trend_display_short,
                basis or ["abnormal_short"],
                zone_low,
                zone_high,
                breakout_level,
                abnormal_type,
                eta_min,
                eta_max,
            )
        )

    if len(signals) <= 1:
        return signals

    # 避免同一根同时多空乱发：优先 volume force + 更高趋势分数的一边
    def _score(sig: dict[str, Any]) -> tuple[int, int]:
        basis = set(sig.get("structure_basis", []))
        force = 1 if "h1_volume_force_x" in basis else 0
        trend = trend_score_long if sig.get("direction") == "long" else trend_score_short
        return (force, trend)

    best = max(signals, key=_score)
    return [best]
