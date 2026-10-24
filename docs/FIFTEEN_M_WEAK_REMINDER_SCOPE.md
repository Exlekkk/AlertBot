# Scope: 15m weak reminders (business chat)

Status: **Draft only**. Does not change 1H formal trial alerts.
L owns final Telegram copy; this doc locks engineering boundaries.

## Goal

Ship a **separate** 15m “possible location” reminder into the business Telegram chat so the operator sees earlier than closed-1H formal 试多/试空.

Formal path stays: **closed 1H only**, EARLY_LONG/SHORT_TRIAL templates only.

## Non-goals

- Do not evaluate or send on the **forming** 1H candle.
- Do not rename, reuse, or visually mimic `试多观察` / `试空观察` titles or full templates.
- Do not mutate 1H `should_alert`, cooldown store keys, observation pending state, or formal scores.
- Do not chase LuxAlgo chart labels 1:1; reuse existing `evaluate_15m_prealert` zone/reaction logic as the candidate source.

## Existing building blocks

| Piece | Role today |
|-------|------------|
| `engine/prealert_15m.py` | Closed-15m evaluate; `shadow_only=True`; types `PREALERT_LONG` / `PREALERT_SHORT` |
| `scripts/run_15m_shadow.py` | Log-only loop (`--shadow` required); never Telegram |
| Host | No `smct-15m` unit; last shadow log ~2026-05 |

## Delivery plan (phased)

### Phase 0 — scope + copy lock (this PR)

- This document.
- L locks short copy (single leading emoji, 1–3 lines, no formal section headers).

### Phase 1 — shadow calibrate (no TG)

- Run `run_15m_shadow.py --shadow` under a dedicated systemd unit or cron (WorkingDirectory `/opt/smct-alert`).
- Log `would_send` / suppress reasons; compare against chart events (e.g. range deviation) offline.
- Raise `min_trigger_score` / cooldowns if noisy before any TG.

### Phase 2 — TG weak reminder (gated)

New thin sender path (suggested module `services/prealert_telegram.py` or extend shadow runner):

1. Call `evaluate_15m_prealert` on **closed** 15m (+1H/4H context as today).
2. If `should_alert` and env allow → format **weak** copy → send to business chat.
3. Own dedupe store (do **not** share formal family/slot keys with 1H trials).

Env kill switch (names provisional):

| Env | Default | Meaning |
|-----|---------|---------|
| `SMCT_15M_WEAK_REMINDER_ENABLED` | `0` | Master off until calibrated |
| `SMCT_15M_WEAK_REMINDER_CHAT_ID` | (business chat) | Optional override; else same chat as formal |
| `SMCT_15M_WEAK_MIN_SCORE` | ≥ current `min_trigger_score` | Extra caution dial |

When disabled: behave exactly like Phase 1 (log only).

## Hard gates (engineering)

- **Copy gate:** deny send if title/body contains formal markers (`试多`, `试空`, `开单建议`, `关注点`, `结论`, or formal alert_type strings).
- **Allowlist:** only `PREALERT_LONG` / `PREALERT_SHORT` (rename display title per L lock; keep type ids stable or alias).
- **Dedupe:** per `zone_cluster_hash` + side; honor `recommended_cooldown_bars` / opposite-side cooldown from prealert.
- **No flip-flop:** existing side-neutral `zone_cluster_hash` blocks rapid long↔short on same cluster.
- **Closed bar only:** keep `klines[:-1]` (already in shadow script).
- **Isolation:** never call `save_observation_state` / 1H `mark_sent` for formal types from this path.

## Suggested weak copy shape (placeholder — L locks)

One line title + one line zone; optional invalid level. Example placeholders only:

- `⚡ BTC 15m 空位提示` / `⚡ BTC 15m 多位提示`
- `区 xxxx-yyyy · 失效 zzzz`

Must **not** use 预警 copy that reads like formal 试多/试空观察.

Current code titles (`📍 BTC 15m 做多预警`) are **log legacy** and must be replaced before TG.

## Ops / deploy

- Separate unit e.g. `smct-15m-reminder` (User=admin or root consistent with host).
- Deploy checklist: enable env only after Phase 1 review; rollback = set enabled `0` + stop unit (1H units untouched).
- `/check` stays 1H/ops status; do not overload with 15m spam (optional one-line “15m reminder: on/off”).

## Test plan

- Unit: format weak copy never matches formal trial markers; disabled env never sends.
- Unit: dedupe / opposite-side cooldown.
- Manual: Phase 1 log vs a known breakout session; Phase 2 one dry send with enabled=1 then kill switch.

## Open items for L

1. Exact emoji + title strings (long/short).
2. Same business chat vs dedicated thread/topic.
3. Whether `min_lead_to_1h_close_min` stays 30 (already anti-chase near 1H close).
