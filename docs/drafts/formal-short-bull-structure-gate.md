# Draft: formal short blocked by bull structure

## Locks (user nodded via L · Finance)

- **Hard gate**: if **1h Dow is bullish** OR **`core_levels` lean=`bull`** → **forbid formal short**
  - Formal short includes `UPPER_KEY_ZONE_REJECTION` / other formal short paths through `assess_trial_candidate`
  - Must kill **A2/A3-class**: formal short against Dow long / lean bull
  - **A1-class** same-direction short (Dow short / break HL, lean ≠ bull) must still pass this gate
- **No other knives** in this Draft (no long-side mirror unless already symmetric — this knife does **not** add a long veto)
- **Baseline tip**: `22909372e3c25fee66fb6520932758f42f25ea44` (#35 + 15m M-top + Dow)
- **Rollback label**: `8e3dbea` (#35)
- **tip-detach** Draft: do **not** squash into `main`; do **not** deploy until L + user say so

## Code

- `engine/trial_decision.py`
  - `build_trial_context` exposes `structure_dow` summary + `core_levels_lean`
  - `assess_trial_candidate` appends `formal_short_blocked_by_bull_structure` when:
    - short side, and
    - (`active_long_evidence` OR `trend=="up"`) **unless** `active_short_evidence` (break HL clears Dow-bull for this gate), **or**
    - `core_levels_lean == "bull"`
- Tests: `tests/test_formal_short_bull_gate.py`

## Counterexamples (from LIVE postmortem)

| Case | Dow | lean | Expect |
|------|-----|------|--------|
| A1 2026-11-03 16:00 | break HL / active short | neutral | gate quiet |
| A2 2026-11-04 14:00 | break LH / active long | bull | blocked |
| A3 2026-11-05 04:01 | trend up + break LH | bull | blocked |

## Homepage hygiene

PR title + any future squash subject: **short English only**. Detail stays in this file + `reports/bot_changes.csv`.
