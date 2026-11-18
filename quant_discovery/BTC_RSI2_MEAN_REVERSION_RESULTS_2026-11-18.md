# BTC 15m RSI(2) extreme-entry mean-reversion — completed, rejected

**Research date:** 2026-11-18  
**Branch:** ai-quant-rebuild  
**Status:** Experimental result; no configuration passed the frozen development/validation gate. The final 15% was not simulated.

## Executive decision

The preregistered 16-configuration BTC RSI(2) study is negative at the primary 10 bps assumed round-trip cost. Every development and validation configuration had negative net R at 10 bps. No row passed even the individual 10 bps gates, and no configuration passed both development and validation. Development remained negative for every configuration even at the optimistic 4 bps cost assumption.

One validation-only configuration showed +5.46R at 4 bps, but its matching development result was -204.29R, its validation PF was only 1.018, and it was positive in only one of four active validation months. It is not a candidate. **Reject this exact RSI(2) extreme-entry definition; do not inspect or tune the final 15%.**

This is related to, but not identical to, the previously rejected 5-minute RSI extreme-crossback system. The current study enters while RSI(2) is at an extreme on 15-minute bars; the earlier study waited for RSI to cross back out of an extreme on 5-minute bars. These are related tests within the broader RSI mean-reversion family, not independent evidence from unrelated strategy families.

## Frozen rules tested

- Signal timeframe: complete UTC-aligned 15-minute bars built from exactly three contiguous 5-minute source bars.
- Indicator: Wilder RSI(2), seeded with the simple average of the first two gains/losses, then Wilder-smoothed.
- Long signal: RSI(2) <= 5 or <= 10. Short signal: RSI(2) >= 95 or >= 90.
- Higher-timeframe filter: off, or require the latest fully completed 1-hour close above its 1-hour EMA200 for longs and below EMA200 for shorts. Only complete 1-hour bars containing four 15-minute bars are used.
- Entry: next 15-minute open after the signal close.
- Stop: 1.5x or 2.0x Wilder ATR(14), measured at the signal close and applied from entry.
- Target: 1.5R or 2R.
- Positioning: one open position per exact configuration; both directions; no extra post-exit cooldown; no overlapping positions.
- Maximum holding period: 96 15-minute bars (24 hours), then exit at the final bar close.
- Execution: same-bar stop/target ambiguity resolves stop-first; adverse stop gaps fill at the bar open; favourable target gaps are capped at target.
- Costs: 4/7/10/20 bps round trip, deducted as cost_bps / initial_stop_risk_bps from gross R.
- Matrix: 2 RSI thresholds x 2 EMA200 filter states x 2 stop multipliers x 2 targets = 16 configurations.

## Data and partitions

The existing archived Delta Exchange India BTCUSD perpetual 5-minute source from the preceding Donchian research package was reused; it was not downloaded again during this run.

| Data check | Result |
|---|---:|
| Source 5-minute rows | 210,239 |
| 5-minute coverage | 2024-11-16 11:30 UTC to 2026-11-16 11:20 UTC |
| 5-minute gaps | 0 |
| Zero-volume 5-minute bars | 334 |
| Invalid OHLC / volume rows | 0 / 0 |
| Complete 15-minute bars | 70,079 |
| Incomplete 15-minute buckets dropped | 1 (partial final bucket) |
| 15-minute gaps | 0 |
| Complete 1-hour bars | 17,519 |
| Raw source SHA-256 | 5b612e1c496f16277b459f58ddff33b69d8f7912b70d8f733f0a17be844eb4fb |
| Derived 15-minute SHA-256 | 5cc5a38e08b4299102680089ff90ec8237dcac8d0b96d2dbe4cac61b205f1a09 |

Chronological 70/15/15 partitions by 15-minute row position:

| Partition | Start | End (exclusive) | Rows |
|---|---|---|---:|
| Development | 2024-11-16 11:30 UTC | 2026-04-11 11:15 UTC | 49,055 |
| Validation | 2026-04-11 11:15 UTC | 2026-07-29 23:15 UTC | 10,512 |
| Final OOS | 2026-07-29 23:15 UTC | 2026-11-16 11:15 UTC | 10,512 |

The final OOS partition was not simulated. Each development/validation trade reserved the full 24-hour maximum holding horizon within its own partition.

## Primary results — 10 bps assumed round-trip cost

The strongest development and validation diagnostic by net R at 10 bps was the same configuration: RSI(2) <=5 / >=95, completed-1H EMA200 filter enabled, 2.0 ATR stop and 2R target. This is a descriptive leaderboard row, not a selected candidate.

| Metric | Development | Validation |
|---|---:|---:|
| Trades | 1,001 | 231 |
| Net win rate | 34.27% | 36.80% |
| Profit factor | 0.752 | 0.810 |
| Net R | **-192.02R** | **-33.52R** |
| Average net R / trade | -0.192R | -0.145R |
| Median net R / trade | -1.114R | -1.139R |
| Maximum drawdown (initial equity baseline 0R) | -198.57R | -39.47R |
| Maximum losing streak | 11 | 7 |
| Positive active months | 2 / 18 | 1 / 4 |
| Long / short trades | 512 / 489 | 123 / 108 |

