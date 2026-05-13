[PATCH_NOTES.md](https://github.com/user-attachments/files/27696715/PATCH_NOTES.md)
# Patch Notes — Trend Segment Engine v1

## Summary

This release replaces the old public alert flow with a BTC 1H trend segment decision engine.

The new main path focuses on:

- 4H background context
- 1H structure change detection
- key price zones
- trend continuation state
- external-safe Telegram wording
- cooldown / deduplication based on trend alert signatures

## Key changes

### Scanner

`engine/scanner.py` now uses only:

- `4h`
- `1h`

The main scanner path no longer requests or depends on `15m`.

### Trend engine

Added / updated:

- `engine/liquidity.py`
- `engine/msb_ob.py`
- `engine/trend_matrix.py`
- `engine/aux_filters.py`
- `engine/trend_segments.py`
- `engine/trend_snapshot.py`
- `engine/trend_config.py`
- `engine/trend_messages.py`

### Telegram messages

Public messages now use neutral wording:

- 结构转多
- 结构转空
- 多头延续观察
- 空头延续观察
- 关注区间
- 大周期
- 动能与热度
- 风险位
- 结论

Telegram messages are checked to avoid leaking internal terminology.

### Cooldown

Trend alerts use signature-based cooldown keys instead of the old slot/family keys.

### Tests

The test suite covers:

- 4H context does not hard-block high-quality 1H structure changes.
- 1H weak structure against strong 4H context can be suppressed.
- 15m is not requested by the scanner.
- Short/noisy moves do not trigger structure alerts.
- Mid-quality moves with recent key-area trigger can create structure alerts.
- Continuation requires existing trend state.
- Telegram messages include emoji titles and do not leak internal terminology.
- Trend cooldown avoids old slot/family writes.

## Validation

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

Auxiliary market filters remain proxy implementations and should be tuned through live replay / dry-run observation.
