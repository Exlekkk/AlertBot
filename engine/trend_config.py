from __future__ import annotations

TREND_ENGINE_CONFIG = {
    "chart_framework": {
        # Values transcribed from the user's BTC 15m / 1H TradingView layout
        # and the three ICT settings screenshots supplied with the Pine bundle.
        "ict": {
            "mode": "Historical",
            "structure_length": 6,
            "show_mss": True,
            "show_bos": False,
            "show_displacement": False,
            "show_volume_imbalance": False,
            "ob_swing_lookback": 14,
            "visible_bullish_ob": 1,
            "visible_bearish_ob": 1,
            "historical_polarity_changes": False,
            "use_candle_body": False,
            "liquidity_margin": 5.0,
            "visible_liquidity_boxes": 2,
            "show_fvg": True,
            "balance_price_range": False,
            "fvg_mode": "FVG",
            "visible_fvg": 2,
            "show_nwog": False,
            "show_ndog": False,
            "fibonacci_source": "NONE",
            "extend_fibonacci": False,
            "show_killzones": False,
        },
        "msb_ob": {
            "zigzag_length": 9,
            "fib_factor": 0.33,
        },
        "dual_log_regression": {
            "macro_length": 300,
            "macro_width": 2.0,
            "macro_bins": 50,
            "macro_extension_bars": 50,
            "short_length": 50,
            "short_width": 1.5,
            "short_bins": 50,
            "short_extension_bars": 20,
        },
        "high_volume_pivots": {
            "resistance_length": 40,
            "support_length": 40,
            "volume_ma_length": 20,
            "volume_multiplier": 1.2,
            "atr_length": 200,
        },
        "fvg_volume_profile": {
            # The custom lower-timeframe input displayed on the chart is 13.
            # Binance has no native 13-minute candle.  The bot profiles with
            # available closed 15m candles and labels that part as a proxy.
            "lower_timeframe_input": "13",
            "bins": 20,
            "gap_filter": 0.6,
            "max_active": 10,
        },
        "fibonacci_ote": {
            "pivot_length": 10,
            "ote_low": 0.618,
            "ote_high": 0.786,
            "levels": (0.0, 0.236, 0.382, 0.5, 0.618, 0.705, 0.786, 0.79, 1.0),
            "extensions": (1.272, 1.618),
        },
        "rar": {"length": 15, "power": 1.0},
        "inertial": {"min_length": 10, "max_length": 40, "smooth_k": 3, "smooth_d": 3},
        "tai": {"formation_length": 30, "history_length": 350},
        "killzones": {
            "new_york": ("America/New_York", "07:00", "09:00"),
            "london_open": ("Europe/London", "07:00", "10:00"),
            "london_close": ("Europe/London", "15:00", "17:00"),
            "asian": ("Asia/Tokyo", "10:00", "14:00"),
        },
    },
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
    "htf": {
        "range_strength_max": 0.45,
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
    "ict_ob": {
        # Exact +OB/-OB values may be supplied by an external TradingView
        # adapter.  Otherwise the supplied LuxAlgo Pine logic is translated
        # from closed candles; these bounds only limit decision-active zones.
        "max_active_distance_atr": 5.0,
        "max_conflict_width_atr": 8.0,
        "max_conflict_width_pct": 0.04,
    },
    "key_zone": {
        "touch_atr_mult": 0.18,
        "touch_pct": 0.0012,
        "range_edge_atr_mult": 0.35,
        "fast_move_atr": 0.85,
        "two_bar_min_atr": 0.55,
        "min_observation_score": 46,
        "min_realert_bars": 4,
        "range_edge_requires_context": True,
        "structural_zone_requires_context": True,
    },
    "range_lock": {
        # Sideways / accumulation lock.  The bot should not keep generating new
        # 1H key zones while price is rotating inside the same accepted value
        # box.  It may still speak when there is a real breakout/acceptance or a
        # high-impulse sweep-reclaim.
        "lookback_bars": 14,
        "max_range_atr": 3.4,
        "max_range_pct": 0.024,
        "min_edge_touches": 3,
        "cooldown_bars": 8,
        "box_shift_atr_mult": 1.25,
        "breakout_accept_atr_mult": 0.35,
        "strong_reversal_atr": 1.35,
        "strong_reversal_volume_ratio": 1.15,
    },
    # --- AMST 证据源参数（用户截图，非 Pine 默认）；见 docs/AMST_EVIDENCE_CONTRACTS_v1.md ---
    "auto_range": {
        "scan_scales": [1, 2, 3],  # Base + 2x + 3x
        "base_length": 20,
        "band_percentile": 90.0,
        "signal_timing": "bar_close",
        "atr_length": 200,
        "compression_percentile": 40.0,
        "calibration_lookback": 500,
        "min_rotation": 0.18,
        "touch_basis": "wick",
        "min_touches": 3,
        "touch_tolerance_atr": 0.10,
        "max_drift": 0.45,
        "min_containment": 0.70,
        "anchoring": "extend",
        "anchor_lookback": 300,
        "min_range_bars": 10,
        "absorb_overshoot": True,
        "overshoot_tol_atr": 0.25,
        "break_confirm": "close",
        "breakout_buffer_atr": 0.25,
        "merge_deviations": True,
        "deviation_window": 6,
        "cooldown_bars": 5,
        "max_range_age": 0,
    },
    "sweep_hunter": {
        "length": 10,
        "filter": 1.0,
        "max_line_width": 4,
        "min_transparency": 0,
        "max_transparency": 60,
        "calc_bars": 700,
    },
    "delta_profile": {
        "length": 200,
        "buckets": 35,
        "value_area_pct": 70.0,
        "highlight_hvol": False,
        "anomaly_threshold": 2.5,
    },
    "ifvg": {
        "min_size_1h": 0.2,
        "min_size_15m": 0.15,
        "longevity": 500,
        "calc_bars": 2000,
        "display_mode": "Both",
    },
    "ote": {
        "pivot": 10,
        "upper": 0.786,
        "lower": 0.618,
    },
    "rar": {
        "length": 15,
        "power": 1,
        "source": "close",
    },
    "tai": {
        "formation": 30,
        "history": 350,
        "timeframes": ["15m"],
    },
    "rsi_heatmap": {
        "max_levels": 5,
        "rsi_length": 14,
        "signal_length": 14,
        "midline_squeeze": True,
        "dashboard": False,
        "timeframes": ["1h", "4h"],  # 仅 1H+；滤镜，不单独告警
    },
    "trial_decision": {
        # Formal 1H trial alerts use weighted evidence.  No individual
        # auxiliary indicator is required; hard blocks are reserved for poor
        # location, invalid risk, stale/chased entries, or a clear opposite
        # structure advantage.
        "formal_min_score": 7.0,
        "range_mid_min_score": 10.0,
        "early_trial_min_score": 8.0,
        "direction_advantage_min": 1.0,
        "opposite_conflict_margin": 2.5,
        "max_zone_chase_atr": 1.0,
        "max_recent_extension_atr": 2.3,
        "max_risk_atr": 2.4,
        "max_risk_pct": 0.018,
        "min_range_reward_risk": 0.80,
        "range_lower_cut": 0.38,
        "range_upper_cut": 0.62,
        "opposite_flip_cooldown_bars": 6,
        "same_side_formal_cooldown_bars": 12,
        "secondary_min_progress_atr": 0.22,
        "secondary_max_chase_atr": 1.05,
        "pending_confirm_expire_bars": 4,
    },
}
