"""Quarantined inertial oscillator builders.

Peeled from live trial / aux / 15m turn scoring. Still used by enrich_klines
for field-compat and by unit tests.
"""
from __future__ import annotations

def _sma(values: list[float], period: int) -> list[float]:
    out: list[float] = []
    running = 0.0
    for i, value in enumerate(values):
        running += value
        if i >= period:
            running -= values[i - period]
        out.append(running / min(i + 1, period))
    return out


def inertial_stochastic_components(
    klines: list[dict],
    min_length: int = 10,
    max_length: int = 40,
    smooth_k: int = 3,
    smooth_d: int = 3,
) -> dict[str, list]:
    """Length-adaptive stochastic-style oscillator (closed candles)."""

    if not klines:
        return {
            "value": [],
            "signal": [],
            "green": [],
            "red": [],
            "turn_up": [],
            "turn_down": [],
        }

    min_length = max(2, int(min_length))
    max_length = max(min_length, int(max_length))
    selected: list[float] = []
    previous_selected = 50.0
    for i, bar in enumerate(klines):
        best = 50.0
        minimum_difference = float("inf")
        close = float(bar["close"])
        for length in range(min_length, max_length + 1):
            if i + 1 < length:
                continue
            window = klines[i - length + 1 : i + 1]
            low = min(float(item["low"]) for item in window)
            high = max(float(item["high"]) for item in window)
            candidate = 50.0 if high <= low else 100.0 * (close - low) / (high - low)
            difference = abs(candidate - previous_selected)
            if difference < minimum_difference:
                minimum_difference = difference
                best = candidate
        if minimum_difference == float("inf"):
            best = previous_selected
        best = max(0.0, min(100.0, best))
        selected.append(best)
        previous_selected = best

    value = _sma(selected, max(1, int(smooth_k)))
    signal = _sma(value, max(1, int(smooth_d)))
    green = [v > 50.0 for v in value]
    red = [not item for item in green]
    turn_up = [False] + [value[i] > 50.0 and value[i - 1] <= 50.0 for i in range(1, len(value))]
    turn_down = [False] + [value[i] < 50.0 and value[i - 1] >= 50.0 for i in range(1, len(value))]
    return {
        "raw": selected,
        "value": value,
        "signal": signal,
        "green": green,
        "red": red,
        "turn_up": turn_up,
        "turn_down": turn_down,
    }


def inertial_stochastic_proxy_components(
    klines: list[dict],
    length: int = 14,
    smooth_k: int = 3,
    smooth_signal: int = 3,
) -> dict[str, list]:
    """Compatibility alias for older callers."""

    return inertial_stochastic_components(
        klines,
        min_length=max(2, min(int(length), 10)),
        max_length=max(40, int(length)),
        smooth_k=smooth_k,
        smooth_d=smooth_signal,
    )


__all__ = ["inertial_stochastic_components", "inertial_stochastic_proxy_components"]
