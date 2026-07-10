# AlertBot

AlertBot is a BTCUSDT market-structure alert system. It is designed for TradingDexCat's crypto framework, where BTC is the core risk switch and the main analysis flow is:

**4H background → 1H structure → 15m entry location**

The project is currently BTC-only. Stock scanning is out of scope.

## Current status

Current package version: **v1.4.0-btc-smc-ict-chart-alignment**

- Main production alert layer: **1H**
- 15m layer: **shadow backtest only**
- Telegram 15m prealerts: **disabled**
- Main decision inputs: **the supplied BTC TradingView Pine framework**
- MACD / ABCX / EMA Ribbon legacy framework: **not used by the scanner decision path**
- 15m cadence: **adaptive by duplicate/new-information quality, never hard-capped per day**
- 1H formal trials use market phase → structure state → weighted evidence → entry-quality validation
- ICT Concepts uses the supplied Pine logic and the user's custom `6 / 14 / 5` settings; `+OB` / `-OB` remain separate from MSB-OB
- RAR, Inertial Stochastic and TAI use the supplied source, including custom TAI `30 / 350`
- Order-flow language is explicitly a closed-candle volume/CVD proxy; it is never labelled true footprint/order-book flow
- Horizontal / accumulation range state suppresses duplicate noise but does not blanket-block a valid early edge trial
- Secondary confirmation revalidates progress, direction, chase distance, risk and current structure instead of trusting the parent alert mechanically

The 15m layer must never change 1H logic, 1H titles, 1H conclusions, cooldowns, or Telegram copy. It remains server-side shadow only in this version.

## Strategy model

AlertBot prioritizes liquidity and structure over standalone indicators.

Primary context:
- liquidity sweep and reclaim/reject
- MSS / CHoCH / BOS
- ICT Order Block, Breaker Block and Mitigation state
- MSB-OB `9 / 0.33` OB / MB / BB zones
- ICT FVG and ChartPrime FVG Volume Profile
- Premium / Discount, PD Array and Killzone context
- 1H close behavior around important zones

Fibonacci and classical context:
- Smart Money Fibonacci OTE anchors and 0.5 equilibrium
- 0.618 / 0.705 / 0.786 / 0.79 retracements
- 1.272 / 1.618 continuation extensions
- Dual Log Regression Channels (`300 / 2.0`, `50 / 1.5`)
- Dow swing structure, volume-price confirmation and market-cycle phase

Volume / order-flow proxy:
- native Binance closed-candle volume
- High Volume Pivot Support & Resistance Zones (`40 / 40 / 20 / 1.2`)
- FVG Volume Profile (`13 / 20 / 0.6` chart settings; available 15m candles are a labelled lower-timeframe proxy)
- candle-direction CVD proxy, stop-run acceptance, fake breakout and absorption proxy


Range / accumulation state:
- detects when price is rotating inside the same accepted value box
- treats simultaneous ICT `+OB` / `-OB` as unresolved box context until one side is accepted
- suppresses repeated lower/upper key-zone observations inside that box
- allows an early edge trial when weighted evidence is asymmetric; no breakout or fixed indicator checklist is required
- blocks rapid opposite formal trials in the same practical box unless fresh structure information appears
- keeps 15m shadow-only; 15m still does not decide 1H direction

Auxiliary filters:
- RAR
- Inertial Stochastic (`10 / 40 / 3 / 3`)
- Trading Activity Index (`30 / 350`) using P20/P40/P60/P80 bands

These filters add timing/confidence evidence. They are not standalone triggers.

Invalid standalone triggers:
- FVG alone
- TAI hot/cold alone
- zone touch alone
- one 15m wick without 1H/4H context

## Timeframes

### 4H
Higher-timeframe bias from SMC/ICT structure, liquidity, Fibonacci swing state, Dow structure and log-regression channels. EMA crosses are not used for the official 4H bias.

### 1H
The official alert body and the main structure engine. This is the primary timeframe for Telegram alerts.

### 15m
Entry-location reminder only. It answers: “Is there a possible long/short entry location worth checking now?”

It does not decide market direction and does not rewrite 1H conclusions.

The bot should not enforce a fixed daily maximum for 15m reminders. Quiet days may produce only a few reminders, while high-volatility days may produce more. The control point is not a daily cap; it is whether each reminder has fresh structure information and is not a duplicate or rapid long/short flip-flop in the same 1H area.


## Alert copy families

1H formal trade alerts use double emoji and full context:
- `📈 BTC 1H 试多观察 📈`
- `📉 BTC 1H 试空观察 📉`
- `📈 BTC 1H 多头确认 📈`
- `📉 BTC 1H 空头确认 📉`

