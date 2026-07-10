# v1.4.0 BTC Framework Replay Review

## Scope

- Candidate: `v1.4.0-btc-smc-ict-chart-alignment`.
- Symbol: Binance USD-M `BTCUSDT`.
- Window: every 1H close from 2026-06-09 00:59 through 2026-06-12 23:59, Asia/Singapore.
- Warm-up: May and June 2026 Binance Vision monthly 1H/4H archives; each decision uses at most the latest 500 closed bars.
- Output: `reports/v1.4.0_btc_framework_replay_2026-06-09_12.csv`.

The replay executes the decision engine on each historical close. It does not simulate entries, fees, slippage, targets or profitability.

## Data and indicator boundary

- ICT, MSB-OB, RAR, Inertial, TAI, Fibonacci, log channels, high-volume pivots and FVG VP are calculated from the supplied Pine logic/settings on closed Binance candles.
- Optional exact external ICT `+OB` / `-OB` fields remain supported, but this archive replay uses the Pine reimplementation because Binance candles contain no TradingView drawing objects.
- The bot has no footprint, order-book or true trade-delta feed. Candle-direction volume/CVD, stop-run and absorption fields are explicitly proxies.
- TradingView's custom 13-minute FVG VP input has no native Binance equivalent. The official 1H replay therefore uses the labelled parent-candle profile fallback.
- This report does not test real 15m outcomes. The 15m engine remains shadow-only and isolated from official 1H decisions.

## Aggregate result

| Metric | Result |
| --- | ---: |
| Hourly decisions | 96 |
| Public alerts | 12 |
| Formal trials | 7 |
| Structure shifts | 2 |
| Passive observations | 3 |
| Secondary confirmations | 0 |

Public-alert count is lower than the earlier v1.3.9 candidate replay (20), but raw count is not the acceptance criterion. The important review is whether each reported incident is handled by structure, location, freshness and risk rules.

## Incident review

| Reported incident | v1.4.0 replay result |
| --- | --- |
| 6/9 23:00 late short | No short alert. The late window remains silent; same-box duplicate/risk checks suppress the available reactions. The replay also does not fabricate the preferred 21:00 short without a qualified official trigger. |
| 6/10 07:00 weak range long | Suppressed as `formal_without_directional_catalyst`. A separate long appeared earlier at 02:59 only after the lower FVG reaction and sell-side reclaim evidence. |
| 6/10 11:00 same-box flip to short | Suppressed as `wrong_range_edge`; no official short flip at the reported time. |
| 6/10 duplicate Telegram sections | Message-section deduplication tests pass; risk/conclusion sections are not repeated. |
| 6/11 07:00 wrong short into support/+OB | Suppressed as `wrong_range_edge`. |
| 6/11 preferred early long | No 07:00 long is fabricated: the supplied-source RAR and Inertial slopes were still falling in the replay. The engine can promote a near-`+OB` early long when both actually turn; that path is covered by a deterministic test. |
| 6/11 10:00 late long | Suppressed after price moved to the wrong box edge. A later 11:59 short is a distinct premium/high-volume-resistance event with fresh buy-side stop-run rejection, not a flip at the original lower-area timestamp. |
| 6/12 10:00 late long | No formal long. The available candidates are blocked by wrong-edge/opposing-structure checks. |
| 6/12 11:00 mechanical secondary | No secondary confirmation. Pending confirmations require real progress and complete revalidation; stale/wide-risk parents are cleared. |
| 6/12 15:00 wrong short on zone touch | No formal short at 14:59/15:59. A passive long OTE observation appears at 14:59; the 15:59 short candidate is blocked at the wrong edge. A later 17:59 early short is allowed only after a new upper stop-run rejection near active `-OB`. |

## Public alerts in the replay

- 6/09 05:59 — early short near active ICT `-OB`.
- 6/09 13:59 — formal long from lower FVG reaction.
- 6/10 02:59 — formal long after lower reclaim evidence.
- 6/10 17:59 — formal short from FVG rejection context.
- 6/10 19:59 — passive lower `+OB` observation.
- 6/11 11:59 — formal short at high-volume resistance with fresh rejection evidence.
- 6/11 16:59 — passive upper OTE observation.
- 6/12 01:59 — bullish structure shift.
- 6/12 14:59 — passive long OTE pullback observation.
- 6/12 17:59 — early short near `-OB` after new stop-run evidence.
- 6/12 22:59 — bullish structure shift.
- 6/12 23:59 — formal short after a fresh buy-side sweep rejection and volume-proxy stop run near `-OB`.

## Acceptance and remaining work

The reviewed 1H incidents are corrected at their reported timestamps, and the scanner decision path now matches the requested BTC framework. This is suitable for local review and a staged 1H deployment candidate, not proof of trading profitability.

Before any future 15m Telegram pilot, run a separate multi-week real-15m shadow backtest and inspect MFE/MAE, duplicates, contradiction skips and lead time. Until the user explicitly changes scope, 15m stays shadow-only.
