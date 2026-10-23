"""Auto Range Detector — K 线近似（非原版 Pine）。

对照：Auto Range Detector [QuantAlgo]，参数取用户截图（非 Pine 默认）。
本模块是 candle-proxy / approx，不复制受 CC BY-NC-SA 许可的 Pine 源码。
语义见 docs/AMST_EVIDENCE_CONTRACTS_v1.md §2。
"""
from __future__ import annotations

import math
from typing import Any

from engine.indicators import atr as compute_atr
from engine.trend_config import TREND_ENGINE_CONFIG


def _f(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _percentile(sorted_vals: list[float], pct: float) -> float:
    """线性插值百分位；pct 为 0..100。"""
    if not sorted_vals:
        return 0.0
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    p = max(0.0, min(100.0, pct)) / 100.0
    idx = (len(sorted_vals) - 1) * p
    lo = int(math.floor(idx))
    hi = int(math.ceil(idx))
    if lo == hi:
        return sorted_vals[lo]
    w = idx - lo
    return sorted_vals[lo] * (1.0 - w) + sorted_vals[hi] * w


def _regression_slope(values: list[float]) -> float:
    n = len(values)
    if n < 2:
        return 0.0
    mean_x = (n - 1) / 2.0
    mean_y = sum(values) / n
    num = 0.0
    den = 0.0
    for i, y in enumerate(values):
        dx = i - mean_x
        num += dx * (y - mean_y)
        den += dx * dx
    return num / den if den else 0.0


def _empty_auto_range(reason: str = "insufficient_history") -> dict[str, Any]:
    return {
        "state": "none",
        "high": None,
        "low": None,
        "mid": None,
        "q25": None,
        "q75": None,
        "bars_held": 0,
        "height_pct": 0.0,
        "last_event": None,
        "event_bar_ts": None,
        "approx": True,
        "reason": reason,
        "scan_window": 0,
        "upper_touches": 0,
        "lower_touches": 0,
    }


def _band_for_window(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    start: int,
    end: int,
    band_pct: float,
) -> tuple[float, float]:
    """Percentile band：高侧 band_pct，低侧镜像 (100-band_pct)。"""
    wh = sorted(highs[start:end])
    wl = sorted(lows[start:end])
    top = _percentile(wh, band_pct)
    bot = _percentile(wl, 100.0 - band_pct)
    if top < bot:
        top, bot = bot, top
    return top, bot


def _count_touches(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    start: int,
    end: int,
    top: float,
    bot: float,
    tol: float,
    wick_mode: bool,
) -> tuple[int, int, int]:
    upper = lower = 0
    mid = (top + bot) / 2.0
    crossings = 0
    prev_side = 0
    for i in range(start, end):
        h, l, c = highs[i], lows[i], closes[i]
        if wick_mode:
            if h >= top - tol:
                upper += 1
            if l <= bot + tol:
                lower += 1
        else:
            if top - tol <= c <= top + tol:
                upper += 1
            if bot - tol <= c <= bot + tol:
                lower += 1
        side = 1 if c >= mid else -1
        if prev_side and side != prev_side:
            crossings += 1
        prev_side = side
    return upper, lower, crossings


def _evaluate_window(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    end: int,
    window: int,
    atr_now: float,
    height_history: list[float],
    cfg: dict[str, Any],
) -> dict[str, Any] | None:
    start = end - window
    if start < 0:
        return None
    band_pct = float(cfg.get("band_percentile", 90.0))
    top, bot = _band_for_window(highs, lows, closes, start, end, band_pct)
    height = top - bot
    if height <= 0:
        return None

    # Compression：相对历史高度百分位门槛
    compression_pct = float(cfg.get("compression_percentile", 40.0))
    if len(height_history) >= 20:
        hist = sorted(height_history[-(int(cfg.get("calibration_lookback", 500))) :])
        threshold = _percentile(hist, compression_pct)
        if height > threshold:
            return None

    tol = atr_now * float(cfg.get("touch_tolerance_atr", 0.10))
    wick_mode = str(cfg.get("touch_basis", "wick")) == "wick"
    upper_t, lower_t, crossings = _count_touches(
        highs, lows, closes, start, end, top, bot, tol, wick_mode
    )
    min_touches = int(cfg.get("min_touches", 3))
    if upper_t < min_touches or lower_t < min_touches:
        return None

    rotation_rate = crossings / max(window, 1)
    if rotation_rate < float(cfg.get("min_rotation", 0.18)):
        # 短窗：至少 3 次穿越作为地板
        if crossings < 3:
            return None

    slope = abs(_regression_slope(closes[start:end]))
    drift = (slope * window) / height if height else 999.0
    if drift > float(cfg.get("max_drift", 0.45)):
        return None

    inside = sum(1 for c in closes[start:end] if bot <= c <= top)
    containment = inside / max(window, 1)
    if containment < float(cfg.get("min_containment", 0.70)):
        return None

    return {
        "window": window,
        "top": top,
        "bot": bot,
        "start": start,
        "end": end,
        "upper_touches": upper_t,
        "lower_touches": lower_t,
        "rotation_rate": rotation_rate,
        "drift": drift,
        "containment": containment,
        "height": height,
    }


def _extend_anchor(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    start: int,
    end: int,
    top: float,
    bot: float,
    atr_now: float,
    cfg: dict[str, Any],
) -> int:
    """Extend to containment：向左延伸左边缘，允许少量越界。"""
    if str(cfg.get("anchoring", "extend")) != "extend":
        return start
    window = end - start
    limit = min(int(cfg.get("anchor_lookback", 300)), start)
    allowed = max(2, int(round((1.0 - float(cfg.get("min_containment", 0.70))) * window)))
    tol = atr_now * float(cfg.get("touch_tolerance_atr", 0.10))
    outside = 0
    span_start = start
    offset = 0
    while offset < limit and outside <= allowed:
        i = start - 1 - offset
        if i < 0:
            break
        c, h, l = closes[i], highs[i], lows[i]
        closed_in = bot <= c <= top
        fully_in = closed_in and h <= top + tol and l >= bot - tol
        if closed_in:
            outside = max(0, outside - 1)
            if fully_in and (end - i) >= window:
                span_start = i
        else:
            outside += 1
        offset += 1
    return span_start


def build_auto_range_context(klines: list[dict[str, Any]]) -> dict[str, Any]:
    """构建 Auto Range context（契约 §2）。

    仅使用已收盘 K 线（调用方应传入 enrich 后的闭盘序列）。
    Breakout = Close beyond + ATR buffer；Deviation = Failed Acceptance（收回箱内）。
    """
    cfg = TREND_ENGINE_CONFIG.get("auto_range", {})
    base = int(cfg.get("base_length", 20))
    atr_len = int(cfg.get("atr_length", 200))
    scales = cfg.get("scan_scales", [1, 2, 3])  # Base + 2x + 3x
    windows = sorted({base * int(s) for s in scales})
    max_win = max(windows)

    n = len(klines)
    min_need = max(max_win + 5, atr_len // 4, 40)
    if n < min_need:
        return _empty_auto_range("insufficient_history")

    highs = [_f(k.get("high")) for k in klines]
    lows = [_f(k.get("low")) for k in klines]
    closes = [_f(k.get("close")) for k in klines]
    atrs = compute_atr(klines, atr_len)
    atr_now = max(_f(atrs[-1], _f(klines[-1].get("atr"), abs(closes[-1]) * 0.004)), 1e-9)

    # 预计算各长度窗口高度历史（用于 compression 排名）
    calib = int(cfg.get("calibration_lookback", 500))
    height_history: list[float] = []
    hist_win = base
    for i in range(hist_win, n):
        top, bot = _band_for_window(highs, lows, closes, i - hist_win, i, float(cfg.get("band_percentile", 90.0)))
        height_history.append(max(top - bot, 0.0))

    end = n
    candidates: list[dict[str, Any]] = []
    for w in windows:
        # height_history 用到当前 end 之前的样本
        hist_slice = height_history[: max(0, end - hist_win)]
        hit = _evaluate_window(highs, lows, closes, end, w, atr_now, hist_slice[-calib:], cfg)
        if hit:
            candidates.append(hit)

    if not candidates:
        # 无合格 range → 仍检测是否刚发生 breakout 残留；第一刀简化为 none
        return _empty_auto_range("no_qualifying_range")

    # 最长合格窗优先（与 Pine「最长窗口通过全部过滤」一致）
    best = max(candidates, key=lambda c: c["window"])
    left = _extend_anchor(
        highs, lows, closes, best["start"], best["end"], best["top"], best["bot"], atr_now, cfg
    )
    top, bot = best["top"], best["bot"]
    bars_held = end - left
    min_bars = int(cfg.get("min_range_bars", 10))
    state = "live" if bars_held >= min_bars else "provisional"

    close = closes[-1]
    buffer = atr_now * float(cfg.get("breakout_buffer_atr", 0.25))
    absorb_on = bool(cfg.get("absorb_overshoot", True))
    overshoot = atr_now * float(cfg.get("overshoot_tol_atr", 0.25))
    break_confirm = str(cfg.get("break_confirm", "close"))
    merge_dev = bool(cfg.get("merge_deviations", True))
    dev_win = int(cfg.get("deviation_window", 6))

    def _is_break_up(i: int) -> bool:
        if break_confirm == "wick":
            return highs[i] > top + buffer
        return closes[i] > top + buffer

    def _is_break_down(i: int) -> bool:
        if break_confirm == "wick":
            return lows[i] < bot - buffer
        return closes[i] < bot - buffer

    def _inside(i: int) -> bool:
        return bot <= closes[i] <= top

    def _absorb(i: int) -> bool:
        """收盘未破、仅 wick 越界且在 overshoot 内 → 吸收，不算破箱。"""
        if not absorb_on or break_confirm != "close":
            return False
        c = closes[i]
        if highs[i] > top and c <= top + buffer and (highs[i] - top) <= overshoot and not _is_break_up(i):
            return True
        if lows[i] < bot and c >= bot - buffer and (bot - lows[i]) <= overshoot and not _is_break_down(i):
            return True
        return False

    # ---- 跨 bar 状态机（Merge Deviations）----
    # pending_break: None | "up" | "down"；记录首次破箱 bar，后续 dev_win 内收回才记 deviation
    last_event = None
    event_bar_ts = None
    pending_break = None  # type: str | None
    pending_bar = None  # type: int | None
    scan_from = max(left, n - max(dev_win * 3, 24))  # 限制回放窗口

    for i in range(scan_from, n):
        if _absorb(i):
            continue
        broke_up = _is_break_up(i)
        broke_dn = _is_break_down(i)

        if pending_break is not None and pending_bar is not None:
            age = i - pending_bar
            if merge_dev and age >= 1 and age <= dev_win and _inside(i):
                # 破箱后的后续 bar 收回 → Failed Acceptance / Deviation
                last_event = "deviation_up" if pending_break == "up" else "deviation_down"
                event_bar_ts = klines[i].get("open_time")
                pending_break = None
                pending_bar = None
                continue
            if age > dev_win:
                # 窗口耗尽仍未收回 → 确认 breakout（落在破箱 bar 语义上）
                last_event = "breakout_up" if pending_break == "up" else "breakout_down"
                event_bar_ts = klines[pending_bar].get("open_time")
                pending_break = None
                pending_bar = None
                # 若本 bar 又破另一侧，下面继续处理

        if pending_break is None and (broke_up or broke_dn):
            # 同 bar 不可能既破又收回；只登记 pending，等后续 bar
            pending_break = "up" if broke_up else "down"
            pending_bar = i
            if not merge_dev:
                last_event = "breakout_up" if broke_up else "breakout_down"
                event_bar_ts = klines[i].get("open_time")
                pending_break = None
                pending_bar = None

    # 收盘态：仍 pending → broken（等待中）；已 deviation → live；已 breakout → broken
    if pending_break is not None:
        state = "broken"
        if last_event is None:
            # 尚未超时：对外仍报 breakout 方向为「进行中的离开」，但不与 deviation 同 bar
            last_event = "breakout_up" if pending_break == "up" else "breakout_down"
            event_bar_ts = klines[pending_bar].get("open_time") if pending_bar is not None else event_bar_ts
    elif last_event in {"deviation_up", "deviation_down"}:
        state = "live" if bars_held >= min_bars else "provisional"
    elif last_event in {"breakout_up", "breakout_down"}:
        state = "broken"

    mid = (top + bot) / 2.0
    q25 = bot + (top - bot) * 0.25
    q75 = bot + (top - bot) * 0.75
    height_pct = (top - bot) / max(abs(close), 1e-9)

    return {
        "state": state,
        "high": round(top, 2),
        "low": round(bot, 2),
        "mid": round(mid, 2),
        "q25": round(q25, 2),
        "q75": round(q75, 2),
        "bars_held": int(bars_held),
        "height_pct": round(height_pct, 5),
        "last_event": last_event,
        "event_bar_ts": event_bar_ts,
        "approx": True,
        "reason": "auto_range_approx",
        "scan_window": int(best["window"]),
        "upper_touches": int(best["upper_touches"]),
        "lower_touches": int(best["lower_touches"]),
        "atr": round(atr_now, 4),
    }


__all__ = ["build_auto_range_context"]