1H secondary confirmation is still formal, but intentionally minimal:
- `✅ BTC 1H 二次确认：承接成立 ✅`
- `✅ BTC 1H 二次确认：承压成立 ✅`

1H non-formal observation alerts use single emoji and only three sections:
- status
- zone
- risk point

Allowed 1H single-emoji observation titles:
- `📍 BTC 1H 关键区观察`
- `📍 BTC 1H 上方关键区观察`
- `📍 BTC 1H 下方关键区观察`

Do not use standalone invalidation Telegram alerts such as bull/bear invalidated. Internal risk-state tracking may still exist, but those titles are not part of the public copy family.

15m prealert copy is also single-emoji and compact, but 15m remains shadow-only until explicitly enabled.

## Important files

- `engine/scanner.py`  
  Main 1H scanner pipeline.

- `engine/prealert_15m.py`  
  Isolated 15m shadow entry-location engine.

- `scripts/backtest_15m_prealert.py`  
  Runs the 15m shadow backtest and writes CSV diagnostics.

- `engine/aux_filters.py`  
  RAR, exact supplied Inertial logic, custom TAI, price displacement, and volume filters.

- `engine/chart_indicators.py`
  Supplied Pine translations for Fibonacci OTE, dual log channels, high-volume pivots, FVG Volume Profile, volume/order-flow proxy, Dow/cycle context and Killzones.

- `engine/framework.py`
  BTC 4H SMC/ICT + classical-theory bias aggregation.

- `engine/ict_ob.py`
  Dedicated ICT MSS/BOS, liquidity, `+OB` / `-OB`, breaker, mitigation, FVG, PD Array and Premium/Discount context.

- `engine/trial_decision.py`
  Market phase, weighted direction evidence, anti-chase/risk checks, and same-box flip control.

- `engine/volume_profile.py`  
  Compatibility adapter backed by FVG Volume Profile and high-volume pivot context. The former generic fixed-range VP is no longer in the live decision path.

- `engine/msb_ob.py`  
  MSB / OB / MB structure context.

- `engine/liquidity.py`  
  Liquidity sweep and reclaim/reject context.

- `scripts/replay_1h_decisions.py`
  Deterministic 1H replay from Binance Vision CSV/ZIP kline archives.

- `docs/V1_4_0_REPLAY_REVIEW.md`
  v1.4.0 BTC framework review for the 2026-06-09 through 2026-06-12 incident window.

- `ALERTBOT_VERSION_CONTEXT.md`  
  Short handoff context for future AI conversations.

- `docs/TRADING_FRAMEWORK.md`  
  Trading framework used by this bot.

- `docs/CHANGELOG_TRADINGDEXCAT.md`  
  Version history and reasoning.

## Test commands

```bash
python -m unittest discover -s tests
python -m compileall -q engine services scripts tests
```

Current v1.4.0 validation: **84 tests pass**.

Run the deterministic 1H incident replay after placing Binance Vision 1H/4H archives in a local data directory:

```bash
python scripts/replay_1h_decisions.py \
  --data-dir /tmp/alertbot-market \
  --start '2026-06-09T00:00:00' \
  --end '2026-06-12T23:59:59' \
  --timezone Asia/Singapore \
  --output reports/v1.4.0_btc_framework_replay_2026-06-09_12.csv
```

Run 15m shadow backtest:

```bash
mkdir -p reports logs

python scripts/backtest_15m_prealert.py \
  --symbol BTCUSDT \
  --days 7 \
  --out reports/15m_prealert_backtest.csv \
  --summary reports/15m_prealert_summary.txt

cat reports/15m_prealert_summary.txt
head -50 reports/15m_prealert_backtest.csv
```

## Deployment notes

The production services are expected to run under systemd:

- `smct-scanner.service`
- `smct-alert.service`
- `smct-webhook.service`

The 15m shadow engine is not connected to Telegram unless explicitly enabled in a later version.

## 15m quality rule

A healthy 15m shadow result is not judged only by signal count. Review:

- whether the reminder came before the 1H confirmation;
- whether long and short both can appear when market structure supports them;
- whether failed signals are explainable from CSV diagnostics;
- whether `duplicate_skips` and `contradiction_skips` remove repeated noise;
- whether high-volatility days are allowed to keep valid new-information reminders.

The 1-4 signals/day range is only a baseline reference for normal markets, not a hard rule.

## Handoff rule for future AI agents

Before changing trading logic, read:

1. `ALERTBOT_VERSION_CONTEXT.md`
2. `docs/TRADING_FRAMEWORK.md`
3. `docs/CHANGELOG_TRADINGDEXCAT.md`
4. `engine/prealert_15m.py`
5. `scripts/backtest_15m_prealert.py`

Preserve the core rule:

**1H is the official alert layer. 15m only reminds the trader of possible entry locations.**
