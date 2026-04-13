from __future__ import annotations

from typing import Any


MIN_15M_ABNORMAL_VOLUME = 8000.0
MIN_1H_ABNORMAL_VOLUME = 12000.0


def _float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _atr(k: dict) -> float:
    return max(_float(k.get("atr"), 0.0), abs(_float(k.get("close"), 0.0)) * 0.0012, 1e-9)


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


def _cross_tf_budget(k_15m: dict, k_1h: dict) -> str:
    h15 = _tai_heat(k_15m)
    h1 = _tai_heat(k_1h)
    avg = (_heat_order(h15) + _heat_order(h1)) / 2.0
    if avg <= 1.0:
        return "restricted"
    if avg >= 3.0:
        return "expanded"
    return "normal"


def _volume_ratio(k: dict) -> float:
    return _float(k.get("volume")) / max(_float(k.get("vol_sma20"), 0.0), 1e-9)


def _body_size(k: dict) -> float:
    return abs(_float(k.get("close")) - _float(k.get("open")))


def _range_size(k: dict) -> float:
    return max(_float(k.get("high")) - _float(k.get("low")), 1e-9)


def _body_ratio(k: dict) -> float:
    return _body_size(k) / _range_size(k)


def _impulse_up(k: dict, prev: dict) -> bool:
    close = _float(k.get("close"))
    prev_high = _float(prev.get("high"))
    atr = _atr(k)
    return (
        close > prev_high
        and (close - _float(prev.get("close"))) >= atr * 0.45
        and _body_ratio(k) >= 0.55
        and _volume_ratio(k) >= 1.8
    )


def _impulse_down(k: dict, prev: dict) -> bool:
    close = _float(k.get("close"))
    prev_low = _float(prev.get("low"))
    atr = _atr(k)
    return (
        close < prev_low
        and (_float(prev.get("close")) - close) >= atr * 0.45
        and _body_ratio(k) >= 0.55
        and _volume_ratio(k) >= 1.8
    )


def _wick_sweep_up(k: dict, prev: dict) -> bool:
    high = _float(k.get("high"))
    close = _float(k.get("close"))
    prev_high = _float(prev.get("high"))
    atr = _atr(k)
    upper_wick = high - max(_float(k.get("open")), close)
    return (
        high > prev_high + atr * 0.12
        and close < high - atr * 0.22
        and upper_wick >= atr * 0.18
        and _volume_ratio(k) >= 1.4
    )


def _wick_sweep_down(k: dict, prev: dict) -> bool:
    low = _float(k.get("low"))
    close = _float(k.get("close"))
    prev_low = _float(prev.get("low"))
    atr = _atr(k)
    lower_wick = min(_float(k.get("open")), close) - low
    return (
        low < prev_low - atr * 0.12
        and close > low + atr * 0.22
        and lower_wick >= atr * 0.18
        and _volume_ratio(k) >= 1.4
    )


def _h1_force_up(k_1h: dict, prev_1h: dict) -> bool:
    return (
        _float(k_1h.get("close")) > _float(prev_1h.get("high"))
        and _volume_ratio(k_1h) >= 1.6
        and _body_ratio(k_1h) >= 0.5
    )


def _h1_force_down(k_1h: dict, prev_1h: dict) -> bool:
    return (
        _float(k_1h.get("close")) < _float(prev_1h.get("low"))
        and _volume_ratio(k_1h) >= 1.6
        and _body_ratio(k_1h) >= 0.5
    )


def _passes_hard_volume_gate(k_15m: dict, k_1h: dict) -> bool:
    vol_15m = _float(k_15m.get("volume"), 0.0)
    vol_1h = _float(k_1h.get("volume"), 0.0)
    return vol_15m > MIN_15M_ABNORMAL_VOLUME and vol_1h > MIN_1H_ABNORMAL_VOLUME


def _passes_relative_force_gate(k_15m: dict, k_1h: dict) -> bool:
    atr = _atr(k_15m)
    displacement = abs(_float(k_15m.get("close")) - _float(k_15m.get("open")))
    return (
        _volume_ratio(k_15m) >= 2.2
        and _body_ratio(k_15m) >= 0.62
        and displacement >= atr * 0.60
        and (_volume_ratio(k_1h) >= 1.35 or _body_ratio(k_1h) >= 0.55)
    )


def _passes_x_gate(k_15m: dict, k_1h: dict) -> bool:
    return _passes_hard_volume_gate(k_15m, k_1h) or _passes_relative_force_gate(k_15m, k_1h)


def _base_signal(
    signal: str,
    symbol: str,
    price: float,
    abnormal_type: str,
    basis: list[str],
    k_15m: dict,
    k_1h: dict,
    zone_low: float,
    zone_high: float,
    trigger_level: float,
) -> dict[str, Any]:
    budget = _cross_tf_budget(k_15m, k_1h)
    confidence = 56

    if "impulse_breakout_up" in basis or "impulse_breakout_down" in basis:
        confidence += 4
    if "h1_volume_force_x" in basis:
        confidence += 3
    if "wick_sweep_resolve_up" in basis or "wick_sweep_resolve_down" in basis:
        confidence += 2
    if "relative_force_gate" in basis:
        confidence += 2

    if budget == "restricted":
        confidence -= 2
    elif budget == "expanded":
        confidence += 2

    confidence = max(52, min(68, confidence))

    signature = f"{signal}|{abnormal_type}|{round(trigger_level, 2)}|{round(price, 2)}"

    return {
        "signal": signal,
        "symbol": symbol,
        "timeframe": "15m",
        "direction": "long" if signal.endswith("_LONG") else "short",
        "priority": 4,
        "price": round(price, 2),
        "status": "early",
        "state_1h": "abnormal",
        "background_4h_direction": "abnormal",
        "trigger_15m_state": "abnormal",
        "tai_budget_mode": budget,
        "tai_heat_15m": _tai_heat(k_15m),
        "tai_heat_1h": _tai_heat(k_1h),
        "tai_heat_4h": _tai_heat(k_1h),
        "freeze_mode": False,
        "heat_restricted": budget == "restricted",
        "structure_basis": basis,
        "zone_low": round(zone_low, 2),
        "zone_high": round(zone_high, 2),
        "trigger_level": round(trigger_level, 2),
        "eta_min_minutes": 10,
        "eta_max_minutes": 75,
        "confidence": confidence,
        "abnormal_type": abnormal_type,
        "phase_name": "abnormal",
        "phase_rank": 1,
        "phase_context": "abnormal",
        "phase_anchor": abnormal_type,
        "signature": signature,
        "x_lane": True,
        "cooldown_seconds": 1800,
    }


