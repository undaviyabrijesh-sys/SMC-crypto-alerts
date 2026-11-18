# BTC 1H EMA crossover continuation — completed, no configuration passed

**Research date:** 2026-11-18  
**Instrument:** Delta Exchange India BTCUSD perpetual  
**Status:** Exploratory; no OOS evaluation; no production promotion.

## Decision

The 1H EMA crossover is a distinct entry family from the previously tested EMA pullback/reclaim and EMA51 candle-break systems. The frozen 24-configuration matrix produced no configuration with positive net R and PF >1.10 in both development and validation at the primary 10 bps round-trip cost.

The 20/50 crossover produced a positive validation diagnostic but negative development performance. It is not a candidate and must not be tuned against this validation partition. The 9/21 crossover was consistently weak; the 50/200 crossover was too sparse to qualify.

## Data and partitions

| Item | Result |
|---|---:|
| Delta BTCUSD 5m source rows | 210,239 |
| Source coverage | 2024-11-16 11:30 to 2026-11-16 11:20 UTC |
| 5m gaps / invalid OHLC | 0 / 0 |
| Complete 1h bars in full archive | 17,519 |
| Complete 4h bars | 4,379 |
| Post-transition evaluation bars | 10,356 |
| Evaluation start | 2025-09-08 12:00 UTC |
| Evaluation end exclusive | 2026-11-14 00:00 UTC |
| Development / validation / reserved OOS rows | 7,249 / 1,553 / 1,554 |
| Configurations | 24 |
| Summary rows across 4 costs × 2 splits | 192 |
| Trade records at 10 bps | 2,908 |

Source SHA-256: \`5b612e1c496f16277b459f58ddff33b69d8f7912b70d8f733f0a17be844eb4fb\`  
Funding archive SHA-256: \`e38d6e4eb3140c81e7a1108b096cd42d5829f50663d64275ac10344767a52dab\`

Only the post-2025-09-08 funding mechanism period was evaluated. Funding snapshots are at 00:00, 08:00 and 16:00 UTC. Positions were exited at a 1h close strictly before the next settlement; no position was open at a settlement timestamp. Five 5-hour gaps exist in the post-transition hourly funding observation series, but all 1,295 expected settlement observations in the archive window were present. The final incomplete block was excluded.

## Primary results — 10 bps round-trip cost

The strongest development row and strongest validation row were the same diagnostic configuration: EMA20/50, 1.5 ATR stop, 3R target, no 4h filter.

| Metric | Development | Validation |
|---|---:|---:|
| Trades | 106 | 27 |
| Win rate (net R > 0) | 41.51% | 62.96% |
| Profit factor | 0.950 | 2.338 |
| Net R | **-1.90R** | **+7.99R** |
| Average net R / trade | -0.018R | +0.296R |
| Maximum drawdown | -11.32R | -2.76R |
| Maximum losing streak | 9 | 5 |
| Positive active months | 6/11 (54.5%) | 2/3 (66.7%) |
| TP / SL / TIME exits | 3 / 22 / 81 | 1 / 2 / 24 |
| Long / short trades | 55 / 51 | 13 / 14 |

The validation headline is based on only 27 trades across three active months and is not corroborated by development. Most exits were time exits, not target hits. The 4h EMA200 filter reduced this configuration to 50 development and 13 validation trades; development remained negative (-2.43R, PF 0.872).

### Cost sensitivity for the same 20/50 diagnostic

| Round-trip cost | Development net R | Validation net R |
|---:|---:|---:|
| 4 bps | +5.94R | +10.27R |
| 7 bps | +2.02R | +9.13R |
| 10 bps | -1.90R | +7.99R |
| 20 bps | -14.96R | +4.18R |

Development break-even cost for this row is approximately 8.55 bps. This is cost-sensitive: at the 10 bps primary assumption the development result is negative. A 4 bps maker/maker assumption is not a reliable proxy for next-open entries and stop exits.

### Other EMA pairs

- EMA9/21: development 243–257 trades per configuration, PF roughly 0.54–0.62 and negative net R; validation 22–54 trades, also negative net R.
- EMA50/200: only 38 development / 10 validation trades without the 4h filter, and 16 / 8 with it; all configurations were negative at 10 bps and underpowered.
- Across all 24 configurations, **0/24** passed the joint development/validation gate. No OOS trades were generated.

## Stability and interpretation

For the strongest 20/50 diagnostic, development monthly net R alternated: positive in 6 of 11 active months, negative in 5. Validation was positive in July and September 2026 but negative in August. The apparent validation edge is concentrated in a short, small sample and did not persist in development. Regime attribution also shifted: development bear regime was negative at 10 bps while bull was slightly positive; validation both bull and bear were positive, but the bear sample was only eight trades. These are descriptive diagnostics, not post-hoc filters.

## Audit and reproducibility

- 10 deterministic test groups passed: complete 1h aggregation, dropped incomplete bars, 1h/4h future-perturbation invariance, stop-first ambiguity, adverse stop gaps, favourable target gap caps and settlement clock.
- Independent audit recalculated 1,344 fields (trade count, net win rate, PF, net R, max drawdown, losing streak and positive-month fraction) across all 192 summary rows; **zero differences**.
- 2,908 trade rows; no overlapping positions; no funding-boundary violations; no OOS rows; no split-boundary trades.
- Local replay was executed from the packaged source and funding CSVs. This was not a GitHub Actions run.

## Limitations

Funding cashflow is not applied; the test avoids settlement exposure but does not resolve raw rate units or rate-to-settlement mapping. Flat 4/7/10/20 bps costs are assumptions; no separate spread/slippage/market-impact model or account-specific fee tier. One-hour OHLC execution resolves ambiguous bars stop-first. Net R is not account return; no fixed capital/risk sizing assumption is imposed.

## Decision and next step

**Reject this 1H EMA crossover family under the tested rules.** Do not select the positive validation row, tune its stop/target or filter on the inspected validation period, or inspect OOS. The next research step is to move to an independent source of information (trade-level aggressor-side data if obtainable) rather than another EMA parameter variation. No production rules, live alerts or exchange orders changed.
