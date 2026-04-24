from __future__ import annotations

from typing import Any

from engine.x_signals import (
    MIN_15M_ABNORMAL_VOLUME,
    MIN_1H_ABNORMAL_VOLUME,
    detect_x_signals,
)


def detect_abnormal_signals(
    symbol: str,
    klines_1d: list[dict[str, Any]],
    klines_4h: list[dict[str, Any]],
    klines_1h: list[dict[str, Any]],
    klines_15m: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Backward-compatible abnormal entrypoint.

    XSignals is the single source of truth for abnormal-event detection.
    Keep this wrapper so older imports of engine.abnormal do not break.
    """

    return detect_x_signals(symbol, klines_1d, klines_4h, klines_1h, klines_15m)


__all__ = [
    "MIN_15M_ABNORMAL_VOLUME",
    "MIN_1H_ABNORMAL_VOLUME",
    "detect_abnormal_signals",
    "detect_x_signals",
]
