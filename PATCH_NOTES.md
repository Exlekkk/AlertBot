[Uploading PATCH_NOTES_20260424_complete.md…]()
# AlertBot Patch Notes — 2026-04-24

## Patch name

`RAR + Telegram reliability + state persistence + dotenv optional hotfix`

## Summary

This patch improves AlertBot reliability without changing the main ABC/X signal logic.

The patch does four main things:

1. Calibrates the Python RAR calculation closer to the LuxAlgo Rainbow Adaptive RSI Pine source.
2. Makes Telegram sending safer by only marking a signal as sent when Telegram actually returns success.
3. Makes cooldown/runtime state persistence safer with atomic file writes and warning logs.
4. Makes `python-dotenv` optional so manual `python3` test runs do not fail when `dotenv` is missing.

## Changed files

### `engine/indicators.py`

- Reworked `rsi_series(...)` to use TradingView-style Wilder/RMA smoothing.
- Reworked `rar_components(...)` to better follow the LuxAlgo Rainbow Adaptive RSI source formula:
  - `alpha = abs(rsi(src - ama[1], length) / 100 - 0.5)`
  - adaptive AMA update
  - `rar_value = rsi(ama, length)`
  - `trigger = ema(rsi(ema(src, length / 2), length), length / 2)`
- This only calibrates computed RAR values.
- RAR is still not wired into ABC/X signal decisions.

### `services/telegram.py`

- Added `TelegramSendError`.
- `send_telegram_message(...)` now requires:
  - HTTP request success
  - valid Telegram JSON response
  - Telegram `ok=true`
- Failed Telegram sends now raise an error instead of returning raw response text.

### `engine/scanner.py`

- Telegram send failures are now logged as `telegram_send_failed`.
- Failed Telegram sends no longer call `mark_sent(...)`.
- Failed Telegram sends no longer enter cooldown.
- Runtime summary now carries `near_miss_signals` when present.
- `near_miss_signals` are diagnostics only:
  - no Telegram broadcast
  - no cooldown effect
  - no ABC/X classification impact

### `engine/cooldown.py`

- Cooldown state file writes now use a temporary file plus atomic replace.
- Load/save failures now log warnings instead of being silently swallowed.
- Cooldown logic and suppression limits are unchanged.

### `engine/runtime_state.py`

- Runtime state file writes now use a temporary file plus atomic replace.
- Load/save failures now log warnings instead of being silently swallowed.

### `config.py`

- Made `python-dotenv` optional.
- If `dotenv` is installed, `.env` loading behavior is unchanged.
- If `dotenv` is missing in a manual `python3` environment, imports/tests no longer crash.
- This fixes:

```text
ModuleNotFoundError: No module named 'dotenv'
```

during server-side manual test runs.

### `tests/test_state_and_message.py`

Added or updated tests for:

- RAR trigger formula regression.
- Telegram success and failure behavior.
- Scanner behavior when Telegram sending fails.
- Signal/runtime state persistence.
- Optional dotenv import compatibility.
- Existing ABC/X independence tests remain intact.

## Deliberately not changed

This patch does **not** change:

- `engine/signals.py` ABC main classifier logic.
- `engine/x_signals.py` X/abnormal trigger logic.
- ABC/X bucket independence.
- A/B/C “three independent buckets” principle.
- X as an independent abnormal-event bucket.
- Phase anchor logic.
- Cooldown/suppress limits.
- Telegram near-miss broadcasting.
- 1h + 15m combined sensitivity behavior.

## Important design boundary

ABCX remains four independent buckets:

- A problems should be fixed inside A.
- B problems should be fixed inside B.
- C problems should be fixed inside C.
- X problems should be fixed inside X.

No bucket should borrow logic from another bucket to “repair” a weak signal.

In other words:

```text
No borrowing water from another bucket.
No拆东墙补西墙.
```

## Expected behavior after patch

Expected improvements:

- RAR values are more consistent with the TradingView source.
- Telegram failed sends are no longer falsely treated as successful.
- Cooldown/runtime state files are less likely to become corrupted.
- State write/load failures are easier to diagnose from logs.
- Manual server tests using `python3` no longer fail just because `python-dotenv` is absent.

Expected non-changes:

- AlertBot should not become more silent.
- AlertBot should not become more aggressive.
- ABC/X trigger frequency should remain effectively unchanged.
- X remains separated from ABC.
- `near_miss_signals` do not create new Telegram alerts.

## Local verification

The following commands were run successfully in the patch workspace:

```bash
python -m unittest discover -s tests
python -m compileall -q engine services tests
```

## Server verification

The following commands were run successfully on the server after GitHub update and pull:

```bash
cd /opt/smct-alert

git status
git pull --ff-only origin main

python3 -m unittest discover -s tests
python3 -m compileall -q engine services tests

sudo systemctl restart smct-scanner.service
sudo systemctl status smct-scanner.service --no-pager -l
```

Observed server result:

```text
Ran 13 tests
OK
smct-scanner.service active (running)
```

## Operational notes

If checking live logs:

```bash
journalctl -u smct-scanner.service -f
```

If future manual `python3` tests fail due to missing packages again, first compare:

```bash
which python3
./venv/bin/python -V
./venv/bin/python -m unittest discover -s tests
```

The production service currently runs through the project virtual environment:

```text
/opt/smct-alert/venv/bin/python
```

## Final status

Patch deployed successfully.

Current server status:

```text
tests: OK
compile: OK
service: active (running)
```
