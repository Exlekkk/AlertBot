# v1.3.9 Layered Trial Decision Replay Review

## Scope

- Review window: 2026-06-09 00:00 through 2026-06-12 23:59, Asia/Singapore.
- Market data: Binance Vision USD-M BTCUSDT 1H and 4H closed candles.
- Comparison baseline: commit `3899c6980058139ae625374ba68b318214f87d02` (`v1.3.8-range-lock-noise-control`).
- Candidate: `v1.3.9-layered-trial-decision`.

This is a deterministic decision replay, not a profitability backtest. It checks timing, direction, box-state handling, late-entry suppression, and secondary-confirmation behavior.

## Important data limitation

Binance candles do not contain the native objects drawn by `ICT Concepts [LuxAlgo]`.

- v1.3.9 has a dedicated exact-field interface for active ICT `+OB` and `-OB` zones.
- The historical replay uses the separately labelled `price_proxy` fallback because no TradingView ICT payload was available for these candles.
- Proxy output must not be described as an exact LuxAlgo match.

## Result

| Metric | v1.3.8 | v1.3.9 |
|---|---:|---:|
| Formal trial / secondary-confirm alerts | 8 | 4 |
| 6/9 late short near the completed selloff | sent | blocked |
| 6/11 07:00 short into active lower support context | sent | blocked |
| 6/12 10:00 late long at the upper side of the reference box | sent | blocked |
| 6/12 11:00 mechanical second confirmation | sent | blocked because no valid parent trial remains |
| 6/12 15:00 short from the lower side of an unresolved box | sent | blocked |

The candidate does not use a blanket range prohibition:

- an edge trial may still pass before a breakout when weighted structure, location, reaction and auxiliary evidence are asymmetric;
- an opposite formal trial in the same practical box needs fresh structure information such as a valid sweep/reclaim-reject or accepted breakout;
- RAR, Inertial and TAI remain weighted evidence, not mandatory simultaneous switches.

## Timing changes seen in replay

- The long using the `61490.0 - 61563.3` area appears around 2026-06-10 02:59 instead of the later v1.3.8 occurrence around 06:59.
- The 2026-06-11 repair long appears around 08:59 instead of the v1.3.8 occurrence around 09:59.

Replay timestamps are candle close times. Telegram timestamps can differ by scanner scheduling and display timezone.

## Artifact

The full hourly candidate output is stored in:

- `reports/v1.3.9_replay_2026-06-09_12.csv`

It includes market phase, box position, range-lock state, ICT source/exactness, trial/opposite scores, chase distance, risk distance, reward/risk proxy, selected zone, and suppression reason.
