# AlertBot

AlertBot is a Telegram-based BTCUSDT market monitoring and alert delivery system.

The current main path is built around a BTC 1H trend-segment decision engine. It is designed to identify meaningful market structure changes and trend-continuation areas while reducing noisy indicator-driven alerts.

## Core design

AlertBot no longer uses the old ABCX signal framework as its primary alert path.

The current engine follows this timeframe model:

- 4H: higher-timeframe background context, including range / bullish / bearish regime
- 1H: primary structure and alert-decision timeframe
- 15m: not used by the main trend engine

The 4H context is used as background only. It can raise or lower confidence, but it should not hard-block a high-quality 1H structure change.

## Alert philosophy

The bot is intended to send fewer, higher-quality alerts around important structural and observation moments, including:

- signal-style long/short trial observations
- long/short confirmations after an initial reaction
- long/short invalidation alerts
- neutral key-area observations
- wick/probe observations
- range-boundary observations
- no-trade range debug decisions

Telegram messages are intentionally written in simple external-facing language. Internal strategy terminology is not exposed in alert messages.

The alert title is now a compact signal label. Position and context details are kept in the body:
the status section explains what happened, and the focus range includes a one-line note below the price range.


## Indicator stack

The active trend engine does not use MACD_SSS_EQ as a decision input.

The current auxiliary layer uses:

- RAR direction and slope
- Inertial Stochastic direction and slope
- Trading Activity Index heat based on the Zeiierman dollar-volume formula
- recent 1H price displacement
- volume expansion

TAI heat is classified by its P20/P40/P60/P80 bands, not by fixed 0-100 thresholds.

## Main pipeline

The main scanner path is implemented in `engine/scanner.py`.

Pipeline overview:

1. Fetch closed 4H and 1H candles.
2. Build higher-timeframe context from 4H data.
3. Build 1H key-area and structure context.
4. Build auxiliary momentum and market-temperature filters.
5. Produce a `TrendDecision`.
6. If there is no structure alert, evaluate the key-zone observation layer for pullbacks, rebounds, support/resistance tests, range-edge probes, and pending secondary confirmations.
7. Format an external-safe Telegram message.
8. Apply cooldown and deduplication.
9. Store trend and observation state for future continuation or confirmation alerts.

## Key modules

- `engine/scanner.py`  
  Main orchestration pipeline for the trend engine.

- `engine/liquidity.py`  
  Builds key-area context and recent trigger context.

- `engine/msb_ob.py`  
  Builds structure-shift context, structure quality, and relevant price zones.

- `engine/trend_matrix.py`  
  Provides a lightweight background-structure proxy.

- `engine/aux_filters.py`  
  Builds auxiliary momentum, heat, and participation filters.

- `engine/trend_segments.py`  
  Produces the final trend decision, score, alert type, suppression reason, and debug fields.

- `engine/trend_snapshot.py`  
  Stores and loads trend state for continuation alerts.

- `engine/trend_messages.py`  
  Formats Telegram messages and protects against leaking internal terminology.

- `engine/trend_config.py`  
  Centralizes trend-engine thresholds and tuning parameters.

- `engine/cooldown.py`  
  Handles cooldown and deduplication for trend alerts.

## Decision behavior

Important rules:

- The scanner requests only 4H and 1H candles for the main trend engine.
- 15m candles are not requested or used by the main trend engine.
- Short and noisy structure moves are suppressed by default.
- Trend continuation requires existing saved trend state.
- Higher-timeframe conflict lowers confidence, but it does not automatically reject strong 1H structure.
- Medium-quality 1H setups can be suppressed when they are directly against a strong 4H background.
- Initial key-zone observations can open an internal pending-confirmation switch; middle candles stay silent until confirmation, invalidation, or a meaningful reaction.
- Final Telegram messages are checked against a banned-terms list before sending.

## Telegram message structure

The default Telegram message format is intentionally concise:

- title
- status
- key price zone
- higher-timeframe context
- momentum and market heat
- invalidation level
- conclusion

Examples of external-facing alert titles:

- BTC 1H bullish structure shift
- BTC 1H bearish structure shift
- BTC 1H bullish continuation watch
- BTC 1H bearish continuation watch

## Testing

Run the full test suite:

```bash
python -m unittest discover -s tests
python -m compileall -q engine services tests
```

Expected result:

```text
Ran 31 tests OK
compileall OK
```

## Deployment notes

Before running the bot in production:

1. Confirm environment variables are configured.
2. Confirm Telegram credentials are valid.
3. Run the full test suite.
4. Start with dry-run or observation mode.
5. Review live alerts before using them in any trading workflow.

## Current limitations

Some auxiliary filters are proxy implementations and should be tuned with live replay data.

Closed-source TradingView indicators are not fully replicated. The bot uses transparent Python approximations where exact indicator logic is unavailable.

AlertBot is a market monitoring and decision-support tool. It does not provide financial advice and should not be treated as an automated trading system.


## Key-zone observation layer

Version 1.1 adds a dedicated observation layer for cases that are useful to monitor but should not be mislabeled as structure shifts.

This layer can alert when BTC quickly tests a lower or upper key area, including:

- fast pullbacks into a lower key area
- fast rebounds into an upper key area
- lower/upper range-edge probes
- tests of intermediate trend areas

The observation layer uses re-entry based cooldown:

- first touch of a key area can alert
- repeated candles inside the same area are suppressed
- once price leaves the area and later re-enters, the alert can re-arm
- if the situation upgrades into a structure shift or continuation alert, the main trend engine takes priority

Public Telegram text still avoids internal strategy terms.
