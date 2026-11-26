# PR#47 Draft: formal short bull-gate + M/W verify (15m/1H/4H)

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

### Knife D — extend M-top / W-bottom to 1H + 4H (user lock 2026-11-05 via L)
- Weight still **0.2** each (verification layer; cannot alone raise formal)
- M / W remain **independent** (no field-flip / mirror)
- **Per-TF independent evidence** — never copy 15m result into 1H/4H
- Tags / evidence keys:
  - M: `h1_supply_reject_m_top` → `structure_1h`; `h4_supply_reject_m_top` → `structure_4h`
  - W: `h1_demand_reclaim_w_bottom` → `structure_1h_demand`; `h4_demand_reclaim_w_bottom` → `structure_4h_demand`
- Shared geometry helpers OK; detection entry + evidence keys must stay TF/pattern-split
- Stack on tip `8135117`; tip-detach; rollback `8e3dbea`

## Baseline / rollback
- **Prior tip**: `8135117157ae2b8dae9c3b690e7601e933dc6fdb` (#47 bull-gate + 15m M/W 0.2)
- **Stack base tip**: `683b50b069f736bf7b9012dc1a329c9759c34fcb` (#47 bull-gate + CSV tip fix)
- **Earlier baseline**: `22909372e3c25fee66fb6520932758f42f25ea44` (#35 + 15m M-top + Dow)
- **Rollback label**: `8e3dbea` (#35)
- **tip-detach** Draft: do **not** squash into `main`; do **not** deploy until L + user say so

## Code
- `engine/structure.py` — `build_structure_supply_m_top_context` + 15m/1h/4h wrappers
- `engine/m15_w_bottom.py` — `build_structure_demand_w_bottom_context` + 15m/1h/4h wrappers
- `engine/trial_decision.py` — score each TF tag at 0.2; confluence tokens; still out of catalyst alignment
- `engine/scanner.py` — per-TF klines + IFVG zones → independent evidence keys
- Tests: `tests/test_formal_short_bull_gate.py`, `tests/test_m15_supply_reject_m_top.py`, `tests/test_m15_demand_reclaim_w_bottom.py`, `tests/test_htf_m_top_w_bottom_verify.py`

## Counterexamples (from LIVE postmortem — Knife A)
| Case | Dow | lean | Expect |
|------|-----|------|--------|
| A1 2026-11-03 16:00 | break HL / active short | neutral | gate quiet |
| A2 2026-11-04 14:00 | break LH / active long | bull | blocked |
| A3 2026-11-05 04:01 | trend up + break LH | bull | blocked |

## Homepage hygiene
PR title + any future squash subject: **short English only**. Detail stays in this file + `reports/bot_changes.csv`.
