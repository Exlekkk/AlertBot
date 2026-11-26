from __future__ import annotations

import math
from typing import Any


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        f = float(value)
        if math.isnan(f) or math.isinf(f):
            return default
        return f
    except (TypeError, ValueError):
        return default


def _series(klines: list[dict[str, Any]], key: str, default: float | None = None) -> list[float]:
    values: list[float] = []
    for k in klines:
        if key in k and k.get(key) is not None:
            values.append(_safe_float(k.get(key), default if default is not None else 0.0))
    return values


def _avg(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _momentum_from_rar_volume(
    klines_1h: list[dict[str, Any]],
    rar_proxy: float,
) -> tuple[str, float, float, float]:
    """RAR + volume momentum only. Inertial slope peeled from this path."""

    rar_values = _series(klines_1h[-8:], "rar_value", rar_proxy)
    if len(rar_values) >= 3:
        rar_slope = rar_values[-1] - rar_values[-3]
    elif len(rar_values) >= 2:
        rar_slope = rar_values[-1] - rar_values[-2]
    else:
        rar_slope = 0.0

    if len(klines_1h) >= 3:
        close_now = _safe_float(klines_1h[-1].get("close"), 0.0)
        close_prev2 = _safe_float(klines_1h[-3].get("close"), close_now)
        atr = _safe_float(klines_1h[-1].get("atr"), max(abs(close_now) * 0.004, 1.0))
        price_impulse = (close_now - close_prev2) / max(atr, 1e-9)
    else:
        price_impulse = 0.0

    volumes = _series(klines_1h[-21:], "volume", 0.0)
    if len(volumes) >= 6:
        current_volume = volumes[-1]
        base_volume = _avg(volumes[:-1][-20:])
        volume_ratio = current_volume / max(base_volume, 1e-9)
    else:
        volume_ratio = 1.0

    downside_confirmation = rar_slope < -0.25 or volume_ratio >= 1.20
    upside_confirmation = rar_slope > 0.25 or volume_ratio >= 1.20

    if price_impulse <= -0.75 and downside_confirmation:
        momentum = "短线卖压释放"
    elif price_impulse >= 0.75 and upside_confirmation:
        momentum = "短线买盘释放"
    elif rar_slope >= 1.0:
        momentum = "短线动能修复"
    elif rar_slope <= -1.0:
        momentum = "短线动能转弱"
    elif rar_proxy >= 55 and rar_slope >= 0:
        momentum = "短线动能偏强"
    elif rar_proxy <= 45 and rar_slope <= 0:
        momentum = "短线动能偏弱"
    else:
        momentum = "短线动能一般"

    return momentum, rar_slope, price_impulse, volume_ratio


def build_aux_filters_proxy(
    klines_1h: list[dict[str, Any]],
    klines_4h: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build auxiliary 1H context without MACD.

    RAR remains the primary aux filter. Inertial is peeled from momentum.
    Formation/participation shadow is 15m-only and is not scored here.
    Core-levels is a soft 1H+ filter only (never a solo trigger).
    Order-flow language stays limited to closed-candle volume proxies.
    """

    from engine.core_levels_filter import build_core_levels_filter

    _ = klines_4h
    k1 = klines_1h[-1]

    rar_proxy = _safe_float(k1.get("rar_value"), 50.0)
    rar_trigger = _safe_float(k1.get("rar_trigger"), 50.0)

    momentum, rar_slope, price_impulse, volume_ratio = _momentum_from_rar_volume(
        klines_1h,
        rar_proxy,
    )
    core = build_core_levels_filter(klines_1h, timeframe="1h")

    # Legacy inertia / formation fields kept inert for older readers.
    return {
        "rar_proxy": rar_proxy,
        "rar_trigger": rar_trigger,
        "rar_above_trigger": rar_proxy >= rar_trigger,
        "inertia": None,
        "inertia_signal": None,
        "inertia_green": False,
        "inertia_turn_up": False,
        "inertia_turn_down": False,
        "inertia_source": "peeled",
        "rar_slope": rar_slope,
        "inertia_slope": 0.0,
        "price_impulse": price_impulse,
        "volume_ratio": volume_ratio,
        # Formation shadow is not active on the 1H aux path.
        "tai_value": None,
        "tai_p20": None,
        "tai_p40": None,
        "tai_p60": None,
        "tai_p80": None,
        "tai_percentile": None,
        "formation_shadow_1h": False,
        "core_levels_filter": core,
        "price": _safe_float(k1.get("close"), 0.0),
        "momentum_desc": momentum,
        "temperature_desc": "热度 中性",
    }
