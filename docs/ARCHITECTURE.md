# Architecture (runtime)

Neutral overview of how this bot runs. No strategy playbook.

## Loop

1. Fetch closed Binance klines (4H / 1H; 15m only for shadow / prealert paths).
2. Build feature contexts (structure proxies, range state, liquidity sweep proxy, volume-profile approx, imbalance zones).
3. Decide whether a formal 1H alert or key-zone observation should fire.
4. Apply cooldown / dedupe, then send Telegram if allowed.
5. Persist runtime + signal state as JSON (atomic writes).

## Surfaces

| Surface | Role |
|---------|------|
| Scanner (`engine/scanner.py`) | Main 1H decision entry |
| Webhook / X path | Separate entry; must not share 1H formal state carelessly |
| Shadow / 15m prealert | Participation / timing only; not a solo formal trigger |
| Telegram | Delivery; pending confirmation state is written only after successful send |
| Ops `/check` | Webhook app getUpdates poll (default) or POST `/telegram/updates`; status only |
| Bihourly probe | Silent when healthy; error alert only |
| Cooldown store | Family-level dedupe |

## Evidence bundle

Decision payloads may attach an `evidence` object with approximate, candle-based helpers (`approx` / `candle_proxy` flags). These are engineering features for weighting — not a claim of footprint / order-book feeds.

Auxiliary filters on this path:

| Name | Role |
|------|------|
| `core_levels_filter` | 1H+ soft filter only; never a solo alert |
| `formation_shadow` | 15m participation / shadow only; not a formal 1H trigger |

Legacy liquidity / volume-profile / ICT adapters remain in parallel while trial weighting is migrated.

## Deploy

Do not overwrite production from a Draft PR. See `docs/DEPLOY_CHECKLIST.md` for a short file checklist.
