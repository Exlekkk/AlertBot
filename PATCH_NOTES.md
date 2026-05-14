# Patch Notes — Trend Segment Engine v1

## v1.1.7 - Zone Note Wording

### Summary

This release adds a short semantic note directly under the focus price range so the alert explains what the range is meant to represent.

### Key changes

- Focus ranges now include a one-line note below the price range.
- The note avoids the label `用途：` and stays compact.
- Examples:
  - lower reaction area: `下方承接观察区，回踩不破才有确认价值。`
  - upper rejection area: `上方承压观察区，反抽不破才有确认价值。`
  - fast pullback: `急跌后的下方反应区，先看是否收回区间上沿。`
  - fast rebound: `急拉后的上方反应区，先看是否跌回区间下沿。`
- No trigger logic changes in this release.

### Validation

- `python -m unittest discover -s tests`
- `python -m compileall -q engine services scripts tests`

Current test suite: 49 tests.



## v1.1.6 - Pending Confirmation Switch / Dynamic Conclusions

### Summary

This release adds a follow-up confirmation switch for key-zone observations.

### Key changes

- Initial key-zone observation opens an internal pending-confirmation state.
- Middle candles stay silent while the pending state is active.
- A second Telegram alert is sent only when the setup confirms, invalidates, or forms a meaningful reaction.
- Added secondary confirmation alerts:
  - lower support/acceptance confirmation
  - upper resistance/rejection confirmation
- Observation conclusions are less rigid:
  - confirmed lower reactions can show small-position trial conditions
  - confirmed upper reactions can show small-position short-trial conditions
- Title emoji changes are limited to:
  - `📈 BTC 1H 下方关键区收回 📈`
  - `📉 BTC 1H 上方关键区承压 📉`
- Other titles keep a single leading emoji.

### Validation

- `python -m unittest discover -s tests`
- `python -m compileall -q engine services scripts tests`

Current test suite: 47 tests.


## v1.1.5 - No MACD / True TAI Calibration / Structure-First Observation

### Summary

This release removes MACD_SSS_EQ from the active trend engine and recalibrates market heat using the Trading Activity Index formula.

### Key changes

- Removed MACD from the active scanner, auxiliary filters, scoring, and tests.
- Rebuilt TAI heat classification from the Zeiierman formula:
  - dollar volume = close * volume
  - average dollar volume = SMA(dollar volume, 20)
  - trading activity = log(average dollar volume)
  - P20/P40/P60/P80 are rolling percentile bands over the history window.
- Heat labels now follow the visible bands:
  - below P20 = over-cold
  - P20-P40 = slightly cold
  - P40-P60 = neutral
  - P60-P80 = slightly hot
  - above P80 = over-hot
- Momentum now uses:
  - RAR slope
  - Inertial slope
  - recent 1H price impulse
  - volume expansion
- Key-zone observation is stricter:
  - range edges no longer trigger by themselves after a sweep
  - observation alerts require FVG / structure / valid POI context
  - passive post-impulse noise is suppressed until a real new reaction appears

### Validation

- `python -m unittest discover -s tests`
- `python -m compileall -q engine services scripts tests`

Current test suite: 41 tests.


## Summary

This release replaces the old ABCX-style alert path with a BTC 1H trend segment decision engine.

The new main path is designed to detect structure shifts, trend continuation areas, and invalidation levels using a 4H/1H framework:

- 4H provides background context only.
- 1H is the primary structure decision timeframe.
- 15m is no longer used by the scanner.
- Public Telegram messages use neutral wording and do not expose internal strategy terms.
- Trend alerts use signature-based cooldown and deduplication.

## Core behavior

### Timeframe model

The scanner now uses:

- `4h` for higher-timeframe context
- `1h` for primary structure decisions

The 4H context can increase or decrease the decision score, but it does not hard-block high-quality 1H structure changes.

A 1H setup can be suppressed only when:

- the 1H structure quality is weak or medium, and
- the 4H background is strongly opposite.

### Trend decision model

The new trend decision engine evaluates:

- recent key-area trigger behavior
- structure shift quality
- key price zones
- continuation state
- higher-timeframe context
- auxiliary market filters
- cooldown and alert state

The engine distinguishes between:

- `BULLISH_STRUCTURE_SHIFT`
- `BEARISH_STRUCTURE_SHIFT`
- `BULLISH_CONTINUATION`
- `BEARISH_CONTINUATION`
- `RANGE_COMPRESSION`
- `STRUCTURE_FAILURE`
- `NO_TRADE_RANGE`

## Key changes

### Scanner

Updated:

- `engine/scanner.py`

Main changes:

