from __future__ import annotations

from typing import Any


# Proxy-only implementation for RAR/TAI-style metrics (non-TV exact clone).
def build_aux_filters_proxy(
    klines_1h: list[dict[str, Any]],
    klines_4h: list[dict[str, Any]],
) -> dict[str, Any]:
    k1 = klines_1h[-1]
    k4 = klines_4h[-1]

    rar_proxy = float(k1.get("rar_value", 50.0))
    tai_proxy = float(k1.get("tai_value", 50.0))
    macd = float(k1.get("macd", 0.0))
    inertia = float(k1.get("inertia", 0.0))

    ema_bias = "bull" if float(k1.get("ema10", 0)) > float(k1.get("ema20", 0)) else "bear"
    heat = "过热" if tai_proxy > 75 else "过冷" if tai_proxy < 25 else "中性"
    momentum = "偏强" if rar_proxy > 55 and macd >= 0 else "偏弱" if rar_proxy < 45 and macd < 0 else "一般"

    return {
        "rar_proxy": rar_proxy,
        "tai_proxy": tai_proxy,
        "macd": macd,
        "inertia": inertia,
        "ema_bias": ema_bias,
        "h4_bias": "bull" if float(k4.get("ema10", 0)) > float(k4.get("ema20", 0)) else "bear",
        "momentum_desc": f"动能 {momentum}",
        "temperature_desc": f"热度 {heat}",
    }
