from __future__ import annotations

import math
from typing import Any


TAI_LEN_FORM = 20
TAI_LEN_HIST = 252


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


def _linear_percentile(values: list[float], percentile: float) -> float | None:
    """Pine-style linear interpolation percentile over a finite window."""

    clean = sorted(v for v in values if not math.isnan(v) and not math.isinf(v))
    if not clean:
        return None
    if len(clean) == 1:
        return clean[0]

    rank = (percentile / 100.0) * (len(clean) - 1)
    lo = int(math.floor(rank))
    hi = int(math.ceil(rank))
    if lo == hi:
        return clean[lo]
    weight = rank - lo
    return clean[lo] * (1.0 - weight) + clean[hi] * weight


def _tai_vscale_series(klines: list[dict[str, Any]], len_form: int = TAI_LEN_FORM) -> list[float | None]:
    """Replicate Zeiierman TAI core: log(SMA(close * volume, len_form))."""

    dollar_volume = [
        max(_safe_float(k.get("close"), 0.0) * _safe_float(k.get("volume"), 0.0), 0.0)
        for k in klines
    ]

    out: list[float | None] = []
    window_sum = 0.0
    for i, value in enumerate(dollar_volume):
        window_sum += value
        if i >= len_form:
            window_sum -= dollar_volume[i - len_form]
        if i >= len_form - 1:
            avg = window_sum / float(len_form)
            out.append(math.log(max(avg, 1e-10)))
        else:
            out.append(None)
    return out


def _latest_tai_from_pine(
    klines_1h: list[dict[str, Any]],
    len_form: int = TAI_LEN_FORM,
    len_hist: int = TAI_LEN_HIST,
) -> dict[str, float | None]:
    """Return latest TAI vscale and P20/P40/P60/P80 bands.

    Trading Activity Index (Zeiierman) is not a 0-100 oscillator.  Its plotted
    value is log(SMA(close * volume, formation_window)), and heat is determined
    by visible rolling percentile bands.
    """

    vscale_series = _tai_vscale_series(klines_1h, len_form=len_form)
    valid = [v for v in vscale_series if v is not None]
    if not valid:
        return {"value": None, "p20": None, "p40": None, "p60": None, "p80": None, "rank01": None}

    current = valid[-1]
    hist_window = valid[-len_hist:]
    if len(hist_window) < min(50, len_hist):
        return {"value": current, "p20": None, "p40": None, "p60": None, "p80": None, "rank01": None}

    p20 = _linear_percentile(hist_window, 20)
    p40 = _linear_percentile(hist_window, 40)
    p60 = _linear_percentile(hist_window, 60)
    p80 = _linear_percentile(hist_window, 80)

    lo, hi = min(hist_window), max(hist_window)
    rank01 = 0.5 if hi <= lo else max(0.0, min(1.0, (current - lo) / (hi - lo)))

    return {"value": current, "p20": p20, "p40": p40, "p60": p60, "p80": p80, "rank01": rank01}


def _explicit_tai_bands(latest: dict[str, Any]) -> dict[str, float | None]:
    value = latest.get("tai_value")
    p20 = latest.get("tai_p20")
    p40 = latest.get("tai_p40")
    p60 = latest.get("tai_p60")
    p80 = latest.get("tai_p80")

    if value is None or p20 is None or p40 is None or p60 is None or p80 is None:
        return {"value": None, "p20": None, "p40": None, "p60": None, "p80": None, "rank01": None}

    value_f = _safe_float(value, float("nan"))
    p20_f = _safe_float(p20, float("nan"))
    p40_f = _safe_float(p40, float("nan"))
    p60_f = _safe_float(p60, float("nan"))
    p80_f = _safe_float(p80, float("nan"))

    if not (p20_f < p40_f < p60_f < p80_f):
        return {"value": None, "p20": None, "p40": None, "p60": None, "p80": None, "rank01": None}

    if value_f < p20_f:
        rank01 = 0.10
    elif value_f < p40_f:
        rank01 = 0.30
    elif value_f < p60_f:
        rank01 = 0.50
    elif value_f < p80_f:
        rank01 = 0.70
    else:
        rank01 = 0.90

    return {"value": value_f, "p20": p20_f, "p40": p40_f, "p60": p60_f, "p80": p80_f, "rank01": rank01}