- Removed 15m from the main scanner path.
- Scanner now requests only 4H and 1H klines.
- Scanner builds higher-timeframe context before the 1H decision.
- Scanner passes trend state into the decision engine so continuation alerts can work in live runs.
- Scanner uses the new trend message formatter for public Telegram output.

### Trend engine modules

Added or updated:

- `engine/liquidity.py`
- `engine/msb_ob.py`
- `engine/trend_matrix.py`
- `engine/aux_filters.py`
- `engine/trend_segments.py`
- `engine/trend_snapshot.py`
- `engine/trend_config.py`
- `engine/trend_messages.py`

### Config

Added:

- `engine/trend_config.py`

This centralizes trend-engine thresholds and avoids scattering magic numbers across the scanner and decision modules.

Configurable areas include:

- key-area lookback
- recent trigger window
- reclaim / reject buffer
- structure leg quality thresholds
- zone width
- continuation zone behavior
- higher-timeframe scoring
- suppression thresholds

### Trend state and snapshots

Added:

- `engine/trend_snapshot.py`

Trend snapshots are used to:

- keep track of the current trend state
- allow valid continuation alerts only after an existing trend state
- avoid repeated alerts from the same structure
- preserve debug information for replay and review

### Cooldown

Updated:

- `engine/cooldown.py`

Trend alerts now use signature-based cooldown keys instead of the old slot/family model.

Trend alert keys are based on:

- symbol
- timeframe
- alert type
- direction
- zone hash
- state version

The old slot/family model is not used for the new trend alert path.

### Telegram messages

Updated:

- `engine/trend_messages.py`

Public Telegram messages now use external-safe wording:

- 结构转多
- 结构转空
- 多头延续观察
- 空头延续观察
- 关注区间
- 大周期
- 动能与热度
- 风险位
- 结论

Message titles now include direction emojis:

- `📈 BTC 1H 结构转多提醒`
- `📉 BTC 1H 结构转空提醒`

The formatter checks outgoing messages to avoid leaking internal terminology.

## Validation

The test suite was expanded to cover the new trend engine path.

Covered cases include:

- scanner requests only 4H and 1H data
- 15m is not used in the new scanner path
- 4H context does not hard-block high-quality 1H structure changes
- weak 1H structure can be suppressed against strong opposite 4H context
- short/noisy structure legs do not trigger structure-shift alerts
- mid-quality structure legs with a recent valid key-area trigger can create structure-shift alerts
- continuation requires existing trend state
- invalidation level prefers the actual recent trigger level for structure-shift alerts
- Telegram messages start with the expected emoji
- Telegram messages do not expose banned internal terminology
- cooldown does not write old slot/family keys for trend alerts

Run:

```bash
python -m unittest discover -s tests
python -m compileall -q engine services tests
```

Current result:

```text
Ran 31 tests OK
compileall OK
```

## Known limitations

Some TradingView-related components are still proxy implementations.

Proxy areas include:

- auxiliary market filters
- trend matrix context
- some closed-source indicator behavior

These should be tuned through:

- dry-run observation
- replay logs
- real alert snapshots
- manual comparison with TradingView charts

## Deployment notes

After replacing files on the remote server:

```bash
git pull
python -m unittest discover -s tests
python -m compileall -q engine services tests
```

Recommended rollout:

1. Run in observation mode first.
2. Confirm Telegram messages are not too frequent.
3. Compare triggered zones with the chart.
4. Tune thresholds in `engine/trend_config.py`.
5. Only then treat alerts as production-grade monitoring output.

## Rollback note

If the trend engine behaves unexpectedly, roll back to the previous stable commit and preserve the latest snapshot/debug files for review.


## v1.1 — Key-Zone Observation Layer

### Summary

This update adds a second alert layer for key-zone observation. It is designed for monitoring opportunities that may matter for short swings but do not yet qualify as full structure shifts.

### New behavior

Added:

- lower key-zone test alerts
- upper key-zone test alerts
- fast pullback observation alerts
- fast rebound observation alerts
- range lower/upper probe alerts
- re-entry based observation cooldown
- scanner health-check compatibility methods

The trend engine still has priority. If a full structure shift or continuation alert is available, the bot uses that alert first. If no structure alert is available, the observation layer can send a lower-priority monitoring alert.

### Cooldown behavior

The observation cooldown is not a hard lock.

It suppresses repeated messages while price remains inside the same key zone. It re-arms when price leaves the zone and later re-enters, or when the observation phase changes.

### Public messages

New observation messages use external-facing wording such as:

- lower key-zone test
- upper key-zone test
- fast pullback observation
- fast rebound observation
- range-edge test

Internal strategy terms remain blocked from Telegram messages.

### Validation

- `python -m unittest discover -s tests`
- `python -m compileall -q engine services scripts tests`

Current test suite: 35 tests.
