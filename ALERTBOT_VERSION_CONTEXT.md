# AlertBot Version Context

## Current version

v1.4.0-btc-smc-ict-chart-alignment


## v1.4.0 scope

- BTCUSDT only. US-stock work is explicitly out of scope.
- Trading hierarchy is fixed at 4H direction -> 1H structure/official Telegram -> 15m entry-location shadow.
- The supplied Pine files and the user's ICT screenshots are the implementation source for this release.
- 15m remains shadow-only: no Telegram, no order path and no influence on the 1H decision.

## v1.4.0 changes

- Replaced the official EMA/MACD/ABCX/generic fixed-range VP decision path with the requested BTC framework:
  - SMC/ICT liquidity sweep, MSS/CHoCH, BOS, FVG, OB, Breaker, mitigation, Premium/Discount and PD Array;
  - 4H bias and 1H structure;
  - Smart Money Fibonacci OTE, 0.5 equilibrium, 0.618/0.705/0.786/0.79 and 1.272/1.618 extensions;
  - Dual Log Regression Channels, Dow structure, volume-price confirmation and market-cycle context.
- Transcribed the user's chart settings, including ICT `6 / 14 / 5`, MSB-OB `9 / 0.33`, high-volume pivots `40 / 40 / 20 / 1.2`, FVG VP `13 / 20 / 0.6`, RAR `15 / 1`, Inertial `10 / 40 / 3 / 3` and TAI `30 / 350`.
- Added deterministic closed-candle translations for ICT Concepts, MSB-OB, Smart Money Fibonacci OTE, Dual Log Regression Channels, High Volume Pivot zones and FVG Volume Profile.
- Restored RAR, Inertial Stochastic and TAI as auxiliary timing/confidence evidence. They cannot trigger a formal alert alone.
- Order-flow wording is explicitly `candle_direction_volume_proxy`; no candle-volume calculation is represented as footprint, order-book or true trade-delta flow.
- Formal trials now require fresh directional information, valid box location, acceptable risk/chase distance and sufficient directional advantage. Same-box duplicate trials and rapid opposite flips are blocked without new information.
- Secondary confirmation requires a real post-trial push and full context revalidation. It can still pass without demanding a second MSS on the same candle.
- The scanner no longer falls back to EMA direction when 4H history is short; it stays neutral until SMC/ICT history is sufficient.

## v1.4.0 validation

- 84 unit tests pass; compile and diff-whitespace checks pass.
- Binance Vision decision replay covers all 96 hourly closes from 2026-06-09 00:59 through 2026-06-12 23:59 (Asia/Singapore).
- Replay output: 12 public alerts = 7 formal trials + 2 structure shifts + 3 passive observations; no mechanical secondary confirmation was emitted.
- The reported late/wrong examples at 6/9 23:00, 6/10 07:00/11:00, 6/11 07:00/10:00 and 6/12 10:00/11:00/15:00 are absent or explicitly suppressed.
- This is a deterministic decision replay, not a profitability backtest. It has no native footprint/order-book feed, and the 15m shadow layer still needs a separate real-15m archive review before any future Telegram pilot.

See `docs/V1_4_0_REPLAY_REVIEW.md` and `reports/v1.4.0_btc_framework_replay_2026-06-09_12.csv`.


## v1.3.9

v1.3.9-layered-trial-decision


## v1.3.9 reason

Live review of v1.3.8 showed that the 1H trial layer was still a key-zone trigger with extra blockers. It could flip long/short inside the same box, report after the useful entry window, issue the wrong side near active support, and mechanically confirm a stale parent trial. The v1.3.8 range lock also became a hard downgrade that incorrectly required an exceptional sweep before any range-edge trial could pass.

## v1.3.9 changes

- Added `engine/ict_ob.py` so ICT Concepts `+OB` / `-OB` are separate from MSB-OB.
  - exact external fields are supported;
  - Binance-only fallback is labelled `price_proxy` and is never called an exact LuxAlgo match;
  - active `+OB` and `-OB` coexistence creates unresolved box context.
- Added `engine/trial_decision.py` with four layers:
  - market phase;
  - structure/location state;
  - weighted evidence (not a fixed confluence checklist);
  - chase, risk, box location, and reward/risk validation.
