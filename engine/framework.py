from __future__ import annotations

from typing import Any

from engine.chart_indicators import build_chart_context
from engine.liquidity import build_liquidity_context


def _vote(scores: dict[str, float], side: str, weight: float) -> None:
    if side in scores:
        scores[side] += float(weight)


def relation_to_htf(htf_ctx: dict[str, Any], direction_1h: str) -> str:
    """Return the 4H relation for the direction actually being evaluated."""

    if direction_1h not in {"long", "short"}:
        return "neutral"
    h4 = str(htf_ctx.get("h4_direction", ""))
    text = str(htf_ctx.get("text", ""))
    if h4 not in {"bull", "bear", "range"}:
        h4 = "bull" if "偏多" in text else "bear" if "偏空" in text else "range"
    if h4 == "range":
        return "neutral"
    aligned = (h4 == "bull" and direction_1h == "long") or (h4 == "bear" and direction_1h == "short")
    if aligned:
        return "aligned"
    try:
        strength = float(htf_ctx.get("h4_strength", 0.0))
    except (TypeError, ValueError):
        strength = 0.0
    if "h4_strength" not in htf_ctx and htf_ctx.get("relation") == "strong_counter":
        strength = 1.0
    return "strong_counter" if strength >= 0.75 else "counter"


def build_htf_bias_context(
    klines_4h: list[dict[str, Any]],
    direction_1h: str = "neutral",
    *,
    liquidity: dict[str, Any] | None = None,
    msb: dict[str, Any] | None = None,
    ict: dict[str, Any] | None = None,
    chart: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """4H bias from liquidity sweep + fibonacci OTE context.

    EMA crosses, dual-log, classic swing, ICT structure and MSB-OB votes are
    hard-deleted from this path. Background vote only; never a 4H entry signal.
    """

    if not klines_4h:
        return {"h4_direction": "range", "relation": "neutral", "text": "4H 震荡", "h4_strength": 0.0}
    liquidity = liquidity or build_liquidity_context(klines_4h)
    msb = msb or {"direction": "neutral"}
    ict = ict or {}
    chart = chart or build_chart_context(klines_4h)
    _ = (msb, ict)

    scores = {"bull": 0.0, "bear": 0.0}
    evidence: list[str] = []

    fibonacci = chart.get("fibonacci", {})
    fib_direction = str(fibonacci.get("trend", "neutral"))
    if fib_direction in scores:
        _vote(scores, fib_direction, 1.5)
        evidence.append(f"fibonacci_{fib_direction}")

    if liquidity.get("recent_sweep_valid"):
        if liquidity.get("sweep_type") == "sellside" and liquidity.get("reclaim_or_reject") == "reclaim":
            _vote(scores, "bull", 1.5)
            evidence.append("sellside_sweep_reclaim")
        elif liquidity.get("sweep_type") == "buyside" and liquidity.get("reclaim_or_reject") == "reject":
            _vote(scores, "bear", 1.5)
            evidence.append("buyside_sweep_reject")

    difference = scores["bull"] - scores["bear"]
    if difference >= 2.0:
        h4 = "bull"
    elif difference <= -2.0:
        h4 = "bear"
    else:
        h4 = "range"
    strength = min(1.0, abs(difference) / 7.5)
    context = {
        "h4_direction": h4,
        "h4_raw_direction": "bull" if difference > 0 else "bear" if difference < 0 else "neutral",
        "text": "4H 震荡" if h4 == "range" else "4H 偏多" if h4 == "bull" else "4H 偏空",
        "h4_strength": strength,
        "bias_scores": scores,
        "bias_evidence": evidence,
        "premium_discount": fibonacci.get("premium_discount", "unknown"),
        "market_cycle": "unknown",
        "source": "fibonacci_liquidity_bias",
    }
    context["relation"] = relation_to_htf(context, direction_1h)
    return context
