# TradingDexCat AlertBot Changelog

## v1.3.0-shadow-entry-engine

Status: shadow-only.  
Deployment safety: does not change 1H official scanner logic.

### Reason for this version

Previous 15m shadow result:
- 8 signals
- 0 long
- 8 short
- short win rate 50%

The issue was not pure noise. The issue was that 15m logic was not fully aligned with the framework:
- 15m should find entry locations before 1H confirmation;
- 15m must remain subordinate to 1H/4H;
- 15m must avoid fake single-factor triggers.

### Main changes

1. Rebuilt `engine/prealert_15m.py`
   - introduced explicit 15m early-entry design
   - added local 15m sweep-high/sweep-low detection
   - separated long and short setup scoring
   - added anti-noise gates
   - added key-level context
   - added shadow-only metadata

2. Kept 1H isolated
   - 15m result is not used by `engine/scanner.py`
   - 15m result does not alter 1H score
   - 15m result does not alter 1H message copy
   - 15m result remains backtest/log only

3. Improved backtest diagnostics
   Added CSV fields:
   - `setup_type`
   - `liquidity_event`
   - `structure_context`
   - `poi_type`
   - `key_level_context`
   - `reaction_type`
   - `momentum_filter`
   - `tai_regime`
   - `early_entry_reason`
   - `trigger_score`
   - `risk_pct`
   - `room_pct`
   - `zone_width_pct`
   - `rar_now`
   - `rar_trigger`
   - `price_impulse`
   - `volume_ratio`

4. Logger robustness
   - if `/opt/smct-alert/logs` cannot be created locally, logging falls back to stderr.
   - this avoids import failure during tests or local review.

### What this version intentionally does not do

- It does not enable 15m Telegram.
- It does not modify 1H official alert text.
- It does not modify 1H scanner loop.
- It does not add stocks.
- It does not reintroduce MACD.

### Next test target

Run:
- 7 days
- 14 days
- 30 days

Minimum review standards:
- long and short should both appear;
- approximate signals/day should remain controlled;
- failed signals should have explainable reasons;
- lead-to-1H-close should be early enough to matter;
- no single FVG / single TAI / single touch trigger should dominate.
