# Architecture (runtime)

Neutral overview of how this bot runs. No strategy playbook.

## Loop

1. Fetch closed exchange klines (4H / 1H; 15m only on shadow paths).
2. Build feature contexts (structure proxies, range state, liquidity/volume approximations).
3. Decide whether a formal 1H alert or a key-zone observation should fire.
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

## Deploy

Do not overwrite production from a Draft PR. See `docs/DEPLOY_CHECKLIST.md`.
