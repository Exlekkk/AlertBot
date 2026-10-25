# Architecture (runtime)

Neutral overview of how this bot runs. No strategy playbook.

## Loop

1. Fetch closed exchange klines (4H / 1H; 15m only on shadow paths).
2. Build feature contexts (structure proxies, range state, liquidity/volume approximations).
3. Decide whether a formal 1H alert should fire (observation / key-zone paths are not outbound).
4. Apply cooldown / dedupe, then send on the configured notification channel if allowed.
5. Persist runtime + signal state as JSON (atomic writes).

## Surfaces

| Surface | Role |
|---------|------|
| Scanner (`engine/scanner.py`) | Main 1H decision entry |
| App / webhook process (`app.py`) | HTTP entry and ops helpers |
| Shadow / 15m path | Timing / participation diagnostics only; not a solo formal trigger |
| Notification channel | Delivery; pending-confirmation state is written only after a successful send |
| Cooldown store | Family-level dedupe |
| State JSON | Runtime + signal persistence |

## Evidence bundle

Decision payloads may attach an `evidence` object with approximate, candle-based helpers (`approx` / `candle_proxy` flags). These are engineering features for weighting — not a claim of footprint or order-book feeds.

Auxiliary filters on this path:

| Name | Role |
|------|------|
| `core_levels_filter` | Soft filter on the primary path; never a solo alert |
| `formation_shadow` | Lower-timeframe participation / shadow only; not a formal 1H trigger |

Legacy adapters may remain in parallel while trial weighting is migrated. Public docs do not enumerate indicator brands or vendor scripts.

## Timeframe contract

- **4H** — bias context only.
- **1H** — formal alert layer.
- **15m** — shadow only; must not rewrite 1H logic, titles, cooldowns, or live copy.

## Auto Range + volume weak (see scope doc)

- **Auto Range** (`engine/auto_range.py` via `range_lock`): primary role is oscillation **box** recognition. Confirmed `breakout_*` / `deviation_*` are **low-weight** annotations only (not high-weight sole-drive of formal 试多/试空). `pending_break` never scores. Details: `docs/AUTO_RANGE_AND_VOLUME_WEAK_SCOPE.md`.
- **Unclosed abnormal-volume weak reminder** (`engine/volume_weak.py`): forming-bar volume path, isolated from formal 1H; TG gated by `SMCT_ABNORMAL_VOLUME_WEAK_ENABLED` default `0`; shadow via `scripts/run_volume_weak_shadow.py`.

## Deploy

Do not overwrite production from a Draft PR. See `docs/DEPLOY_CHECKLIST.md`.
