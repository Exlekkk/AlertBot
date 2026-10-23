"""Liquidity Sweep Hunter — K 线近似 stub（契约 §3）。

对照：Liquidity Sweep Hunter [BigBeluga]；参数取用户截图。
第一刀仅落地接口与字段形状；算法细节下一刀补齐。
"""
from __future__ import annotations

from typing import Any

from engine.trend_config import TREND_ENGINE_CONFIG


def build_sweep_context(klines: list[dict[str, Any]]) -> dict[str, Any]:
    """输出 sweep context；不单独入场。"""
    cfg = TREND_ENGINE_CONFIG.get("sweep_hunter", {})
    _ = cfg  # 参数预留
    if len(klines) < 20:
        return {
            "side": None,
            "level": None,
            "swept": False,
            "reclaim_or_reject": None,
            "strength": 0.0,
            "approx": True,
            "reason": "insufficient_history",
        }
    # Stub：接口齐，算法下一刀
    return {
        "side": None,
        "level": None,
        "swept": False,
        "reclaim_or_reject": None,
        "strength": 0.0,
        "approx": True,
        "reason": "stub_pending_algorithm",
        "params": {
            "length": int(cfg.get("length", 10)),
            "filter": float(cfg.get("filter", 1.0)),
            "calc_bars": int(cfg.get("calc_bars", 700)),
        },
    }


__all__ = ["build_sweep_context"]