def detect_x_signals(
    symbol: str,
    klines_1d: list[dict],
    klines_4h: list[dict],
    klines_1h: list[dict],
    klines_15m: list[dict],
) -> list[dict]:
    if len(klines_1h) < 3 or len(klines_15m) < 4:
        return []

    k_1h = klines_1h[-1]
    prev_1h = klines_1h[-2]

    k_15m = klines_15m[-1]
    prev_15m = klines_15m[-2]
    prev2_15m = klines_15m[-3]

    if not _passes_x_gate(k_15m, k_1h):
        return []

    price = _float(k_15m.get("close"))
    atr15 = _atr(k_15m)
    signals: list[dict[str, Any]] = []

    impulse_up = _impulse_up(k_15m, prev_15m)
    impulse_down = _impulse_down(k_15m, prev_15m)
    sweep_up = _wick_sweep_up(k_15m, prev_15m)
    sweep_down = _wick_sweep_down(k_15m, prev_15m)
    h1_force_up = _h1_force_up(k_1h, prev_1h)
    h1_force_down = _h1_force_down(k_1h, prev_1h)
    relative_force = _passes_relative_force_gate(k_15m, k_1h)

    if impulse_up and (h1_force_up or _volume_ratio(k_15m) >= 2.1 or relative_force):
        basis = ["impulse_breakout_up"]
        if h1_force_up:
            basis.insert(0, "h1_volume_force_x")
        if relative_force:
            basis.append("relative_force_gate")
        zone_low = min(_float(prev_15m.get("close")), price - atr15 * 0.35)
        zone_high = max(price, _float(k_15m.get("high")))
        trigger_level = max(_float(prev_15m.get("high")), _float(prev2_15m.get("high")))
        signals.append(_base_signal(
            signal="X_BREAKOUT_LONG",
            symbol=symbol,
            price=price,
            abnormal_type="异动上破",
            basis=basis,
            k_15m=k_15m,
            k_1h=k_1h,
            zone_low=zone_low,
            zone_high=zone_high,
            trigger_level=trigger_level,
        ))

    if impulse_down and (h1_force_down or _volume_ratio(k_15m) >= 2.1 or relative_force):
        basis = ["impulse_breakout_down"]
        if h1_force_down:
            basis.insert(0, "h1_volume_force_x")
        if relative_force:
            basis.append("relative_force_gate")
        zone_low = min(price, _float(k_15m.get("low")))
        zone_high = max(_float(prev_15m.get("close")), price + atr15 * 0.35)
        trigger_level = min(_float(prev_15m.get("low")), _float(prev2_15m.get("low")))
        signals.append(_base_signal(
            signal="X_BREAKOUT_SHORT",
            symbol=symbol,
            price=price,
            abnormal_type="异动下破",
            basis=basis,
            k_15m=k_15m,
            k_1h=k_1h,
            zone_low=zone_low,
            zone_high=zone_high,
            trigger_level=trigger_level,
        ))

    if sweep_up and not impulse_up:
        zone_low = price - atr15 * 0.15
        zone_high = _float(k_15m.get("high"))
        trigger_level = _float(prev_15m.get("high"))
        basis = ["wick_sweep_resolve_down"]
        if relative_force:
            basis.append("relative_force_gate")
        signals.append(_base_signal(
            signal="X_BREAKOUT_SHORT",
            symbol=symbol,
            price=price,
            abnormal_type="上方扫流动性后回落",
            basis=basis,
            k_15m=k_15m,
            k_1h=k_1h,
            zone_low=zone_low,
            zone_high=zone_high,
            trigger_level=trigger_level,
        ))

    if sweep_down and not impulse_down:
        zone_low = _float(k_15m.get("low"))
        zone_high = price + atr15 * 0.15
        trigger_level = _float(prev_15m.get("low"))
        basis = ["wick_sweep_resolve_up"]
        if relative_force:
            basis.append("relative_force_gate")
        signals.append(_base_signal(
            signal="X_BREAKOUT_LONG",
            symbol=symbol,
            price=price,
            abnormal_type="下方扫流动性后收回",
            basis=basis,
            k_15m=k_15m,
            k_1h=k_1h,
            zone_low=zone_low,
            zone_high=zone_high,
            trigger_level=trigger_level,
        ))

    if len(signals) > 1:
        signals.sort(key=lambda s: (-int(s.get("confidence", 0)), s.get("signal", "")))
        top = signals[0]
        same_dir = [s for s in signals if s.get("direction") == top.get("direction")]
        signals = [same_dir[0] if same_dir else top]

    return signals
