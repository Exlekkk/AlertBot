from __future__ import annotations

from typing import Any


def build_trend_matrix_proxy(klines_1h: list[dict[str, Any]]) -> dict[str, Any]:
    """Peeled adapter: dual-log / classic-swing no longer feed decisions.

    Callers keep the ``matrix_direction`` field for backward compatibility, but
    the live value stays neutral so structure-shift scoring cannot lean on
    channel or classic-swing alignment.
    """

    _ = klines_1h
    return {
        "matrix_direction": "neutral",
        "support_score": 0,
        "source": "peeled",
        "macro_channel": {},
        "short_channel": {},
        "channel_alignment": "neutral",
        "classic_market": {},
    }
