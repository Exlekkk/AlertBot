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
    - 专门补消息面 / 挤仓 / 放量直线拉升或瀑布
    - 不要求必须先走完整 A/B/C 模板
    - 仍然尊重你的周期框架：1h 主判，15m 执行，4h 方向过滤，必要时 1d 兜底
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
    prev_volume_ratio = _volume_ratio(prev)
    range_ratio = candle_range / max(_atr(latest), 1e-9)

    breakout_cross_up = prev_close < recent_high and close > recent_high
    breakout_cross_down = prev_close > recent_low and close < recent_low
    fresh_break_up = max(prev_high, open_) <= recent_high + atr * 0.10
    fresh_break_down = min(prev_low, open_) >= recent_low - atr * 0.10
    impulse_up = breakout_cross_up and fresh_break_up and body_ratio >= 0.58 and range_ratio >= 1.15
    impulse_down = breakout_cross_down and fresh_break_down and body_ratio >= 0.58 and range_ratio >= 1.15

    stack_up = _price_above_stack(latest)
    stack_down = _price_below_stack(latest)
    momentum_up = _momentum_up(latest)
    momentum_down = _momentum_down(latest)

    signals: list[dict[str, Any]] = []

    long_checks = {
        "volume_expansion": vol_ratio >= 2.2 and vol_ratio >= prev_volume_ratio,
        "impulse_breakout": impulse_up,
        "stack_or_reclaim": stack_up or (close >= ema20 and ema10 >= ema20),
        "momentum_confirm": momentum_up or bool(latest.get("fl_buy_signal")) or bool(latest.get("tai_rising")),
        "not_too_extended": extension_long_atr <= 4.8,
        "htf_not_hard_counter": trend_score_long >= 2,
    }
    if _count_true(*long_checks.values()) >= 5 and long_checks["volume_expansion"] and long_checks["impulse_breakout"]:
        breakout_level = recent_high
        zone_low = max(ema10, breakout_level - atr * 0.45)
        zone_high = max(close, breakout_level + atr * 0.25)
        zone_low, zone_high = _normalize_zone(zone_low, zone_high)
        eta_min, eta_max = _window_from_extension(extension_long_atr, vol_ratio)
        basis: list[str] = []
        if vol_ratio >= 2.6:
            basis.append("volume_spike")
        basis.append("first_impulse_breakout_up")
        if momentum_up:
            basis.append("momentum_up")
        if trend_score_long >= 4:
            basis.append("h1_repairing_up")
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
                "首根放量起爆 / 可能空头回补",
                eta_min,
                eta_max,
            )
        )

    short_checks = {
        "volume_expansion": vol_ratio >= 2.2 and vol_ratio >= prev_volume_ratio,
        "impulse_breakdown": impulse_down,
        "stack_or_reject": stack_down or (close <= ema20 and ema10 <= ema20),
        "momentum_confirm": momentum_down or bool(latest.get("fl_sell_signal")) or (bool(latest.get("tai_rising")) is False),
        "not_too_extended": extension_short_atr <= 4.8,
        "htf_not_hard_counter": trend_score_short >= 2,
    }
    if _count_true(*short_checks.values()) >= 5 and short_checks["volume_expansion"] and short_checks["impulse_breakdown"]:
        breakout_level = recent_low
        zone_low = min(close, breakout_level - atr * 0.25)
        zone_high = min(ema10, breakout_level + atr * 0.45)
        zone_low, zone_high = _normalize_zone(zone_low, zone_high)
        eta_min, eta_max = _window_from_extension(extension_short_atr, vol_ratio)
        basis: list[str] = []
        if vol_ratio >= 2.6:
            basis.append("volume_spike")
        basis.append("first_impulse_breakdown_down")
        if momentum_down:
            basis.append("momentum_down")
        if trend_score_short >= 4:
            basis.append("h1_repairing_down")
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
                "首根放量起爆 / 可能多头踩踏",
                eta_min,
                eta_max,
            )
        )

    return signals
