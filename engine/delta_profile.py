"""3D Delta Profile + POC — K 线近似 stub（契约 §4）。

对照：LuxAlgo 3D Delta Profile；**非真实 footprint / trade-delta**。
label 固定为 candle_delta_proxy。
"""
from __future__ import annotations

from typing import Any

from engine.trend_config import TREND_ENGINE_CONFIG


def build_delta_profile_context(klines: list[dict[str, Any]]) -> dict[str, Any]:
    cfg = TREND_ENGINE_CONFIG.get("delta_profile", {})
    length = int(cfg.get("length", 200))
    if len(klines) < max(30, length // 4):
        return {
            "poc": None,
            "vah": None,
            "val": None,
            "value_area_pos": "inside",
            "node_bias": "neutral",
            "label": "candle_delta_proxy",
            "approx": True,
            "reason": "insufficient_history",
        }
    # Stub：接口齐；POC/VA 下一刀用 volume-by-price 近似
    close = float(klines[-1].get("close") or 0.0)
    return {
        "poc": close,
        "vah": close,
        "val": close,
        "value_area_pos": "inside",
        "node_bias": "neutral",
        "label": "candle_delta_proxy",
        "approx": True,
        "reason": "stub_pending_algorithm",
        "params": {
            "length": length,
            "buckets": int(cfg.get("buckets", 35)),
            "value_area_pct": float(cfg.get("value_area_pct", 70.0)),
            "highlight_hvol": False,
        },
    }


__all__ = ["build_delta_profile_context"]
