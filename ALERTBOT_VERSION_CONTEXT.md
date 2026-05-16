# AlertBot Version Context

## Current version

v1.3.2-adaptive-shadow-cadence

## v1.3.2 reason

v1.3.1 tightened the 15m shadow engine after v1.3.0 became too noisy.  The next design correction is about cadence: 1-4 reminders per day is useful as a normal-market reference, but it must not become a hard daily cap.

TradingDexCat wants 15m only as an entry-location reminder.  On active/high-volatility days, the bot should be able to show more valid locations if each reminder has fresh structure information.  The correct filter is duplicate/contradiction control, not a fixed daily maximum.

## v1.3.2 changes

- Added adaptive cadence metadata:
  - `zone_cluster_hash`
  - `cadence_mode`
  - `recommended_cooldown_bars`
- Added reusable cadence helpers in `engine/prealert_15m.py`:
  - `decision_cadence_keys`
  - `cooldown_bars_for_decision`
  - `is_high_quality_new_information`
- Same-direction reminders in the same 1H area still use cooldown.
- Strong new-information setups can use a shorter cooldown.
- Rapid long/short flip-flops in the same 1H area are suppressed unless the new signal has strong sweep/reclaim/reject information.
- Backtest summary now reports:
  - `duplicate_skips`
  - `contradiction_skips`
- GitHub README clarifies that 1-4 signals/day is a baseline reference, not a hard cap.

## v1.3.1 reason

v1.3.0 successfully made both long and short 15m shadow entries appear, but the backtest became too noisy:
- 61 total 15m shadow signals in 7 days
- about 7.62 signals per active day
- long win rate around 20.7%
- short win rate around 43.8%

This is not acceptable for a future Telegram prealert layer. v1.3.1 tightens the 15m shadow engine while preserving the core separation rule: 15m never changes 1H logic.

## v1.3.1 changes

- Reduced broad-zone noise:
  - lower max zone width
  - higher minimum trigger score
  - lower maximum risk percentage
  - longer same-zone cooldown
- Added hard 1H liquidity-context alignment:
  - no long prealert inside a clear 1H sweep-high-failed context
  - no short prealert inside a clear 1H sweep-low-reclaim context
- Tightened 15m reaction requirements:
  - standalone local sweep is not enough
  - standalone zone reaction is not enough
  - non-sweep setups need key-level reaction, aligned momentum, and candle confirmation
- TAI remains a filter, not a trigger:
  - overheated long without sweep reclaim is rejected
  - cold short without sweep rejection is rejected
- Replaced GitHub README with a concise English handoff README.

## Core rule

1H is the official alert body and the main trading-structure logic.  
15m is only an early entry-location reminder.

The 15m layer must not change:
- 1H alert title
- 1H alert conclusion
- 1H direction
- 1H cooldown logic
- 1H Telegram copy
- 1H decision scoring

The 15m layer may only produce/log:
- `📍 BTC 15m 做空预警`
- `📍 BTC 15m 做多预警`

Until explicitly enabled later, the 15m layer remains shadow-only:
- no Telegram send
- no order
- no scanner integration
- backtest/log only

## TradingDexCat framework anchor

- BTC is the only current AlertBot target.
- 4H provides background.
- 1H provides structure and POI.
- 15m only finds possible entry locations.
- Structure/liquidity lead the signal.
- RAR / Inertial / TAI are filters, not standalone triggers.
- MACDSSSEQ is removed from the decision framework.
- Do not use single FVG, single TAI, or single zone touch as a trigger.

## v1.3.0 design intent

The previous 15m shadow result was too one-sided:
- long = 0
- short = 8
- short win rate = 50%

v1.3.0 rebuilds the 15m shadow layer into an early-entry engine:
- Short prealert looks for 15m sweep-high rejection / pressure reaction near 1H resistance POI.
- Long prealert looks for 15m sweep-low reclaim / support reaction near 1H support POI.
- The engine requires 1H/4H context before any 15m alert can be considered.
- The engine adds diagnostic CSV fields so failures can be reviewed without guessing.

## Important interpretation

"Do not chase the first waterfall / first vertical rally" means:
- If 15m warned before the move from a valid 1H/4H location, the trader can review and act.
- If the move already happened without a valid early-entry setup, the bot should not chase afterwards.

## Files changed in v1.3.0

- `engine/prealert_15m.py`
  - rebuilt 15m shadow early-entry logic
  - added 1H context gate
  - added 15m local sweep detection
  - added key-level context
  - added anti-noise gates
  - added diagnostic fields

- `scripts/backtest_15m_prealert.py`
  - expanded summary
  - added diagnostic CSV columns
  - keeps shadow-only workflow

- `services/logger.py`
  - log-file permission fallback to stderr
  - prevents local/import startup failure when `/opt/smct-alert/logs` is not writable

- `docs/TRADING_FRAMEWORK.md`
  - condensed framework for handoff

- `docs/CHANGELOG_TRADINGDEXCAT.md`
  - version-specific change log

- `ALERTBOT_VERSION_CONTEXT.md`
  - single-file handoff context for future conversations
