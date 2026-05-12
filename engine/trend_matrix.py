from __future__ import annotations

from typing import Any


def build_trend_matrix_proxy(klines_1h: list[dict[str, Any]]) -> dict[str, Any]:
    fast = float(klines_1h[-1].get("ema10", klines_1h[-1]["close"]))
    slow = float(klines_1h[-1].get("ema20", klines_1h[-1]["close"]))
    direction = "bull" if fast > slow else "bear" if fast < slow else "neutral"
    return {"matrix_direction": direction, "support_score": 1 if direction != "neutral" else 0}
