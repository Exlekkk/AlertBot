"""Inversion FVG — K 线近似 stub（契约 §5）。

对照：Inversion FVG [ChartPrime]；1H minSize=0.2 / 15m=0.15。
第一刀接口齐；倒置检测下一刀替换 ict_ob/msb_ob 栈。
"""
from __future__ import annotations

from typing import Any

from engine.trend_config import TREND_ENGINE_CONFIG


def build_ifvg_context(
    klines: list[dict[str, Any]],
    *,
    timeframe: str = "1h",
) -> dict[str, Any]:
    cfg = TREND_ENGINE_CONFIG.get("ifvg", {})
    min_size = float(cfg.get("min_size_1h", 0.2) if timeframe.lower() in {"1h", "1H", "60"} else cfg.get("min_size_15m", 0.15))
    if len(klines) < 30:
        return {
            "zones": [],
            "nearest_active": None,
            "approx": True,
            "reason": "insufficient_history",
            "timeframe": timeframe,
            "min_size_pct": min_size,
        }
    return {
        "zones": [],
        "nearest_active": None,
        "approx": True,
        "reason": "stub_pending_algorithm",
        "timeframe": timeframe,
        "min_size_pct": min_size,
        "params": {
            "display_mode": "Both",
            "longevity": int(cfg.get("longevity", 500)),
            "calc_bars": int(cfg.get("calc_bars", 2000)),
        },
    }


__all__ = ["build_ifvg_context"]
