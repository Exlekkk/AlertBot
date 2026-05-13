[README.md](https://github.com/user-attachments/files/27696748/README.md)
# AlertBot

AlertBot is a Telegram-based BTCUSDT market monitoring and alert delivery system.

The current main path is built around a BTC 1H trend-segment decision engine. It is designed to identify meaningful market structure changes and trend-continuation areas while reducing noisy indicator-driven alerts.

## Core design

AlertBot no longer uses the old ABCX signal framework as its primary alert path.

The current engine follows this timeframe model:

- 4H: higher-timeframe background context
- 1H: primary structure and alert-decision timeframe
- 15m: not used by the main trend engine

The 4H context is used as background only. It can raise or lower confidence, but it should not hard-block a high-quality 1H structure change.

## Alert philosophy

The bot is intended to send fewer, higher-quality alerts around important structural moments, including:

- bullish structure shift
- bearish structure shift
- bullish trend continuation
- bearish trend continuation
- range compression
- structure failure
- no-trade range

Telegram messages are intentionally written in simple external-facing language. Internal strategy terminology is not exposed in alert messages.

## Main pipeline

The main scanner path is implemented in `engine/scanner.py`.

Pipeline overview:

1. Fetch closed 4H and 1H candles.
2. Build higher-timeframe context from 4H data.
3. Build 1H key-area and structure context.
4. Build auxiliary momentum and market-temperature filters.
5. Produce a `TrendDecision`.
6. Format an external-safe Telegram message.
7. Apply cooldown and deduplication.
8. Store trend state for future continuation alerts.

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
