# TradingDexCat AlertBot Changelog

## v1.4.0-btc-smc-ict-chart-alignment

Status: BTC Pine-framework alignment and decision-path replacement.
Deployment safety: 1H remains the only production Telegram layer; 15m remains shadow-only.

### Scope and source

The user supplied the Pine sources used on the BTC 15m/1H layout plus screenshots of the custom ICT settings. US-stock analysis is not part of AlertBot. The fixed hierarchy is 4H direction, 1H structure and official alert, 15m entry-location shadow.

### Main changes

1. SMC/ICT core
   - translated ICT zigzag structure with MSS/BOS selection matching the Pine array logic;
   - translated custom order-block swing logic with full-wick zones, breaker polarity and mitigation state;
   - added ICT FVG, clustered liquidity, Premium/Discount and PD Array context;
   - kept ICT `+OB` / `-OB` separate from MSB-OB;
   - applied chart settings `6 / 14 / 5`, one visible bullish/bearish OB and two visible FVGs.

2. Fibonacci and classical context
   - translated Smart Money Fibonacci OTE with pivot 10 and 0.618-0.786 OTE;
   - added 0.5, 0.705, 0.79, 1.272 and 1.618 decision fields;
   - translated Dual Log Regression Channels (`300 / 2.0`, `50 / 1.5`);
   - added Dow swing structure, volume-price confirmation and market-cycle phase to 4H/1H context.

3. Volume and order-flow boundary
   - translated High Volume Pivot Support/Resistance (`40 / 40 / 20 / 1.2`);
   - translated FVG Volume Profile (`13 / 20 / 0.6` chart values);
   - a native 13-minute Binance interval does not exist, so closed 15m data is used only as a labelled shadow proxy when available; the official 1H path uses a labelled parent-candle fallback;
   - candle-direction CVD, stop-run, acceptance and absorption are labelled proxies with `is_true_orderflow=false`.

4. Auxiliary filters
   - restored RAR `15 / 1`;
   - restored the supplied Inertial Stochastic search/smoothing algorithm `10 / 40 / 3 / 3`;
   - restored TAI with the user's `30 / 350` percentile settings;
   - all three remain timing/confidence evidence, never standalone triggers.

5. Decision safety
   - formal trials require fresh sweep/structure/volume evidence or a qualified OB + auxiliary reversal;
   - zone touch alone cannot produce a formal trial;
   - wrong edge, stale/chased entries, excessive invalidation distance and opposing structure are hard blocks;
   - same-box duplicate trials use a 12-bar cooldown unless genuinely new information appears;
   - secondary confirmation requires progress outside the parent zone and complete current-context revalidation;
   - no EMA fallback remains in official 4H bias.

6. Isolation and diagnostics
   - scanner fetches only 4H and 1H;
   - 15m scripts remain shadow/log/backtest only and contain no Telegram send path;
   - replay diagnostics now include ICT source/event age, Premium/Discount, Fibonacci, classical cycle, volume source and directional-catalyst fields.

### Review result

The Binance Vision replay includes 96 hourly closes from 2026-06-09 00:59 through 2026-06-12 23:59 Asia/Singapore. It emits 12 public alerts: 7 formal trials, 2 structure shifts and 3 passive observations. The issue-summary examples of late shorts, wrong low-area shorts, late longs, same-box flips and mechanical secondary confirmation do not recur at their reported timestamps.

This is a decision replay, not a PnL backtest. The bot still has no native footprint/order-book data, and no real 15m historical performance claim is made by this review.


## v1.3.9-layered-trial-decision

Status: 1H formal-trial decision-layer rebuild.
Deployment safety: 15m remains shadow-only and Telegram 15m is not enabled.

### Reason for this version

v1.3.8 reduced repeated range messages but retained the wrong core model: a selected key-zone interaction became a formal trial unless separate gates downgraded it. Live incidents on 6/9-6/12 showed late shorts after selloffs, shorts into lower support/+OB context, late longs after the useful repair window, mechanical second confirmations, and repeated direction changes inside unresolved boxes.

### Main changes

1. Separate ICT order-block context
   - `ICT Concepts [LuxAlgo]` `+OB` / `-OB` no longer share the MSB-OB object.
   - Exact adapter fields and Binance candle proxies carry different source labels.
   - `+OB` and `-OB` coexistence creates unresolved box context until a side is accepted.

2. Layered formal-trial decision
   - market phase;
   - structure and location state;
   - weighted SMC/ICT, Volume Profile, RAR, Inertial and TAI evidence;
   - chase, invalidation distance, box location and reward/risk checks.

3. Range behavior corrected
   - breakout is not the only formal-trial switch;
   - full indicator confluence is not mandatory;
   - a weighted early edge trial can pass inside a box;
   - an opposite formal trial inside the same practical box needs fresh structure information.

4. Secondary confirmation rebuilt
   - parent trial must have been delivered successfully;
   - price must make a real post-trial push;
   - current direction, location, chase distance and risk are revalidated;
   - stale parent trials are cleared instead of being mechanically confirmed.

5. Diagnostics and replay
   - added `scripts/replay_1h_decisions.py`;
   - added `reports/v1.3.9_replay_2026-06-09_12.csv`;
   - added `docs/V1_3_9_REPLAY_REVIEW.md`.

