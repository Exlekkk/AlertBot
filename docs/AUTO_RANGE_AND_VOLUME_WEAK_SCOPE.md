# Scope: Auto Range 低权 + 未收盘异常量能弱提醒

Status: **Draft — merge waits for L business pass**.  
Rollback tip: **`ceb42f1`** (main before this Draft).  
Does **not** change 1H formal trial titles (`EARLY_LONG_TRIAL` / `EARLY_SHORT_TRIAL`) or open TG by default.

## L locks (2026-10-25 night)

### 1) Auto Range — low weight

| Rule | Detail |
|------|--------|
| Primary use | Recognize oscillation **box** (range location) |
| Formal events | Only **pending → confirmed** `breakout_*` / `deviation_*` from `engine/auto_range.py` state machine |
| Forbidden | Chasing instantaneous / raw Lux-like tags as high-weight drive |
| Max role | Weak catalyst / stage **annotation** |
| Forbidden | Naked chase; high-weight sole-drive of formal 试多/试空 |
| Direction | Still from structure + liquidity / IFVG / POC + RAR (existing evidence path) |

### 2) Unclosed abnormal-volume weak reminder — required

| Rule | Detail |
|------|--------|
| Product | Weak reminder on **forming / unclosed** abnormal volume |
| Isolation | Must **not** mutate 1H cooldown, observation pending, formal scores, or formal title family |
| Bars | Forming-bar read OK for this weak path only; formal 1H stays closed-candle |
| Env master | `SMCT_ABNORMAL_VOLUME_WEAK_ENABLED` default **`0`** |
| Copy | Short; **not** 1H 试多/试空 template; L locks final Chinese later (draft placeholder in code) |

## Isolation table

| Concern | Formal 1H trial | Auto Range (this Draft) | Volume weak (this Draft) |
|---------|-----------------|-------------------------|--------------------------|
| Candle | Closed 1H | Closed 1H state machine | **Forming** 15m / 1H volume OK |
| Score weight | Full evidence path | Event score **0.5** (was 1.5); box location unchanged | **No** formal score mutation |
| Sole-drive 试多/试空 | Via directional catalyst gates | Auto Range **cannot** sole-drive (`breakout_matches` removed from `matching_fresh_event`) | Never |
| Cooldown store | `SignalStateStore` / family | Unchanged | Own shadow dedupe only |
| TG | Existing formal path | N/A (annotation only) | Env default **off** |
| Titles | 试多/试空 | N/A | Draft weak copy; forbid 试多/试空 |

## Auto Range score change (code)

| Event | Before | After |
|-------|--------|-------|
| `deviation_down` → long | `+1.5` `range_reclaim_after_break_down` | `+0.5` same token |
| `deviation_up` → short | `+1.5` `range_reclaim_after_break_up` | `+0.5` same token |
| `breakout_up` / `breakout_down` (confirmed) | no score (gate via `accepted_breakout`) | `+0.5` annotation token; still **not** sole `matching_fresh_event` |
| `pending_break` | no score | no score (enforced + tests) |
| Box edge location (`range_lower_location` / …) | `+1.5` / `-2.0` | **unchanged** (box recognition) |

`accepted_breakout` still exempts wrong-edge / poor RR hard-blocks when confirmed — that is gate plumbing, not high-weight score drive.

## Volume weak — frequency draft (for L to scan)

Provisional; not locked.

| Knob | Draft value | Notes |
|------|-------------|-------|
| Hard abs volume | `MIN_15M_ABNORMAL_VOLUME=6000` **or** `MIN_1H=12000` (reuse `x_signals`) | Same hard floor as X lane |
| Min volume ratio | **1.8** vs `vol_sma20` (15m or 1H) | Stricter than X impulse 1.45 — prefer miss |
| Same-side cooldown | **4** × 15m bars | Per side |
| Opposite-side cooldown | **2** × 15m bars | Flip-flop dampen |
| Side from | Forming 15m body (`close` vs `open`) | Neutral/flat → no alert |
| Shadow log | `logs/volume_weak_shadow.log` | Always log-capable |
| TG | `SMCT_ABNORMAL_VOLUME_WEAK_ENABLED=0` | Enable only after L + shadow calm |

Suggested env (provisional): `SMCT_ABNORMAL_VOLUME_WEAK_ENABLED`, optional later `SMCT_ABNORMAL_VOLUME_WEAK_CHAT_ID`.

## Building blocks

| Piece | Role |
|-------|------|
| `engine/auto_range.py` | State machine (unchanged semantics) |
| `engine/trial_decision.py` | Demoted event weights + no sole-drive |
| `engine/volume_weak.py` | Forming abnormal-volume evaluate + draft format |
| `engine/x_signals.py` / `abnormal.py` | Shared volume floors only |
| `scripts/run_volume_weak_shadow.py` | Log-only shadow (`--shadow`; never TG) |

## Phased delivery

1. **This Draft** — scope + Auto Range demotion + volume-weak scaffold + shadow script + tests; TG env default off.  
2. **L business pass** — lock frequency numbers + final Chinese copy.  
3. **Later** — optional resident systemd unit + TG enable after shadow healthy. **不合入/不上机 until L says so.**

## Non-goals

- Mapping 1:1 to LuxAlgo Breakout/Deviation labels as high-weight drivers  
- Changing closed-1H formal policy / 试多/试空 templates  
- Enabling TG in the same cut without env default off  
- Mutating 1H cooldown or observation pending from volume weak  
- Merging / deploying / urging pull while user sleeps  

## Test plan

- `pending_break` ⇒ no direction score tokens  
- Confirmed `deviation_*` ⇒ weight `+0.5` not `+1.5`  
- Confirmed `breakout_*` ⇒ annotation only; not sole directional catalyst  
- Volume weak: forming bar can fire; `enabled=0` ⇒ `should_send_volume_weak_tg` false  
- Draft message forbids substrings `试多` / `试空`  
- `./scripts/run_ci.sh` green  

## Rollback

```text
git checkout main && git reset --hard ceb42f1
# or revert the squash commit that lands this Draft
```

Host tip to restore before this Draft: **`ceb42f1`**.
