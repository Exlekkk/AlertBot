"""Unclosed (forming) abnormal-volume weak reminder — isolated from 1H formal trial.

L lock (2026-10-25): necessary product path for forming-bar abnormal volume.
Must NOT mutate 1H cooldown, observation pending, formal scores, or formal
title family (试多/试空). Formal 1H stays closed-candle; forming-bar read is
OK for this weak path only.

Env kill switch: SMCT_ABNORMAL_VOLUME_WEAK_ENABLED default 0 (TG off).
Shadow / log path always available via scripts/run_volume_weak_shadow.py.
No systemd unit in this PR (deferred until after merge + user awake).
"""
from __future__ import annotations

import os
from typing import Any

from engine.x_signals import MIN_15M_ABNORMAL_VOLUME, MIN_1H_ABNORMAL_VOLUME

# L-locked frequency (2026-10-25): prefer miss over false positive.
DEFAULT_MIN_VOLUME_RATIO = 1.8
DEFAULT_COOLDOWN_BARS_15M = 4  # same side
DEFAULT_OPPOSITE_COOLDOWN_BARS = 2
VOLUME_WEAK_SIGNAL_LONG = "VOLUME_WEAK_LONG"
VOLUME_WEAK_SIGNAL_SHORT = "VOLUME_WEAK_SHORT"


def _float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _volume_ratio(k: dict[str, Any]) -> float:
    return _float(k.get("volume")) / max(_float(k.get("vol_sma20"), 0.0), 1e-9)


def _fmt_vol(vol: Any) -> str:
    try:
        return str(int(round(float(vol))))
    except (TypeError, ValueError):
        return "0"


def _fmt_ratio(ratio: Any) -> str:
    try:
        return f"{float(ratio):.1f}"
    except (TypeError, ValueError):
        return "0.0"


def abnormal_volume_weak_enabled() -> bool:
    """TG outbound gate; default off. Shadow/log does not require this."""
    return os.getenv("SMCT_ABNORMAL_VOLUME_WEAK_ENABLED", "0").strip() == "1"


def evaluate_forming_volume_weak(
    symbol: str,
    klines_15m_including_forming: list[dict[str, Any]],
    klines_1h_including_forming: list[dict[str, Any]] | None = None,
    *,
    min_volume_ratio: float = DEFAULT_MIN_VOLUME_RATIO,
    min_abs_volume_15m: float = MIN_15M_ABNORMAL_VOLUME,
    min_abs_volume_1h: float = MIN_1H_ABNORMAL_VOLUME,
) -> dict[str, Any]:
    """Evaluate forming-bar abnormal volume for a weak reminder.

    Expects klines with the **last** bar possibly still open (forming).
    Returns a decision dict; never touches formal 1H state stores.

    Frequency (L-locked): ratio >= 1.8 AND abs volume above x_signals floors
    (15m OR 1H). Prefer miss over false positive.
    """
    base: dict[str, Any] = {
        "symbol": symbol,
        "should_alert": False,
        "reason": "insufficient_history",
        "forming": True,
        "family": "volume_weak",
        "formal_1h_isolated": True,
    }
    if len(klines_15m_including_forming) < 3:
        return base

    k15 = klines_15m_including_forming[-1]
    k1h = None
    if klines_1h_including_forming and len(klines_1h_including_forming) >= 1:
        k1h = klines_1h_including_forming[-1]

    vol_15m = _float(k15.get("volume"))
    ratio_15m = _volume_ratio(k15)
    vol_1h = _float(k1h.get("volume")) if k1h else 0.0
    ratio_1h = _volume_ratio(k1h) if k1h else 0.0

    hard_ok = vol_15m > min_abs_volume_15m or vol_1h > min_abs_volume_1h
    ratio_ok = ratio_15m >= min_volume_ratio or ratio_1h >= min_volume_ratio
    if not hard_ok or not ratio_ok:
        base["reason"] = "volume_not_abnormal"
        base["volume_15m"] = vol_15m
        base["volume_ratio_15m"] = round(ratio_15m, 3)
        base["volume_1h"] = vol_1h
        base["volume_ratio_1h"] = round(ratio_1h, 3)
        return base

    open_px = _float(k15.get("open"))
    close_px = _float(k15.get("close"))
    if close_px > open_px:
        side = "long"
        signal = VOLUME_WEAK_SIGNAL_LONG
    elif close_px < open_px:
        side = "short"
        signal = VOLUME_WEAK_SIGNAL_SHORT
    else:
        base["reason"] = "flat_forming_body"
        base["volume_15m"] = vol_15m
        base["volume_ratio_15m"] = round(ratio_15m, 3)
        return base

    open_time = int(k15.get("open_time") or 0)
    return {
        "symbol": symbol,
        "should_alert": True,
        "reason": "forming_abnormal_volume",
        "forming": True,
        "family": "volume_weak",
        "formal_1h_isolated": True,
        "signal": signal,
        "direction": side,
        "side": side,
        "price": close_px,
        "open_time": open_time,
        "volume_15m": vol_15m,
        "volume_ratio_15m": round(ratio_15m, 3),
        "volume_1h": vol_1h,
        "volume_ratio_1h": round(ratio_1h, 3),
        "recommended_cooldown_bars": DEFAULT_COOLDOWN_BARS_15M,
        "opposite_cooldown_bars": DEFAULT_OPPOSITE_COOLDOWN_BARS,
        "tg_enabled": abnormal_volume_weak_enabled(),
    }