### Review result

In the 2026-06-09 through 2026-06-12 Binance Vision replay, formal trial/secondary alerts fell from 8 to 4. The listed late/wrong examples were blocked while earlier long candidates remained available. Native LuxAlgo objects were not present in Binance data, so that replay uses the explicitly labelled price proxy; exact-field behavior is covered by tests.


## v1.3.8-range-lock-noise-control

Status: 1H range/noise-control update.  
Deployment safety: 15m remains shadow-only and Telegram 15m is not enabled.

### Reason for this version

After v1.3.7, weak-market false long trials were reduced, but live review showed a new problem: in sideways / accumulation boxes the bot kept emitting repeated `📍 BTC 1H 上方/下方关键区观察` and occasional formal试多/试空 alerts. In that environment, upper/lower touches are usually the same box being tested, not fresh direction information.

### Main changes

1. Added range / accumulation lock
   - detects when price is rotating inside a compact 1H value box
   - uses recent high/low compression, edge touches, lack of directional expansion, and VP/HVN/POC acceptance context
   - this is a noise gate only, not a standalone signal

2. Reduced repeated key-zone observations
   - same range box shares a cooldown across upper and lower observations
   - passive observations inside the same box are suppressed
   - synthetic range-edge observations are ignored while range-lock is active

3. Protected formal trial alerts inside ranges
   - `LOWER_KEY_ZONE_RECLAIM` / `UPPER_KEY_ZONE_REJECTION` are downgraded inside range-lock
   - only a strong high-impulse sweep-reclaim/reject exception can escape the lock

4. Isolation remains unchanged
   - 15m continues server-side shadow testing only
   - no 15m Telegram pilot is enabled
   - 15m does not decide direction or modify 1H logic

### Review target

The main live-review target is whether pure sideways / accumulation conditions stop producing hourly key-zone noise, while true sweep-reclaim/reject reactions can still surface.

## v1.3.7-smc-vp-1h-filter

Status: 1H signal-quality update.  
Deployment safety: 15m remains shadow-only and Telegram 15m is not enabled.

### Reason for this version

The user observed repeated wrong or premature `📈 BTC 1H 试多观察 📈` alerts during weak BTC price action. The live chart showed price under supply / BE-OB context, failing to reclaim value, and moving through thin low-volume areas. In that environment, a lower-zone touch or short-term RAR/Inertial repair should not become a formal long trial.

The update follows the user's indicator priority:
MSB-OB / SMC / ICT structure first, Volume Profile value acceptance second, RAR / Inertial / TAI as filters only.

### Main changes

1. Added internal Volume Profile filter
   - approximate 1H POC / HVN / LVN / VAH / VAL from exchange candles
   - detects value-area position, VAL reclaim, VAH rejection, LVN / thin-air pressure
   - used only as a filter, never as a standalone trigger

2. Tightened formal 1H trial upgrades
   - weak lower-area reclaim can stay `📍 BTC 1H 下方关键区观察` instead of becoming `📈 BTC 1H 试多观察 📈`
   - weak upper-area rejection can stay `📍 BTC 1H 上方关键区观察` instead of becoming `📉 BTC 1H 试空观察 📉`

3. Secondary confirmation is now formal-only
   - single-emoji observations do not open a pending secondary-confirmation state
   - secondary confirmation can be blocked if value acceptance does not support the side

4. Isolation remains unchanged
   - 15m continues server-side shadow testing only
   - no 15m Telegram pilot is enabled
   - 15m does not decide direction or modify 1H logic

### Review target

The main live-review target is whether 1H stops calling formal long trials while price is below value / under supply / inside LVN continuation with no real acceptance.



## v1.3.4-copy-layer-fix

Status: copy-only update.  
Deployment safety: does not change 15m shadow logic or official 1H signal scoring.

### Reason for this version

v1.3.4 fixes Telegram copy layering after the user clarified that `试多观察` and `试空观察` are formal 1H trade alerts, not casual observations.

Final copy layering:

- double emoji = formal 1H trade alert;
- single emoji = non-formal observation / future 15m location reminder;
- secondary confirmation remains formal but must be extremely short;
- standalone bull/bear invalidation Telegram alerts are removed from the public copy family.

### Main changes

1. Formal 1H titles
   - `📈 BTC 1H 试多观察 📈`
   - `📉 BTC 1H 试空观察 📉`
   - `📈 BTC 1H 多头确认 📈`
   - `📉 BTC 1H 空头确认 📉`

2. Secondary confirmation copy
   - `✅ BTC 1H 二次确认：承接成立 ✅`
   - `✅ BTC 1H 二次确认：承压成立 ✅`
   - body keeps only the risk-level note

3. Single-emoji 1H observations
   - only status, zone, and risk point
   - no 4H background
   - no momentum/temperature section
   - no conclusion section

4. Removed standalone public invalidation alerts
   - no `⚠️ BTC 1H 多头失效`
   - no `⚠️ BTC 1H 空头失效`
   - internal invalidation state can still update silently

5. 15m remains shadow-only
   - future 15m copy template is compact and single-emoji
   - no Telegram 15m send is enabled by this version


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