- Range state no longer blanket-downgrades every formal trial. A weighted early trial may pass at an edge before breakout.
- Opposite formal trials inside the same practical box require fresh structure information, not a touch or score flip alone.
- Secondary confirmation now requires a valid push beyond the parent alert, re-scores current context, and rejects stale/chased/wrong-side confirmation.
- Observation pending state is persisted only after Telegram confirms delivery. A failed or deduped parent alert cannot create a phantom second confirmation.
- Added exact Inertial adapter fields and a labelled Stochastic fallback because the original Pine source is not stored in this repository.
- Telegram formatting removes repeated major sections before send.
- Added deterministic 1H replay tooling and a 6/9-6/12 review artifact.
- 15m remains server-side shadow only and never changes 1H logic or Telegram output.

## v1.3.9 validation

- 70 unit tests pass.
- compileall and app import pass.
- Binance Vision replay for 2026-06-09 through 2026-06-12:
  - v1.3.8 formal trial/secondary alerts: 8;
  - v1.3.9 formal trial/secondary alerts: 4;
  - targeted late/wrong alerts from the issue summary are blocked;
  - useful long candidates are not silenced and appear earlier in the replay.

See `docs/V1_3_9_REPLAY_REVIEW.md` for limits and incident-level results.


## v1.3.8

v1.3.8-range-lock-noise-control


## v1.3.8 reason

After v1.3.7, the weak-market false-long issue improved, but the bot produced too many single-emoji key-zone observations and some formal试多/试空 alerts while BTC was rotating in a pure sideways / accumulation box. The user clarified that in this environment, repeated upper/lower touches are not fresh information; the bot should prioritize silence or one recent observation until the range breaks or a true sweep-reclaim/reject appears.

## v1.3.8 changes

- Added `engine/range_lock.py`.
- Scanner now builds an internal 1H range/accumulation-lock context after SMC/ICT + Volume Profile context.
- Key-zone observations now respect range-lock:
  - same value box has a shared cooldown across upper/lower observations;
  - repeated passive observations inside the same box are suppressed;
  - synthetic range-edge observations are ignored while range-lock is active;
  - formal trial upgrades inside range-lock are downgraded unless there is a strong sweep-reclaim/reject exception.
- Added tests for range-lock cooldown and downgrade behavior.
- 15m remains server-side shadow only; no Telegram 15m pilot is enabled.

## v1.3.8 safety

- Does not enable 15m Telegram.
- Does not change 15m shadow isolation.
- Keeps v1.3.7 SMC/ICT + Volume Profile filter.
- Adds a noise-control layer for sideways/accumulation environments only.


## v1.3.7 reason

This version is based on v1.3.4-copy-layer-fix after the user rolled back the experimental v1.3.5/v1.3.6 active-setup changes.

TradingDexCat identified a high-priority 1H issue: during weak or bearish BTC conditions, especially below BE-OB / supply and inside LVN / Volume Gap paths, the bot kept upgrading lower-area reactions into formal `📈 BTC 1H 试多观察 📈` alerts. That violated the user's indicator order: MSB-OB/SMC/ICT structure first, Volume Profile value acceptance second, and RAR/Inertial/TAI only as filters.

## v1.3.7 changes

- Added `engine/volume_profile.py`, an internal 1H Volume Profile proxy from exchange candles:
  - POC / HVN / LVN / VAH / VAL approximation
  - value-area position
  - VAL reclaim / VAH rejection
  - LVN / thin-air pressure
- 1H formal trial alerts now pass an SMC/ICT + Volume Profile filter before being sent.
- `LOWER_KEY_ZONE_RECLAIM` can be downgraded to `LOWER_KEY_ZONE_TEST` when value acceptance does not support a formal long trial.
- `UPPER_KEY_ZONE_REJECTION` can be downgraded to `UPPER_KEY_ZONE_TEST` when value acceptance does not support a formal short trial.
- Passive single-emoji observations no longer create the pending state for `✅ BTC 1H 二次确认`.
- Secondary confirmations are blocked when the Volume Profile filter says the original side has not been accepted.
- 15m remains server-side shadow only; no 15m Telegram pilot is enabled.

## v1.3.7 safety

- Does not enable 15m Telegram.
- Does not change 15m shadow isolation.
- Does not expose internal indicator names in Telegram copy.
- Keeps v1.3.4 copy layering.

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