def format_volume_weak_log(decision: dict[str, Any]) -> str:
    if not decision.get("should_alert"):
        return (
            f"no_volume_weak symbol={decision.get('symbol')} "
            f"reason={decision.get('reason')} "
            f"vol15={decision.get('volume_15m')} ratio15={decision.get('volume_ratio_15m')}"
        )
    return (
        "would_send_volume_weak "
        f"symbol={decision.get('symbol')} side={decision.get('side')} "
        f"signal={decision.get('signal')} price={decision.get('price')} "
        f"vol15={decision.get('volume_15m')} ratio15={decision.get('volume_ratio_15m')} "
        f"tg_enabled={decision.get('tg_enabled')}"
    )


def format_volume_weak_message(decision: dict[str, Any]) -> str:
    """L-locked TG copy (2026-10-25). Forbidden: 试多/试空 formal family.

    Only call when should_alert; TG send still gated by abnormal_volume_weak_enabled().
    """
    side = str(decision.get("side") or "")
    if side == "long":
        side_zh = "偏多🟢"
    elif side == "short":
        side_zh = "偏空🔴"
    else:
        side_zh = "中性"
    symbol = str(decision.get("symbol") or "BTCUSDT").replace("USDT", "")
    vol_s = _fmt_vol(decision.get("volume_15m"))
    ratio_s = _fmt_ratio(decision.get("volume_ratio_15m"))
    return (
        f"📍 {symbol} 未收盘放量弱提醒\n"
        f"\n"
        f"15m 未收盘出现异常放量（{side_zh}）。\n"
        f"vol≈{vol_s}  ratio≈{ratio_s}\n"
        f"这不是 1H 正式观察，只提醒看盘。\n"
        f"最终以 1H / 4H 为准。"
    )


# Back-compat alias.
format_volume_weak_message_draft = format_volume_weak_message


def should_send_volume_weak_tg(decision: dict[str, Any]) -> bool:
    """True only when candidate fires AND env kill switch is on."""
    return bool(decision.get("should_alert")) and abnormal_volume_weak_enabled()


__all__ = [
    "DEFAULT_COOLDOWN_BARS_15M",
    "DEFAULT_MIN_VOLUME_RATIO",
    "DEFAULT_OPPOSITE_COOLDOWN_BARS",
    "VOLUME_WEAK_SIGNAL_LONG",
    "VOLUME_WEAK_SIGNAL_SHORT",
    "abnormal_volume_weak_enabled",
    "evaluate_forming_volume_weak",
    "format_volume_weak_log",
    "format_volume_weak_message",
    "format_volume_weak_message_draft",
    "should_send_volume_weak_tg",
]