def _temperature_from_tai(klines_1h: list[dict[str, Any]]) -> tuple[str, dict[str, float | None]]:
    latest = klines_1h[-1] if klines_1h else {}

    # Unit tests or external feeds may provide the TradingView bands directly.
    tai = _explicit_tai_bands(latest)
    if tai["value"] is None:
        tai = _latest_tai_from_pine(klines_1h)

    value = tai["value"]
    p20 = tai["p20"]
    p40 = tai["p40"]
    p60 = tai["p60"]
    p80 = tai["p80"]

    if value is None or p20 is None or p40 is None or p60 is None or p80 is None:
        # If real bands are not available, do not force a hot/cold call.
        return "中性", tai

    if value < p20:
        return "过冷", tai
    if value < p40:
        return "偏冷", tai
    if value < p60:
        return "中性", tai
    if value < p80:
        return "偏热", tai
    return "过热", tai


def _avg(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _momentum_from_rar_inertial_volume(
    klines_1h: list[dict[str, Any]],
    rar_proxy: float,
    inertia_proxy: float,
) -> tuple[str, float, float, float, float]:
    rar_values = _series(klines_1h[-8:], "rar_value", rar_proxy)
    if len(rar_values) >= 3:
        rar_slope = rar_values[-1] - rar_values[-3]
    elif len(rar_values) >= 2:
        rar_slope = rar_values[-1] - rar_values[-2]
    else:
        rar_slope = 0.0

    inertia_values = _series(klines_1h[-8:], "inertia", inertia_proxy)
    if len(inertia_values) >= 3:
        inertia_slope = inertia_values[-1] - inertia_values[-3]
    elif len(inertia_values) >= 2:
        inertia_slope = inertia_values[-1] - inertia_values[-2]
    else:
        inertia_slope = 0.0

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

    downside_confirmation = rar_slope < -0.25 or inertia_slope < -0.25 or volume_ratio >= 1.20
    upside_confirmation = rar_slope > 0.25 or inertia_slope > 0.25 or volume_ratio >= 1.20

    if price_impulse <= -0.75 and downside_confirmation:
        momentum = "短线卖压释放"
    elif price_impulse >= 0.75 and upside_confirmation:
        momentum = "短线买盘释放"
    elif rar_slope >= 1.0 or inertia_slope >= 1.0:
        momentum = "短线动能修复"
    elif rar_slope <= -1.0 or inertia_slope <= -1.0:
        momentum = "短线动能转弱"
    elif rar_proxy >= 55 and rar_slope >= 0:
        momentum = "短线动能偏强"
    elif rar_proxy <= 45 and rar_slope <= 0:
        momentum = "短线动能偏弱"
    else:
        momentum = "短线动能一般"

    return momentum, rar_slope, inertia_slope, price_impulse, volume_ratio


def build_aux_filters_proxy(
    klines_1h: list[dict[str, Any]],
    klines_4h: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build auxiliary context without MACD.

    The current strategy stack removed MACD_SSS_EQ because of lag.  Momentum is
    therefore based on RAR, Inertial Stochastic, recent price displacement, and
    volume expansion.  Market heat follows the Trading Activity Index formula:
    log(SMA(close * volume, 20)) compared against rolling P20/P40/P60/P80 bands.
    """

    k1 = klines_1h[-1]
    k4 = klines_4h[-1]

    rar_proxy = _safe_float(k1.get("rar_value"), 50.0)
    inertia = _safe_float(k1.get("inertia"), 50.0)

    ema_bias = "bull" if _safe_float(k1.get("ema10"), 0.0) > _safe_float(k1.get("ema20"), 0.0) else "bear"
    heat, tai = _temperature_from_tai(klines_1h)
    momentum, rar_slope, inertia_slope, price_impulse, volume_ratio = _momentum_from_rar_inertial_volume(
        klines_1h,
        rar_proxy,
        inertia,
    )

    return {
        "rar_proxy": rar_proxy,
        "inertia": inertia,
        "rar_slope": rar_slope,
        "inertia_slope": inertia_slope,
        "price_impulse": price_impulse,
        "volume_ratio": volume_ratio,
        "tai_value": tai["value"],
        "tai_p20": tai["p20"],
        "tai_p40": tai["p40"],
        "tai_p60": tai["p60"],
        "tai_p80": tai["p80"],
        "tai_percentile": tai["rank01"],
        "ema_bias": ema_bias,
        "price": _safe_float(k1.get("close"), 0.0),
        "h4_bias": "bull" if _safe_float(k4.get("ema10"), 0.0) > _safe_float(k4.get("ema20"), 0.0) else "bear",
        "momentum_desc": momentum,
        "temperature_desc": f"热度 {heat}",
    }
