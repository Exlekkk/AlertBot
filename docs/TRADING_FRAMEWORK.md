# TradingDexCat Crypto Trading Framework for AlertBot

## Scope

AlertBot currently focuses on BTC only.  
No stock scanning is required.

## Timeframe hierarchy

- 4H: background, major liquidity, large supply/demand context.
- 1H: main structure and official alert body.
- 15m: entry-location reminder only.

15m does not decide the market direction.  
15m does not rewrite 1H conclusions.

## Main trading idea

BTC trading is driven by liquidity and structure conversion.

Primary signal sources:
- MSB-OB
- OB / MB / BB
- FVG
- liquidity sweep and reclaim/reject
- key round levels
- 1H close behavior

Auxiliary filters:
- RAR
- Inertial Stochastic
- TAI
- MA Ribbon
- MS Trend Matrix

Removed / deprecated:
- MACDSSSEQ
- ABS / EXH / DIV / REJ

## Long logic

Long setups are preferred when:
- price sweeps downside liquidity and quickly reclaims;
- 1H reclaims a key level such as round number / previous low / FVG upper edge;
- pullback holds BU-OB / BU-MB / FVG overlap;
- RAR repairs, Inertial turns up, and TAI does not show obvious participation failure.

Avoid long when:
- price breaks a key level and stays below it;
- bounce into 80k / 80.5k / 80.8k style key levels gets rejected;
- waterfall volume is large and rebound has no participation;
- macro/risk backdrop is still worsening.

## Short logic

Short setups are preferred when:
- price sweeps upside liquidity and fails to hold;
- price falls back into range or loses BE-MB / BE-OB lower edge;
- 1H has volume-backed key-level loss;
- 15m reacts at a key retest with rejection;
- RAR turns down, Inertial rolls over, and TAI is active while price cannot rise.

Avoid chasing short when:
- the first waterfall already hit sell-side liquidity;
- price is sitting at previous low / PDL / major round number;
- 15m rapidly reclaims after downside sweep;
- price is at a 4H demand area without confirmation.

## 15m shadow design

15m only answers this question:

"Is there a possible long/short entry location here that deserves attention?"

It must not answer:

"Is BTC officially bullish/bearish?"

15m allowed titles:
- `📍 BTC 15m 做空预警`
- `📍 BTC 15m 做多预警`

15m must require:
- 1H/4H structure context
- nearby POI / key level / liquidity area
- actual 15m reaction
- no direct conflict from RAR / Inertial / TAI

Invalid standalone triggers:
- FVG alone
- TAI hot/cold alone
- zone touch alone
- single 15m wick without 1H context
