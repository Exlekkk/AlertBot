[PATCH_NOTES.md](https://github.com/user-attachments/files/27114652/PATCH_NOTES.md)
# AlertBot Patch Notes — X hard volume OR gate

## Patch name

`x-volume-hard-gate-or-fix`

## Reason

The user's hard requirement for X / abnormal volume gating is:

```text
15m VOL > 6000 OR 1h VOL > 12000
```

The previous implementation incorrectly used:

```text
15m VOL > 6000 AND 1h VOL > 12000
```

This made X too strict. A 1h abnormal move could be blocked when the latest closed 15m candle did not also exceed the 15m absolute volume threshold.

## Changed files

### `engine/x_signals.py`

- Fixed `_passes_hard_volume_gate(...)`.
- Previous behavior:

```python
return vol_15m > MIN_15M_ABNORMAL_VOLUME and vol_1h > MIN_1H_ABNORMAL_VOLUME
```

- New behavior:

```python
return vol_15m > MIN_15M_ABNORMAL_VOLUME or vol_1h > MIN_1H_ABNORMAL_VOLUME
```

- Updated the nearby comment to explicitly state the OR relationship:
  - `15m VOL > 6000`
  - or `1h VOL > 12000`

### `tests/test_state_and_message.py`

- Added regression test:

```text
test_x_hard_volume_gate_uses_or_between_15m_and_1h
```

The test verifies:

- 15m high / 1h low => pass
- 15m low / 1h high => pass
- both high => pass
- both low => fail

## Deliberately not changed

This patch does **not** change:

- ABC logic.
- X signal categories.
- X impulse / sweep / first-burst shape checks.
- cooldown / suppress behavior.
- Telegram message formatting.
- phase anchor.
- ABCX bucket independence.

## Important note

This patch fixes the hard volume gate only.

It does **not** mean that `1h VOL > 12000` alone automatically sends an X alert. After the hard volume gate passes, X still checks the existing X behavior layer, such as:

- impulse breakout
- first burst
- wick sweep resolve
- relative force / h1 force confirmation

If the desired rule is:

```text
1h VOL > 12000 alone should produce a dedicated X_H1_FORCE alert
```

that should be added as a separate X sub-type in `engine/x_signals.py`, not by borrowing from A/B/C.

## Verification run locally

```bash
python -m unittest discover -s tests
python -m compileall -q engine services tests
```

Result:

```text
Ran 14 tests
OK
compileall OK
```
