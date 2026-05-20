# AlertBot Version Context

## Current version

v1.3.6-historical-active-setup-bridge



## v1.3.6 reason

v1.3.5 deployed correctly, but the 15m shadow backtest still showed `active_1h_setup=False` for every row.  That meant the active 1H setup bridge existed as an API field, but historical backtest reconstruction did not actually populate it.

The user confirmed the intended workflow: after a valid 1H `试多观察` / `试空观察`, 1H should not repeat the same setup.  Instead, 15m shadow should test whether a later retest offers an entry-location reminder.

## v1.3.6 changes

- 1H formal trial setup state is now explicitly written into observation state:
  - `active_setup_side`
  - `active_setup_zone_low`
  - `active_setup_zone_high`
  - `active_setup_invalid_level`
  - `active_setup_open_time`
  - `active_setup_phase`
- Historical 15m backtest can now reconstruct active 1H setup context.
- Active 1H setup zones are inserted as high-priority 15m shadow POI.
- Active setup 15m retests are slightly relaxed versus standalone 15m signals:
  - still need POI reaction;
  - do not require every momentum proxy to have fully turned yet.
- Added tests for active setup state writing and active setup 15m bridge usage.

## v1.3.6 safety

- 15m remains shadow-only.
- No Telegram 15m sending is enabled.
- 1H official alert copy from v1.3.4 is unchanged.
- This version fixes state/backtest bridging, not execution or order routing.


## v1.3.5 reason

This version fixes the 1H state-machine problem observed after v1.3.4:

- same-zone `试多观察` repeated several hours apart;
- the same setup later downgraded into `下方关键区观察`;
- `二次确认：承接成立` fired too close to the original risk level;
- 15m shadow did not see the "1H setup is active, now look for entry location" context.

TradingDexCat clarified that after a 1H formal setup fires, 1H should not keep repeating the same official alert.  The trader would switch to 15m to find an entry location.  Therefore 15m shadow needs a bridge from the active 1H setup, but 15m still must not send Telegram or affect 1H logic.

## v1.3.5 changes

- Added active setup state tracking for 1H key-zone observations.
- Suppressed repeated same-zone/same-direction 1H `试多观察` / `试空观察` alerts while the active setup is still live.
- Suppressed same-zone single-emoji observation downgrade after a formal 1H setup is active.
- Tightened secondary confirmation:
  - `承接成立` now requires a clean reclaim above the zone, not just a mid-zone bounce.
  - `承压成立` now requires a clean rejection below the zone, not just inside-zone weakness.
- Added a 15m shadow bridge:
  - backtest can expose active 1H setup context to the 15m early-entry evaluator;
  - the bridge is shadow-only and does not change Telegram behavior.
- Added test coverage for strict secondary confirmation.

## v1.3.5 safety

- 15m remains shadow-only.
- 1H formal alert scoring is not replaced.
- Telegram copy rules from v1.3.4 stay unchanged.
- This version changes state flow and shadow diagnostics, not order execution.


## v1.3.4 reason

This version fixes Telegram copy layering only. It is based on v1.3.2 and does not include the discarded v1.3.3 observe-guard change.

TradingDexCat clarified the final copy-family rule:
- double emoji = formal 1H trade alert;
- single emoji = non-formal observation or future 15m entry-location reminder;
- secondary confirmation stays double emoji but must be very short;
- standalone bull/bear invalidation Telegram alerts should be removed because they disturb decision flow.

## v1.3.4 changes

- Kept `📈 BTC 1H 试多观察 📈` and `📉 BTC 1H 试空观察 📉` as formal double-emoji alerts.
- Changed formal confirmation titles to:
  - `📈 BTC 1H 多头确认 📈`
  - `📉 BTC 1H 空头确认 📉`
- Changed secondary confirmations to minimal copy:
  - `✅ BTC 1H 二次确认：承接成立 ✅`
  - `✅ BTC 1H 二次确认：承压成立 ✅`
  - body contains only the risk-level note.
- Changed 1H single-emoji observations to compact three-section copy:
  - status
  - zone
  - risk point
- Removed standalone public copy for:
  - `⚠️ BTC 1H 多头失效`
  - `⚠️ BTC 1H 空头失效`
- Internal invalidation tracking can still update state, but it no longer sends a standalone Telegram alert.
- 15m remains shadow-only; its future copy template is compact single-emoji format.

## Safety

This version does not change the 15m shadow engine or official 1H signal scoring. It only changes Telegram copy formatting and suppresses standalone invalidation messages.

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
