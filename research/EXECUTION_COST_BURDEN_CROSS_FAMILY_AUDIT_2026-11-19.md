# Cross-family execution-cost burden audit — 19 November 2026

**Status:** completed and independently reproducible accounting audit. This is not a new strategy backtest and no strategy is promoted.

## Purpose and method

This audit separates gross signal quality from the share of initial stop risk consumed by flat round-trip trading costs.

For each split-based family, the representative configuration was selected using development net R at 10 bps only, then carried unchanged into validation. Validation was not used for selection. Both September true-volume-profile variants are included as post-hoc diagnostics, not as validation.

- Stop risk bps = abs(entry - stop) / entry × 10,000.
- Cost R = assumed round-trip cost bps / stop-risk bps.
- Net R = gross R - cost R.
- Costs: 0, 4, 7, 10 and 20 bps round trip.
- Published per-trade net-R fields were independently reconciled where available.

## Results at 10 bps

| Family / configuration | Split | Trades | Gross mean R | Median stop risk (bps) | Median cost (R) | P90 cost (R) | Cost >0.5R | Cost >1R | Net mean R | Net PF |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| BTC 5m CRT-style / close0.25 next-bar-break range | Development | 3,001 | -0.006 | 17.1 | 0.585 | 1.604 | 58.7% | 23.5% | -0.862 | 0.287 |
| BTC 5m CRT-style / close0.25 next-bar-break range | Validation | 659 | +0.012 | 14.2 | 0.703 | 1.886 | 68.3% | 29.4% | -0.937 | 0.278 |
| BTC 1h EMA20/50 / 1.5 ATR / 3R | Development | 106 | +0.105 | 93.3 | 0.107 | 0.210 | 0.0% | 0.0% | -0.018 | 0.950 |
| BTC 1h EMA20/50 / 1.5 ATR / 3R | Validation | 27 | +0.437 | 79.5 | 0.126 | 0.215 | 0.0% | 0.0% | +0.296 | 2.338 |
| BTC 15m Donchian55 / prior-10 stop / 3R | Development | 289 | +0.069 | 121.4 | 0.082 | 0.185 | 0.3% | 0.0% | -0.033 | 0.957 |
| BTC 15m Donchian55 / prior-10 stop / 3R | Validation | 62 | -0.112 | 126.3 | 0.079 | 0.159 | 0.0% | 0.0% | -0.209 | 0.745 |
| BTC 15m RSI(2) / 5-95 / 1h EMA200 / 2 ATR / 2R | Development | 1,001 | -0.003 | 61.1 | 0.164 | 0.319 | 1.8% | 0.0% | -0.192 | 0.752 |
| BTC 15m RSI(2) / 5-95 / 1h EMA200 / 2 ATR / 2R | Validation | 231 | +0.065 | 54.1 | 0.185 | 0.341 | 1.3% | 0.0% | -0.145 | 0.810 |
| BTCUSDT true VP / delta-confirmed | September diagnostic | 20 | +0.032 | 14.8 | 0.677 | 1.012 | 70.0% | 10.0% | -0.699 | 0.440 |
| BTCUSDT true VP / price-only | September diagnostic | 42 | +0.023 | 14.2 | 0.703 | 1.330 | 76.2% | 19.0% | -0.746 | 0.374 |

## Findings

1. The 5m CRT-style and true-VP sweep setups are structurally cost-sensitive. Median stops are only about 14–17 bps; a 10-bps round-trip assumption consumes roughly 0.59–0.70R at the median. Between 58.7% and 76.2% of trades in these rows lose more than 0.5R to assumed costs alone. Their gross mean R is already close to zero, so widening stops is not a justified fix.
2. The 1h EMA crossover and 15m Donchian structural-stop rows have wider risk (median 79–126 bps), so costs consume much less R. Yet development net R remains negative at 10 bps. The EMA validation result is only 27 trades and does not override its negative development result. The development-ranked Donchian configuration is negative in both splits.
3. RSI(2) is not primarily a stop-width problem: development gross mean R is slightly negative and validation gross edge is too small to cover costs.
4. True-VP figures are one-month September diagnostics, not multi-month validation.
5. At 10 bps, cost consumes 0.25R at 40 bps stop risk, 0.5R at 20 bps and 1R at 10 bps. This is an execution-feasibility reference, not a stop-widening rule.

## Research decision

- Do not widen stops or retune rejected strategies based on this audit.
- Future reports must include median and lower-decile stop-risk bps, median/P90 cost_R, and the share of trades where costs exceed 0.25R, 0.5R and 1R.
- The 1h EMA20/50 crossover is the only selected row with positive gross mean in both development and validation, but it fails the 10-bps development net gate and has only 27 validation trades. It remains a research lead, not a candidate.
- Next confirmatory step: freeze that exact EMA20/50, 1.5 ATR, 3R, no-4h-filter rule for a Binance BTCUSDT cross-exchange replication. This is venue-robustness evidence, not independent temporal OOS, because the historical dates overlap the Delta study. Keep post-19-Nov data untouched for prospective confirmation.

## Verification and limitations

- Five original research ZIPs, their SHA-256 manifest, the audit script and outputs are included in the downloadable reproducibility package.
- The audit generated 50 family/configuration/split/cost rows. A clean second execution reproduced the CSV and JSON outputs byte-for-byte.
- Published 10-bps net-R parity checks for EMA, Donchian, RSI(2) and true-VP trades were below 9e-16 maximum absolute difference. CRT was recomputed from its trade ledger and matched its published summary to rounding.
- Costs are flat assumptions, not the user's verified fee tier. Maker/taker asymmetry, spread, queue position, slippage, impact and funding cashflows are not modeled.
- The families differ in venue, timeframe and period; this compares cost burden, not strategy performance rankings. Support/resistance was excluded because its development-ranked row had only 14 trades, while its larger validation-ranked row would introduce validation-selection bias.

**Decision: no validated BTC intraday strategy.** This audit supports a shift toward cost-aware, lower-turnover research, but does not establish profitability.
