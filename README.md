# AlertBot

AlertBot is a BTCUSDT market-structure alert system. It is designed for TradingDexCat's crypto framework, where BTC is the core risk switch and the main analysis flow is:

**4H background → 1H structure → 15m entry location**

The project is currently BTC-only. Stock scanning is out of scope.

## Current status

Current package version: **v1.3.4-copy-layer-fix**

- Main production alert layer: **1H**
- 15m layer: **shadow backtest only**
- Telegram 15m prealerts: **disabled**
- MACD / ABCX legacy framework: **removed from the main decision path**
- 15m cadence: **adaptive by duplicate/new-information quality, never hard-capped per day**

The 15m layer must never change 1H logic, 1H titles, 1H conclusions, cooldowns, or Telegram copy.

## Strategy model

AlertBot prioritizes liquidity and structure over standalone indicators.

Primary context:
- liquidity sweep and reclaim/reject
- MSB / BOS
- OB / MB / BB zones
- FVG and key round levels
- 1H close behavior around important zones

Auxiliary filters:
- RAR
- Inertial Stochastic
- Trading Activity Index using P20/P40/P60/P80 bands
- MA Ribbon
- MS Trend Matrix

Invalid standalone triggers:
- FVG alone
- TAI hot/cold alone
- zone touch alone
- one 15m wick without 1H/4H context

## Timeframes

### 4H
Higher-timeframe background only. It provides regime context such as range, bullish, or bearish pressure.

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
  RAR, Inertial, TAI, price displacement, and volume filters.

- `engine/msb_ob.py`  
  MSB / OB / MB structure context.

- `engine/liquidity.py`  
  Liquidity sweep and reclaim/reject context.

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
