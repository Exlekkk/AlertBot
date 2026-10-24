# Scope: 15m weak reminders (business chat)

Status: **Draft only — do not merge until L/user nod Phase work**.  
Does **not** change 1H formal trial alerts (`EARLY_LONG_TRIAL` / `EARLY_SHORT_TRIAL`).

## Goal

Business-chat **15m weak reminders**: “possible long/short location,” earlier than closed-1H formal 试多/试空.

Formal path unchanged: **closed 1H only**.

## L-locked copy (2026-10-24)

Short, **single** leading emoji. No formal dual-emoji heads. No 试多/试空. No 止盈目标. No `开单建议` / `关注点` / `结论` section headers.

### Short (做空)

```
📍 BTC 15m 做空位置提醒

15m 出现可能的做空位置。
这不是 1H 正式观察，只提醒看盘。

区间 xxxxx.xx - xxxxx.xx。
站回 xxxxx.xx → 本提醒失效。
最终以 1H / 4H 为准。
```

### Long (做多)

Same skeleton; swap 做空→做多, 站回→跌破 for the invalidation line.

### Forbidden in TG body/title

- Substrings: `试多`, `试空`, `止盈目标`, `开单建议`, `关注点`, `结论`
- Dual trailing emoji formal heads (e.g. `📈 … 📈`)
- Legacy log titles `📍 BTC 15m 做多预警` / `做空预警` (replace before any TG send)

## Hard gates

| Gate | Rule |
|------|------|
| Bars | **Closed 15m only** (`klines[:-1]`); never forming 1H chase |
| Env master | `SMCT_15M_WEAK_REMINDER_ENABLED` default **`0`**; log-only until on |
| Dedupe | Same zone cluster + side cooldown (`zone_hash` / `recommended_cooldown_bars`) |
| Flip-flop | Side-neutral `zone_cluster_hash` short opposite-side suppress |
| Isolation | Must not mutate 1H cooldown, observation pending, formal scores, or formal titles |
| Coexistence | May fire while 1H is quiet or active; copy must stay “弱提醒” |
| Bias | Prefer miss over false positive (raise score / tighten before enabling TG) |

## Building blocks

| Piece | Role |
|-------|------|
| `engine/prealert_15m.py` | Candidate eval; types `PREALERT_LONG` / `PREALERT_SHORT` |
| `scripts/run_15m_shadow.py` | Log-only today (`--shadow`) |
| Host | No live 15m unit; shadow log stale since ~2026-05 |

## Phased delivery

1. **This doc** (copy + gates locked).  
2. **Phase 1 — shadow**: systemd/cron run shadow; calibrate false positives; no TG.  
3. **Phase 2 — TG**: format L-locked template; own dedupe store; env default off; enable after Phase 1 OK.

Suggested env (names provisional): `SMCT_15M_WEAK_REMINDER_ENABLED`, optional `SMCT_15M_WEAK_REMINDER_CHAT_ID`, optional `SMCT_15M_WEAK_MIN_SCORE`.

## Non-goals

- Mapping 1:1 to LuxAlgo Breakout/Deviation labels  
- Changing closed-1H formal policy  
- Opening TG in the same PR as the first code cut without env default off  

## Test plan (later code PRs)

- Format never contains forbidden markers  
- Enabled=0 ⇒ never Telegram  
- Dedupe / opposite-side unit tests  
- Manual: one known session in shadow logs before enabling TG  

## Open for later (not blocking this doc)

- Dedicated chat vs same business chat (default: same chat)  
- Whether `/check` shows a one-line 15m on/off bit  
