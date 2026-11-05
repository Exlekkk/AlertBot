# PR#47 Draft: formal short bull-gate + M-top/W-bottom verification

## Locks (user nodded via L · Finance)

### Knife A — formal short vs bull structure
- **Hard gate**: if **1h Dow is bullish** OR **`core_levels` lean=`bull`** → **forbid formal short**
  - Formal short includes `UPPER_KEY_ZONE_REJECTION` / other formal short paths through `assess_trial_candidate`
  - Must kill **A2/A3-class**: formal short against Dow long / lean bull
  - **A1-class** same-direction short (Dow short / break HL, lean ≠ bull) must still pass this gate
- **No long-side mirror** for this hard gate

### Knife B — demote 15m M-top weight (user lock 2026-11-05)
- Tag `m15_supply_reject_m_top` weight **3.5 → 0.2**
- Still appears in short evidence / confluence 辅证
- **Verification layer only** — removed from catalyst alignment and opposite-margin relaxation
- **Cannot alone raise formal**

### Knife C — independent 15m W-bottom (user lock 2026-11-05, same tip)
- Tag `m15_demand_reclaim_w_bottom`, weight **0.2** (same verification tier)
- **Independent module** `engine/m15_w_bottom.py` + evidence key `structure_15m_demand`
- **Must not** reuse / field-flip `m15_supply_reject_m_top`
- Purpose: bottom-fish + true/false rebound (`neckline_reclaim` / `false_bounce`)
- Long-side 辅证 only — **cannot alone raise formal**

## Baseline / rollback
- **Stack base tip**: `683b50b069f736bf7b9012dc1a329c9759c34fcb` (#47 bull-gate + CSV tip fix)
- **Earlier baseline**: `22909372e3c25fee66fb6520932758f42f25ea44` (#35 + 15m M-top + Dow)
- **Rollback label**: `8e3dbea` (#35)
- **tip-detach** Draft: do **not** squash into `main`; do **not** deploy until L + user say so

## Code
- `engine/trial_decision.py`
  - bull-structure hard block (Knife A)
  - M-top score 0.2; excluded from catalyst alignment (Knife B)
  - W-bottom score 0.2 from `structure_15m_demand` (Knife C)
- `engine/m15_w_bottom.py` — independent W detector + demand context builder
- `engine/scanner.py` — demand IFVG zones → `structure_15m_demand`
- Tests: `tests/test_formal_short_bull_gate.py`, `tests/test_m15_supply_reject_m_top.py`, `tests/test_m15_demand_reclaim_w_bottom.py`

## Counterexamples (from LIVE postmortem — Knife A)
| Case | Dow | lean | Expect |
|------|-----|------|--------|
| A1 2026-11-03 16:00 | break HL / active short | neutral | gate quiet |
| A2 2026-11-04 14:00 | break LH / active long | bull | blocked |
| A3 2026-11-05 04:01 | trend up + break LH | bull | blocked |

## Homepage hygiene
PR title + any future squash subject: **short English only**. Detail stays in this file + `reports/bot_changes.csv`.
