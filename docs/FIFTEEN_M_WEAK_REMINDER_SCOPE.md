# Scope: 15m weak reminders (business chat)

Status: **Draft PR#29 — merge waits for L business pass**. Phase 1 deliverable in this PR: `systemd/smct-15m-shadow.service` (resident log-only shadow). Phase 2 TG remains env-gated off (`SMCT_15M_WEAK_REMINDER_ENABLED` default `0`; not wired in this cut).  
Does **not** change 1H formal trial alerts (`EARLY_LONG_TRIAL` / `EARLY_SHORT_TRIAL`).

## Goal

Business-chat **15m weak reminders**: “possible long/short location,” earlier than closed-1H formal 试多/试空.

Formal path unchanged: **closed 1H only**.

## L-locked copy (2026-10-24; side emoji 2026-10-25)

Short, **single** leading 📍. Side marker: `做多🟢` / `做空🔴` (titles and body; not 📈/📉 after 做多/做空). No formal dual-emoji heads (`📈 … 📈`). No 试多/试空. No 止盈目标. No `开单建议` / `关注点` / `结论` section headers.

### Short (做空🔴)

```
📍 BTC 15m 做空🔴位置提醒

15m 出现可能的做空🔴位置。
这不是 1H 正式观察，只提醒看盘。

区间 xxxxx.xx - xxxxx.xx。
站回 xxxxx.xx → 本提醒失效。
最终以 1H / 4H 为准。
```

### Long (做多🟢)

Same skeleton; swap 做空🔴→做多🟢, 站回→跌破 for the invalidation line.

### Forbidden in TG body/title

- Substrings: `试多`, `试空`, `止盈目标`, `开单建议`, `关注点`, `结论`
- Dual trailing emoji formal heads (e.g. `📈 … 📈`)
- Forbidden wording: 「预警」 in titles/body (use `位置提醒`); no bare side without 🟢/🔴

## Hard gates

| Gate | Rule |
|------|------|
| Bars | **Closed 15m only** (`klines[:-1]`); never forming 1H chase |
| Env master | `SMCT_15M_WEAK_REMINDER_ENABLED` default **`0`**; log-only until on |
| Dedupe | Same zone cluster + side cooldown (`zone_hash` / `recommended_cooldown_bars`) |
| Flip-flop | Side-neutral `zone_cluster_hash` short opposite-side suppress |
| Isolation | Must not mutate 1H cooldown, observation pending, formal scores, or formal titles |
| Coexistence | May fire while 1H is quiet or active; copy must stay “弱提醒” |
| Lead to 1H close | Keep `min_lead_to_1h_close_min=30` |
| Bias | Prefer miss over false positive (raise score / tighten before enabling TG) |

## Building blocks

| Piece | Role |
|-------|------|
| `engine/prealert_15m.py` | Candidate eval; types `PREALERT_LONG` / `PREALERT_SHORT` |
| `scripts/run_15m_shadow.py` | Log-only today (`--shadow`; refuses without flag; never sends TG) |
| `systemd/smct-15m-shadow.service` | **Phase 1 deliverable**: resident shadow unit (`--shadow --log …/logs/15m_shadow.log`) |
| Host | Restore via `smct-15m-shadow`; shadow log was stale since ~2026-05 |

## Phased delivery

1. **This doc** (copy + gates locked).  
2. **Phase 1 — shadow** (this PR): ship `systemd/smct-15m-shadow.service`; enable resident shadow; calibrate false positives; **no TG**.  
3. **Phase 2 — TG** (later): format L-locked template on the **same** candidates; own dedupe store; env default off / still gated; **shadow keeps running**; enable TG only after resident shadow is healthy.

Suggested env (names provisional): `SMCT_15M_WEAK_REMINDER_ENABLED`, optional `SMCT_15M_WEAK_REMINDER_CHAT_ID`, optional `SMCT_15M_WEAK_MIN_SCORE`.

## Shadow continuity (user + L 2026-10-24)

- **Shadow never stops** when TG weak reminders turn on. Phase 2 only adds an env-gated outbound formatter on the **same** `evaluate_15m_prealert` candidates.
- Shadow log path remains the calibration / backtest record (`would_send` / suppress), even while TG is enabled.
- Host note: live `15m_shadow.log` last lines are ~2026-05 — **restore resident shadow first** via `smct-15m-shadow` (`--shadow`) before enabling `SMCT_15M_WEAK_REMINDER_ENABLED=1`. Phase 2 stays env-gated off until then.

## Non-goals

- Mapping 1:1 to LuxAlgo Breakout/Deviation labels  
- Changing closed-1H formal policy  
- Opening TG in the same PR as the first code cut without env default off  

## Test plan (later code PRs)

- Format never contains forbidden markers  
- Enabled=0 ⇒ never Telegram  
- Dedupe / opposite-side unit tests  
- Manual: one known session in shadow logs before enabling TG  

## L locks (2026-10-24 final)

1. Titles exactly: `📍 BTC 15m 做多🟢位置提醒` / `📍 BTC 15m 做空🔴位置提醒` (no 「预警」, no `⚡`; 做多🟢/做空🔴 only — still single leading 📍, no dual formal wrap)
2. Body = prior template (zone + 跌破/站回 invalidation + not-1H-formal disclaimer); forbid 试多/试空/开单建议/关注点/结论
3. Chat: **same business group** (no separate topic required)
4. Keep `min_lead_to_1h_close_min=30` (anti-rush into 1H close)

Optional later: `/check` one-line 15m on/off — not required for Phase 1.