Both directions were negative in both partitions. Development long trades contributed -116.25R and shorts -75.78R. Validation longs contributed -21.40R and shorts -12.12R. No post-hoc direction selection is justified.

Monthly net R for this same configuration:
- Development positive months: February 2025 (+7.94R) and November 2025 (+2.53R); the other 16 active months were negative.
- Validation: April -7.45R, May -2.30R, June +1.48R, July -25.24R.

The 10 bps trade-ledger exit counts for the same configuration were development: 645 stop, 1 ambiguous stop-first, 0 stop gaps, 311 targets and 44 time exits; validation: 141 stops, 0 ambiguous, 1 stop gap, 78 targets and 11 time exits.

## Cost sensitivity

For the same RSI<=5 / >=95, EMA200-filtered, 2 ATR / 2R configuration:

| Round-trip cost | Development net R | Validation net R |
|---:|---:|---:|
| 4 bps | -78.76R | -4.37R |
| 7 bps | -135.39R | -18.94R |
| 10 bps | -192.02R | -33.52R |
| 20 bps | -380.79R | -82.09R |

Across the entire 16-configuration matrix, the best development net R at each cost was still negative: -62.87R at 4 bps, -135.39R at 7 bps, -192.02R at 10 bps and -380.79R at 20 bps.

The best validation-only result at 4 bps was a different configuration (RSI<=10/>=90, EMA200 filter, 1.5 ATR stop, 1.5R target): 504 trades, 45.04% net win rate, PF 1.018, +5.46R, max DD -18.35R, losing streak 9 and 1/4 positive months. Its matching development result was 2,196 trades, PF 0.858, -204.29R, max DD -215.79R, losing streak 18 and 3/18 positive months. At 7/10/20 bps that validation row was -36.36R / -78.18R / -217.59R. It fails the development, PF and monthly stability requirements and is rejected.

Median initial stop risk across all trades was 52.20 bps in development and 45.82 bps in validation. A 10 bps round-trip assumption therefore consumes a meaningful fraction of initial risk, but the strategy was already negative in development at 4 bps.

## Promotion gate and audit

Frozen gate at 10 bps: at least 100 development and 30 validation trades; PF >1.10 and net R >0 in both; at least 55% positive active months in both.

- 16 configurations tested; 32 development/validation primary rows.
- 0/32 rows passed all individual gates.
- 0/16 configurations passed both development and validation.
- OOS simulations: 0.
- 128 summary rows across 16 configurations x 2 partitions x 4 cost assumptions.
- 39,941 trade records across the 16 independently simulated configurations and two partitions at 10 bps. This is not 39,941 unique market signals; the same market events can appear in multiple configuration ledgers.
- Eleven deterministic tests passed: RSI seed/edge cases, ATR seed, chronological splits, stop-first ambiguity, adverse stop gap, favourable target gap cap, 24-hour time exit, complete 1-hour aggregation and future-data perturbation invariance.
- Independent trade-ledger audit recomputed all 128 cost/split/config summary rows; maximum numeric difference was 0.0.
- 32 configuration/partition groups passed the no-overlap audit; no OOS trade rows were present.
- A second clean local replay reproduced summary, monthly and regime outputs exactly (maximum numeric difference 0.0).

## Limitations

- Historical Delta funding cashflows are not in the source archive. Funding is not modelled; all results are pre-funding despite the 24-hour maximum holding period.
- The 4/7/10/20 bps figures are flat assumed round-trip costs, not verified account-specific fees. Spread, slippage and market impact are not separately modelled.
- R is normalized by each trade's initial stop risk; it is not account return or compounded portfolio PnL.
- 1-hour EMA200 is a mechanical filter, not a full market-structure regime model.
- The data is a reused archive ending 2026-11-16 11:20 UTC, not a newly refreshed feed.
- This is a 15-minute extreme-entry variant within the broader RSI mean-reversion family. It is not independent confirmation of a new unrelated edge.

## Decision and next step

Reject the tested RSI(2) extreme-entry definition. Do not tune this inspected development/validation matrix and do not evaluate its final 15% after failing the gate. Preserve the prior 5-minute RSI crossback and RSI-divergence results as separate historical experiments; do not conflate them with this one.

Next research should move away from another RSI threshold/entry variation. First audit the remaining ledger for an untested, independent source of edge and require a frozen hypothesis plus a data-quality plan. If genuine trade-level price/quantity/aggressor-side data becomes available, prioritize true order-flow reconstruction; otherwise select a price-only family not already exhausted by the existing CRT/SMC/EMA/Supertrend/Donchian/VP/TPO/RSI experiments.
