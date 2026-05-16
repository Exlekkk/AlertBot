# TradingDexCat AlertBot Changelog

## v1.3.2-adaptive-shadow-cadence

Status: shadow-only.  
Deployment safety: does not change 1H official scanner logic.

### Reason for this version

The 15m layer should help find possible long/short entry locations before 1H confirmation, but it must not become a fixed daily quota system.  A normal-market reference of 1-4 signals/day is useful for review, but active days can validly produce more reminders.

The correct rule is:
- suppress duplicate same-zone reminders;
- suppress rapid long/short flip-flops in the same 1H area;
- allow high-quality new-information setups to pass with shorter cooldown.

### Main changes

1. Adaptive cadence instead of hard daily caps
   - added `fast_cooldown_bars`
   - added `opposite_side_cooldown_bars`
   - added `high_quality_score`
   - added `cadence_mode` and `recommended_cooldown_bars` diagnostics

2. Better noise accounting in shadow tests
   - backtest now tracks duplicate skips separately from contradiction skips
   - CSV includes `zone_cluster_hash`, `cadence_mode`, and `recommended_cooldown_bars`

3. 15m/1H isolation remains unchanged
   - 15m remains shadow-only
   - 15m does not alter 1H scoring, titles, conclusions, cooldowns, or Telegram copy

### Review target

Do not reject a good active day only because it has more than 4 reminders.  Check whether each reminder has new structure information and whether repeated same-zone noise is being skipped.


## v1.3.1-shadow-entry-tighten

Status: shadow-only.  
Deployment safety: does not change 1H official scanner logic.

### Reason for this version

v1.3.0 15m shadow backtest became too noisy after rebuilding the entry engine:
- 61 signals in 7 days
- about 7.62 signals per active day
- long win rate about 20.7%
- short win rate about 43.8%

The main problem was not missing direction coverage anymore. Both long and short appeared, but 15m allowed too many weak entry-location reminders.

### Main changes

1. Tightened default 15m config
   - higher minimum trigger score
   - lower maximum risk percentage
   - narrower maximum zone width
   - longer same-zone cooldown

2. Added 1H context alignment
   - reject long prealerts during clear 1H sweep-high-failed context
   - reject short prealerts during clear 1H sweep-low-reclaim context

3. Strengthened anti-noise gates
   - local 15m sweep must also react at a 1H POI or key level
   - non-sweep setup must have key-level reaction, aligned momentum, and candle confirmation
   - FVG-only and zone-touch-only setups remain invalid

4. Kept isolation
   - 15m remains shadow-only
   - 15m does not alter 1H scoring, copy, cooldown, or Telegram output

5. README cleanup
   - GitHub README is now concise, English-only, and focused on future model handoff.

### Next review target

Run 7-day and 14-day shadow backtests.  
Target range:
- 1 to 4 signals per active day
- both long and short can still appear
- win rate should improve materially
- failed signals should be explainable from CSV diagnostics



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
