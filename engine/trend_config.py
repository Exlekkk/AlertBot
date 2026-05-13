from __future__ import annotations

TREND_ENGINE_CONFIG = {
    "liquidity": {
        "sweep_lookback": 24,
        "eq_tolerance": 0.001,
        "close_buffer_pct": 0.0004,
        "close_buffer_atr_mult": 0.05,
        "recent_sweep_window": 4,
    },
    "msb": {
        "atr_short_max": 0.55,
        "atr_long_min": 1.05,
        "atr_extended_min": 1.55,
        "range_short_max": 0.25,
        "range_long_min": 0.45,
        "range_extended_min": 0.9,
        "body_short_max": 0.5,
        "body_long_min": 0.58,
        "position_short_max": 0.65,
        "position_long_min": 0.75,
        "short_weak_count_min": 3,
    },
    "score": {
        "htf_aligned_bonus": 8,
        "htf_counter_penalty": -10,
        "htf_strong_counter_penalty": -18,
        "strong_counter_suppress_below": 65,
        "min_alert_score": 45,
        "medium_quality_max": 72,
    },
    "zone": {
        "merge_width_atr_mult": 0.25,
        "continuation_mid_ratio": 0.5,
    },
    "key_zone": {
        "touch_atr_mult": 0.18,
        "touch_pct": 0.0012,
        "range_edge_atr_mult": 0.35,
        "fast_move_atr": 0.85,
        "two_bar_min_atr": 0.55,
        "min_observation_score": 38,
    },
}
