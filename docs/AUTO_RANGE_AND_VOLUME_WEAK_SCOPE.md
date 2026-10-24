# Scope: Auto Range 低权 + 未收盘异常量能弱提醒

Status: **Draft PR#32 — merge waits for L final pass + user awake**.  
Rollback tip: **`ceb42f1`** (main before this Draft).  
Does **not** change 1H formal trial titles (`EARLY_LONG_TRIAL` / `EARLY_SHORT_TRIAL`) or open TG by default.  
**No** `smct-volume-weak-shadow.service` in this PR (unit deferred until after merge + user awake).

## L locks (2026-10-25)

### 1) Auto Range — low weight — **PASSED**

| Rule | Detail |
|------|--------|
| Primary use | Recognize oscillation **box** (range location) |
| Formal events | Only **pending → confirmed** `breakout_*` / `deviation_*` from `engine/auto_range.py` state machine |
| Forbidden | Chasing instantaneous / raw Lux-like tags as high-weight drive |
| Max role | Weak catalyst / stage **annotation** |
| Forbidden | Naked chase; high-weight sole-drive of formal 试多/试空 |
| Direction | Still from structure + liquidity / IFVG / POC + RAR (existing evidence path) |

### 2) Unclosed abnormal-volume weak reminder — **frequency + copy LOCKED**

| Rule | Detail |
|------|--------|
| Product | Weak reminder on **forming / unclosed** abnormal volume |
| Isolation | Must **not** mutate 1H cooldown, observation pending, formal scores, or formal title family |
| Bars | Forming-bar read OK for this weak path only; formal 1H stays closed-candle |
| Env master | `SMCT_ABNORMAL_VOLUME_WEAK_ENABLED` default **`0`** |
| Copy | L-locked Chinese (see below); forbid 试多/试空 |
| Bias | Prefer miss over false positive |

## Isolation table

| Concern | Formal 1H trial | Auto Range (this Draft) | Volume weak (this Draft) |
|---------|-----------------|-------------------------|--------------------------|
| Candle | Closed 1H | Closed 1H state machine | **Forming** 15m / 1H volume OK |
| Score weight | Full evidence path | Event score **0.5** (was 1.5); box location unchanged | **No** formal score mutation |
| Sole-drive 试多/试空 | Via directional catalyst gates | Auto Range **cannot** sole-drive (`breakout_matches` removed from `matching_fresh_event`) | Never |
| Cooldown store | `SignalStateStore` / family | Unchanged | Own shadow dedupe only |
| TG | Existing formal path | N/A (annotation only) | Env default **off** |
| Titles | 试多/试空 | N/A | L-locked weak copy; forbid 试多/试空 |

## Auto Range score change (code)

| Event | Before | After |
|-------|--------|-------|
| `deviation_down` → long | `+1.5` `range_reclaim_after_break_down` | `+0.5` same token |
| `deviation_up` → short | `+1.5` `range_reclaim_after_break_up` | `+0.5` same token |
| `breakout_up` / `breakout_down` (confirmed) | no score (gate via `accepted_breakout`) | `+0.5` annotation token; still **not** sole `matching_fresh_event` |
| `pending_break` | no score | no score (enforced + tests) |
| Box edge location (`range_lower_location` / …) | `+1.5` / `-2.0` | **unchanged** (box recognition) |

`accepted_breakout` still exempts wrong-edge / poor RR hard-blocks when confirmed — that is gate plumbing, not high-weight score drive.

## Volume weak — frequency (**L-locked** into code)

Wired in `engine/volume_weak.py` + `scripts/run_volume_weak_shadow.py` defaults.

| Knob | Locked value | Notes |
|------|--------------|-------|
| Hard abs volume | `MIN_15M_ABNORMAL_VOLUME` **or** `MIN_1H_ABNORMAL_VOLUME` (reuse `x_signals`) | Same hard floor as X lane |
| Min volume ratio | **1.8** vs `vol_sma20` (15m or 1H) | Stricter than X impulse 1.45 — prefer miss |
| Same-side cooldown | **4** × 15m bars | Per side |
| Opposite-side cooldown | **2** × 15m bars | Flip-flop dampen |
| Side from | Forming 15m body (`close` vs `open`) | Neutral/flat → no alert |
| Shadow log | `logs/volume_weak_shadow.log` | Script only; **no systemd unit in this PR** |
| TG | `SMCT_ABNORMAL_VOLUME_WEAK_ENABLED=0` | Enable only after merge + shadow calm |

Env: `SMCT_ABNORMAL_VOLUME_WEAK_ENABLED` (optional later chat id).

## Volume weak — copy (**L-locked**)

```
📍 BTC 未收盘放量弱提醒

15m 未收盘出现异常放量（偏多🟢 / 偏空🔴）。
vol≈{vol}  ratio≈{ratio}
这不是 1H 正式观察，只提醒看盘。
最终以 1H / 4H 为准。
```

- Side marker: `偏多🟢` or `偏空🔴` (not 试多/试空).
- `vol` integer; `ratio` one decimal.
- Implemented by `format_volume_weak_message`.

## Building blocks

| Piece | Role |
|-------|------|
| `engine/auto_range.py` | State machine (unchanged semantics) |
| `engine/trial_decision.py` | Demoted event weights + no sole-drive |
| `engine/volume_weak.py` | Forming abnormal-volume evaluate + L-locked format |
| `engine/x_signals.py` / `abnormal.py` | Shared volume floors only |
| `scripts/run_volume_weak_shadow.py` | Log-only shadow (`--shadow`; never TG) |

## Phased delivery

1. **This Draft (PR#32)** — Auto Range demotion + volume-weak code/shadow + L-locked frequency/copy; TG env default off; **no systemd unit**.  
2. **After user awake + merge** — optional `smct-volume-weak-shadow.service` + calibrate shadow.  
3. **Later** — TG enable after shadow healthy.

## Non-goals

- Mapping 1:1 to LuxAlgo Breakout/Deviation labels as high-weight drivers  
- Changing closed-1H formal policy / 试多/试空 templates  
- Enabling TG in the same cut without env default off  
- Mutating 1H cooldown or observation pending from volume weak  
- Shipping `smct-volume-weak-shadow.service` in this PR  
- Merging / deploying / urging pull while user sleeps  

## Test plan

- `pending_break` ⇒ no direction score tokens  
- Confirmed `deviation_*` ⇒ weight `+0.5` not `+1.5`  
- Confirmed `breakout_*` ⇒ annotation only; not sole directional catalyst  
- Volume weak: forming bar can fire; `enabled=0` ⇒ `should_send_volume_weak_tg` false  
- Frequency constants locked (1.8 / 4 / 2) + floors from x_signals  
- Formatter matches L copy (偏多🟢/偏空🔴); forbids `试多` / `试空` / 草稿 / TODO  
- `./scripts/run_ci.sh` green  

## Rollback

```text
git checkout main && git reset --hard ceb42f1
# or revert the squash commit that lands this Draft
```

Host tip to restore before this Draft: **`ceb42f1`**.
