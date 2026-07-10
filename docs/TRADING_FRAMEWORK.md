# TradingDexCat BTC Framework for AlertBot

## Scope and hierarchy

AlertBot is BTC-only. Stock/equity scanning is out of scope.

- 4H: determine higher-timeframe direction and major location.
- 1H: determine structure and own all official Telegram decisions.
- 15m: find possible entry locations in shadow/log mode only.

15m never changes a 1H direction, title, score, cooldown, pending confirmation or Telegram message.

## Core framework

SMC / ICT is the strategy core:

- liquidity pools, sweeps and reclaim/reject;
- MSS / CHoCH and BOS;
- Fair Value Gap;
- Order Block;
- Breaker Block and polarity change;
- mitigation;
- Premium / Discount and equilibrium;
- PD Array;
- HTF bias;
- OTE;
- Killzones.

No single item above is a standalone trade trigger. Structure, location and a directional catalyst must agree before a formal 1H trial can pass.

## Supplied chart sources and settings

The bot translates decision-relevant calculations from the supplied Pine files. Plotting objects are not copied.

- ICT Concepts [LuxAlgo]
  - Historical mode;
  - market-structure length 6;
  - MSS displayed, BOS hidden;
  - OB swing lookback 14;
  - one visible bullish and bearish OB;
  - full candle wick, not candle body;
  - liquidity margin 5 and two visible boxes;
  - FVG mode with two visible gaps;
  - VI, BPR, NWOG/NDOG, ICT Fibonacci drawings and Killzone shading disabled on the chart.
- MSB-OB: ZigZag 9, breakout factor 0.33.
- Smart Money Fibonacci OTE Engine: pivot 10, OTE 0.618–0.786.
- FVG Volume Profile: custom input 13, 20 bins, gap filter 0.6.
- High Volume Pivot zones: 40 / 40 pivots, volume SMA 20, multiplier 1.2.
- Dual Log Regression Channels: macro 300 / 2.0 and short 50 / 1.5.
- RAR: 15 / 1.0 / close.
- Inertial Stochastic: 10 / 40 / 3 / 3.
- TAI: formation 30, history 350.

BOS and Killzone context may still be calculated internally because they are part of the stated framework. Their disabled TradingView toggles are treated as visual settings, not permission to replace them with unrelated indicators.

## 4H bias

Official 4H bias is weighted from:

- ICT structure direction and recent MSS/BOS;
- MSB-OB structure;
- liquidity sweep/reclaim/reject;
- Fibonacci swing direction and Premium/Discount location;
- Dual Log Regression alignment;
- Dow higher-high/higher-low or lower-high/lower-low structure;
- market-cycle phase.

EMA crosses are not used by the official 4H bias.

## 1H structure and formal trials

The 1H layer uses:

1. market phase;
2. structure and box location;
3. directional evidence;
4. entry quality, invalidation distance and chase checks.

Formal trials require a directional catalyst in addition to a zone reaction. A valid catalyst can be:

- a matching liquidity sweep and reclaim/reject;
- a fresh MSS/BOS or accepted breakout;
- a candle-volume stop-run/acceptance event;
- RAR and Inertial reversal evidence aligned with structure;
- a near ICT OB with aligned structure plus at least one genuine auxiliary turn.

When `+OB` and `-OB` coexist, the market is unresolved. A broad OB is context, not a repeated trigger: the bot watches its first mitigation boundary and keeps the far edge only as invalidation. Same-side formal trials share a 12-bar box cooldown unless genuinely new information appears. Opposite trials require fresh directional information.

Secondary confirmation is a new decision. It must show real progress outside the parent zone and revalidate current structure, risk and chase distance. That verified post-trial push is fresh directional information; a failed parent revalidation cannot immediately create a replacement formal trial on the same candle.

## Fibonacci

The active swing supplies:

- 0.5 equilibrium;
- 0.618, 0.705, 0.786 and 0.79 retracements;
- OTE zone;
- 1.272 and 1.618 continuation targets.

OTE is location evidence, never a standalone entry.

## Volume and order-flow limitation

No footprint, trade-delta or order-book feed was supplied. Therefore:

- `close >= open` volume and `close < open` volume form a candle-direction CVD proxy;
- absorption, fake breakout, stop-run acceptance and continuation are labelled proxies;
- the bot never describes these values as true order flow;
- FVG volume distribution uses available closed 15m candles in shadow mode, or a parent-candle fallback in the official 1H scanner.

The TradingView custom lower-timeframe input is 13 minutes, which Binance does not provide natively. Any 15m substitution remains explicitly labelled.

## Auxiliary filters

RAR, Inertial Stochastic and TAI remain in the framework. They improve timing and confidence but cannot create a trade by themselves.

Inactive legacy decision inputs:

- MACDSSSEQ;
- EMA Ribbon;
- the former EMA-based MS Trend Matrix;
- the former generic fixed-range Volume Profile approximation;
- ABS / EXH / DIV / REJ trigger families.

Legacy modules may remain importable for compatibility, but the BTC scanner does not use them for official decisions.

## 15m shadow layer

15m asks only:

> Is there a possible entry location inside a valid 1H/4H context?

It may log:

- `📍 BTC 15m 做多预警`
- `📍 BTC 15m 做空预警`

It requires a 1H POI, actual 15m reaction and no hard conflict with 4H/1H structure. Duplicate and rapid opposite reminders share adaptive cooldowns. There is no hard daily quota.

Invalid standalone 15m triggers:

- one FVG;
- one wick;
- one TAI hot/cold value;
- one OTE touch;
- one OB or high-volume-zone touch.

Until the user explicitly changes the rule, 15m is shadow-only: no Telegram, no orders and no effect on 1H.
