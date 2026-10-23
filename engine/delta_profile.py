"""3D Delta Profile + POC — K 线近似（契约 §4）。

对照：LuxAlgo 3D Delta Profile；**非真实 footprint / trade-delta**。
label 固定为 candle_delta_proxy。参数：Length=200 / Buckets=35 / VA%=70。
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


def build_delta_profile_context(klines: list[dict[str, Any]]) -> dict[str, Any]:
    cfg = TREND_ENGINE_CONFIG.get("delta_profile", {})
    length = int(cfg.get("length", 200))
    buckets = max(5, int(cfg.get("buckets", 35)))
    va_pct = float(cfg.get("value_area_pct", 70.0)) / 100.0
    anomaly = float(cfg.get("anomaly_threshold", 2.5))

    empty = {
        "poc": None,
        "vah": None,
        "val": None,
        "value_area_pos": "inside",
        "node_bias": "neutral",
        "label": "candle_delta_proxy",
        "approx": True,
        "candle_proxy": True,
        "buy_vol": 0.0,
        "sell_vol": 0.0,
        "imbalance_ratio": 0.0,
        "hvn_lvn": [],
        "reason": "insufficient_history",
        "params": {
            "length": length,
            "buckets": buckets,
            "value_area_pct": va_pct * 100.0,
            "anomaly_threshold": anomaly,
        },
    }
    if len(klines) < max(30, length // 4):
        return empty

    window = klines[-min(len(klines), length):]
    highs = [_f(k.get("high")) for k in window]
    lows = [_f(k.get("low")) for k in window]
    opens = [_f(k.get("open")) for k in window]
    closes = [_f(k.get("close")) for k in window]
    volumes = [_f(k.get("volume")) for k in window]

    price_hi = max(highs)
    price_lo = min(lows)
    if price_hi <= price_lo:
        out = dict(empty)
        out["reason"] = "flat_range"
        return out

    step = (price_hi - price_lo) / buckets
    buy_bins = [0.0] * buckets
    sell_bins = [0.0] * buckets
    total_bins = [0.0] * buckets
    delta_bins = [0.0] * buckets

    for o, h, l, c, v in zip(opens, highs, lows, closes, volumes):
        if v <= 0 or h < l:
            continue
        # candle_proxy：涨 bar buy 主导，跌 bar sell；按高低跨 bin 均摊
        buy_share = 0.55 if c >= o else 0.45
        sell_share = 1.0 - buy_share
        i0 = max(0, min(buckets - 1, int((l - price_lo) / step)))
        i1 = max(0, min(buckets - 1, int((h - price_lo) / step)))
        if i1 < i0:
            i0, i1 = i1, i0
        span = i1 - i0 + 1
        per = v / span
        signed = (buy_share - sell_share) * per
        for i in range(i0, i1 + 1):
            buy_bins[i] += per * buy_share
            sell_bins[i] += per * sell_share
            total_bins[i] += per
            delta_bins[i] += signed

    buy_vol = sum(buy_bins)
    sell_vol = sum(sell_bins)
    total_vol = buy_vol + sell_vol
    if total_vol <= 0:
        out = dict(empty)
        out["reason"] = "zero_volume"
        return out

    poc_idx = max(range(buckets), key=lambda i: total_bins[i])
    poc = price_lo + (poc_idx + 0.5) * step

    included = {poc_idx}
    cum = total_bins[poc_idx]
    target = total_vol * va_pct
    lo_i, hi_i = poc_idx, poc_idx
    while cum < target and (lo_i > 0 or hi_i < buckets - 1):
        left = total_bins[lo_i - 1] if lo_i > 0 else -1.0
        right = total_bins[hi_i + 1] if hi_i < buckets - 1 else -1.0
        if right >= left and hi_i < buckets - 1:
            hi_i += 1
            included.add(hi_i)
            cum += total_bins[hi_i]
        elif lo_i > 0:
            lo_i -= 1
            included.add(lo_i)
            cum += total_bins[lo_i]
        else:
            break
    vah = price_lo + (hi_i + 1) * step
    val = price_lo + lo_i * step

    close = closes[-1]
    if close > vah:
        va_pos = "above"
    elif close < val:
        va_pos = "below"
    else:
        va_pos = "inside"

    # node_bias：VA 内桶累计 signed delta
    va_delta = sum(delta_bins[i] for i in included)
    if va_delta > total_vol * 0.02:
        node_bias = "bull"
    elif va_delta < -total_vol * 0.02:
        node_bias = "bear"
    else:
        node_bias = "neutral"

    imbalance = (buy_vol - sell_vol) / total_vol
    mean_vol = total_vol / buckets
    hvn_lvn = []
    for i, vol in enumerate(total_bins):
        mid = price_lo + (i + 0.5) * step
        if mean_vol > 0 and vol >= mean_vol * anomaly:
            hvn_lvn.append({"price": round(mid, 2), "kind": "HVN", "vol": round(vol, 2)})
        elif mean_vol > 0 and 0 < vol <= mean_vol / anomaly:
            hvn_lvn.append({"price": round(mid, 2), "kind": "LVN", "vol": round(vol, 2)})

    return {
        "poc": round(poc, 2),
        "vah": round(vah, 2),
        "val": round(val, 2),
        "value_area_pos": va_pos,
        "node_bias": node_bias,
        "label": "candle_delta_proxy",
        "approx": True,
        "candle_proxy": True,
        "buy_vol": round(buy_vol, 2),
        "sell_vol": round(sell_vol, 2),
        "imbalance_ratio": round(imbalance, 4),
        "hvn_lvn": hvn_lvn[:24],
        "reason": "delta_profile_approx",
        "params": empty["params"],
    }


def merge_delta_into_vp(vp: dict[str, Any], delta: dict[str, Any]) -> dict[str, Any]:
    """3D Delta 叠加到旧 VP；不删旧 POC。"""
    out = dict(vp or {})
    out["delta_profile"] = delta
    if not delta or delta.get("poc") is None:
        return out
    if out.get("poc") is None:
        out["poc"] = delta.get("poc")
    if out.get("vah") is None:
        out["vah"] = delta.get("vah")
    if out.get("val") is None:
        out["val"] = delta.get("val")
    out["value_area_pos"] = delta.get("value_area_pos", out.get("value_area_pos"))
    out["node_bias"] = delta.get("node_bias", "neutral")
    out["delta_source"] = "delta_profile_approx"
    out["delta_label"] = delta.get("label", "candle_delta_proxy")
    return out


__all__ = ["build_delta_profile_context", "merge_delta_into_vp"]
