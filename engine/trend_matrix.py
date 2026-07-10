from __future__ import annotations

from typing import Any

from engine.chart_indicators import build_classic_market_context, build_dual_log_regression_context


def build_trend_matrix_proxy(klines_1h: list[dict[str, Any]]) -> dict[str, Any]:
    """Backward-compatible adapter backed by the supplied log channels.

    The old EMA trend-matrix proxy is no longer part of the decision framework.
    Existing callers keep the ``matrix_direction`` field, but it now represents
    classical trend/channel alignment from Dual Log Regression Channels.
    """

    context = build_dual_log_regression_context(klines_1h)
    classic = build_classic_market_context(klines_1h)
    alignment = str(context.get("alignment", "neutral"))
    direction = alignment if alignment in {"bull", "bear"} else "neutral"
    return {
        "matrix_direction": direction,
        "support_score": 1 if direction != "neutral" else 0,
        "source": "dual_log_regression",
        "macro_channel": context.get("macro", {}),
        "short_channel": context.get("short", {}),
        "channel_alignment": alignment,
        "classic_market": classic,
    }
