"""Quarantined builders no longer on the live decision path.

These modules remain importable for enrich-compat and unit tests.
Do not wire them back into trial / HTF bias / structure-shift scoring.
"""
from __future__ import annotations

__all__ = [
    "build_dual_log_regression_context",
    "build_classic_market_context",
    "build_log_regression_channel",
    "inertial_stochastic_components",
    "inertial_stochastic_proxy_components",
]


def __getattr__(name: str):
    if name in {"build_dual_log_regression_context", "build_log_regression_channel"}:
        from engine.legacy_quarantine import dual_log as mod
        return getattr(mod, name)
    if name == "build_classic_market_context":
        from engine.legacy_quarantine import classic_market as mod
        return getattr(mod, name)
    if name in {"inertial_stochastic_components", "inertial_stochastic_proxy_components"}:
        from engine.legacy_quarantine import inertial as mod
        return getattr(mod, name)
    raise AttributeError(name)
