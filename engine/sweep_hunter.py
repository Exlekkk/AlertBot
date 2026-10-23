"""Liquidity Sweep Hunter — K 线近似（契约 §3）。

对照：Liquidity Sweep Hunter [BigBeluga]。
参数取用户截图：Length=10，Filter=1，calcBars≈700。
不复制受许可 Pine；翻译 pivot + volume filter + sweep/reclaim 语义。
"""
from __future__ import annotations

from typing import Any

from engine.trend_config import TREND_ENGINE_CONFIG


def _f(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _volume_change_pct(volumes: list[float], i: int) -> float:
    if i <= 0 or i >= len(volumes):
        return 0.0
    vol = volumes[i]
    if vol <= 0:
        return 0.0
    return (vol - volumes[i - 1]) / vol * 100.0


def _is_pivot_low(lows: list[float], i: int, length: int) -> bool:
    if i < length or i + length >= len(lows):
        return False
    pivot = lows[i]
    for j in range(i - length, i + length + 1):
        if j != i and lows[j] < pivot:
            return False
    return True


def _is_pivot_high(highs: list[float], i: int, length: int) -> bool:
    if i < length or i + length >= len(highs):
        return False
    pivot = highs[i]
    for j in range(i - length, i + length + 1):
        if j != i and highs[j] > pivot:
            return False
    return True


def build_sweep_context(klines: list[dict[str, Any]]) -> dict[str, Any]:
    """契约 sweep 字段；附旧 liquidity 兼容映射。不单独入场。"""
    cfg = TREND_ENGINE_CONFIG.get("sweep_hunter", {})
    length = int(cfg.get("length", 10))
    vol_filter = float(cfg.get("filter", 1.0))
    calc_bars = int(cfg.get("calc_bars", 700))

    empty = {
        "side": None,
        "level": None,
        "swept": False,
        "reclaim_or_reject": None,
        "strength": 0.0,
        "approx": True,
        "candle_proxy": True,
        "bars_since": None,
        "active_levels": [],
        "legacy_sweep_type": "none",
        "recent_sweep_valid": False,
        "reason": "insufficient_history",
        "params": {"length": length, "filter": vol_filter, "calc_bars": calc_bars},
    }
    if len(klines) < length * 2 + 5:
        return empty

    window = klines[-min(len(klines), calc_bars):]
    highs = [_f(k.get("high")) for k in window]
    lows = [_f(k.get("low")) for k in window]
    closes = [_f(k.get("close")) for k in window]
    volumes = [_f(k.get("volume")) for k in window]
    n = len(window)

    # is_support=True → pivot low（sell-side liquidity）
    levels: list[dict[str, Any]] = []
    for i in range(length, n - length):
        vchg = _volume_change_pct(volumes, i)
        if vchg <= vol_filter:
            continue
        if _is_pivot_low(lows, i, length):
            levels.append({"price": lows[i], "is_support": True, "born": i, "strength": max(0.0, min(1.0, vchg / 100.0)), "broken": False})
        if _is_pivot_high(highs, i, length):
            levels.append({"price": highs[i], "is_support": False, "born": i, "strength": max(0.0, min(1.0, vchg / 100.0)), "broken": False})

    last_sweep: dict[str, Any] | None = None
    for i in range(n):
        h, l, c = highs[i], lows[i], closes[i]
        for lv in levels:
            if lv["broken"] or i <= lv["born"]:
                continue
            price = lv["price"]
            if not (h > price and l < price):
                continue
            low_sweep = lv["is_support"] and l < price and c > price
            high_sweep = (not lv["is_support"]) and h > price and c < price
            if low_sweep or high_sweep:
                last_sweep = {
                    "side": "sell_side" if low_sweep else "buy_side",
                    "level": price,
                    "reclaim_or_reject": "reclaim" if low_sweep else "reject",
                    "strength": float(lv["strength"]),
                    "bars_since": n - 1 - i,
                }
            lv["broken"] = True

    active = [lv for lv in levels if not lv["broken"]][-12:]
    active_payload = [
        {"price": round(lv["price"], 2), "side": "sell_side" if lv["is_support"] else "buy_side", "strength": round(lv["strength"], 3)}
        for lv in active
    ]
    if last_sweep is None:
        out = dict(empty)
        out["reason"] = "no_recent_sweep"
        out["active_levels"] = active_payload
        return out

    legacy_type = "sellside" if last_sweep["side"] == "sell_side" else "buyside"
    bars_since = int(last_sweep["bars_since"])
    return {
        "side": last_sweep["side"],
        "level": round(float(last_sweep["level"]), 2),
        "swept": True,
        "reclaim_or_reject": last_sweep["reclaim_or_reject"],
        "strength": round(float(last_sweep["strength"]), 3),
        "approx": True,
        "candle_proxy": True,
        "bars_since": bars_since,
        "active_levels": active_payload,
        "legacy_sweep_type": legacy_type,
        "recent_sweep_valid": bars_since <= 6,
        "reason": "sweep_hunter_approx",
        "params": {"length": length, "filter": vol_filter, "calc_bars": calc_bars},
    }


def merge_sweep_into_liquidity(liq: dict[str, Any], sweep: dict[str, Any]) -> dict[str, Any]:
    """Hunter 最近有效 sweep 时叠加到旧 liq 字段；不删旧检测。"""
    out = dict(liq or {})
    out["sweep_hunter"] = sweep
    if not sweep or not sweep.get("swept") or not sweep.get("recent_sweep_valid"):
        return out
    bars = sweep.get("bars_since")
    legacy_bars = out.get("bars_since_sweep")
    hunter_fresher = bars is not None and (legacy_bars is None or int(bars) <= int(legacy_bars))
    if hunter_fresher:
        out["sweep_type"] = sweep.get("legacy_sweep_type", "none")
        out["reclaim_or_reject"] = sweep.get("reclaim_or_reject") or "none"
        out["sweep_level"] = sweep.get("level")
        out["bars_since_sweep"] = bars
        out["recent_sweep_valid"] = True
        out["sweep_source"] = "sweep_hunter_approx"
    return out


__all__ = ["build_sweep_context", "merge_sweep_into_liquidity"]
