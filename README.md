[Uploading README.md…]()
# AlertBot

AlertBot is a Telegram-based BTCUSDT market monitoring and alert delivery system.

The current main path is built around a **BTC 1H trend segment decision engine**:

- **4H** = background context
- **1H** = main structure and alert decision timeframe
- **15m** = not used by the main alert engine

The bot is designed to send fewer, higher-quality alerts around meaningful structure changes instead of reacting to every indicator movement.

## Current alert types

The public Telegram wording is intentionally simple:

- `结构转多`
- `结构转空`
- `多头延续观察`
- `空头延续观察`
- `关注区间`
- `大周期`
- `动能与热度`
- `风险位`
- `结论`

Internal strategy terms are not exposed in Telegram messages.

## Main pipeline

`engine/scanner.py` now runs the trend engine path:

1. Fetch closed 4H and 1H candles.
2. Build 4H background context.
3. Build 1H key-area and structure context.
4. Build auxiliary momentum / market-temperature filters.
5. Produce a `TrendDecision`.
6. Format an external-safe Telegram message.
7. Apply cooldown / deduplication before sending.
8. Store trend state for future continuation alerts.

## Important behavior

- 4H is context only. It can add or subtract confidence, but it does not hard-block high-quality 1H structure changes.
- 15m is not requested or used by the main trend engine.
- Trend continuation requires existing saved trend state.
- Short/noisy structure moves are suppressed by default.
- Alert messages are checked for banned internal terminology before sending.

## Tests

Run:

```bash
python -m unittest discover -s tests
python -m compileall -q engine services tests
```

Expected result:

```text
Ran 31 tests OK
compileall OK
```

## Files of interest

- `engine/scanner.py`
- `engine/liquidity.py`
- `engine/msb_ob.py`
- `engine/trend_segments.py`
- `engine/trend_messages.py`
- `engine/trend_snapshot.py`
- `engine/trend_config.py`
- `engine/cooldown.py`
- `tests/test_state_and_message.py`

## Notes

Some auxiliary filters are proxy implementations and should be tuned with live replay data. Do not treat alerts as automated trade instructions.
