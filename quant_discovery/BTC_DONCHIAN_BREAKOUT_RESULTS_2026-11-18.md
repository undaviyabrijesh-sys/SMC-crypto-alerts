# BTC Donchian breakout baseline — results (2026-11-18)

## Scope and data integrity

- Instrument: Delta BTCUSD perpetual.
- Source: archived 5-minute OHLCV, 210,239 rows, 2024-11-16 11:30 UTC through 2026-11-16 11:20 UTC.
- Aggregated 70,079 complete UTC-aligned 15-minute bars, 2024-11-16 11:30 UTC through 2026-11-16 11:00 UTC.
- Source SHA-256: 5b612e1c496f16277b459f58ddff33b69d8f7912b70d8f733f0a17be844eb4fb.
- Source 5-minute gaps: 0; invalid OHLC rows: 0; invalid volume rows: 0.
- 15-minute gaps: 0; one incomplete final 15-minute bucket was dropped.

Chronological row-aligned partitions:
- Development: 2024-11-16 11:30 UTC to 2026-04-11 11:15 UTC.
- Validation: 2026-04-11 11:15 UTC to 2026-07-29 23:15 UTC.
- Final 15% OOS begins 2026-07-29 23:15 UTC and was not evaluated.

## Frozen rules

- 15-minute close crosses the prior 20- or 55-bar Donchian high/low; channel shifted one bar.
- Entry at next 15-minute open.
- Stops: 10-bar opposite extreme or 1.5 x Wilder ATR(14).
- Targets: 2R or 3R.
- Optional latest completed 1-hour close versus EMA50 direction filter.
- One position at a time per configuration; seven-day maximum hold.
- Stop-first on ambiguous candles; adverse stop gaps fill at open; target gaps capped at target.
- Round-trip cost sensitivities: 4, 7, 10 and 20 bps.
- Net R = gross R minus round-trip cost divided by initial stop-risk bps.

## Primary results at 10 bps round-trip cost

All 16 configurations were tested in development and validation. No configuration passed the frozen gate.

| Configuration | Split | Trades | Win % | PF | Net R | Max DD | Max losing streak | Positive months |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| DC20 / prior10 / 2R / no filter | Dev | 429 | 35.43 | 0.904 | -29.47 | -42.51R | 11 | 6/18 |
| DC20 / prior10 / 2R / no filter | Val | 104 | 29.81 | 0.662 | -27.89 | -32.10R | 14 | 0/4 |
| DC20 / ATR1.5 / 2R / no filter | Dev | 1,803 | 32.78 | 0.674 | -498.33 | -500.00R | 13 | 1/18 |
| DC20 / ATR1.5 / 2R / no filter | Val | 375 | 30.93 | 0.608 | -128.50 | -130.88R | 16 | 0/4 |
| DC55 / prior10 / 2R / no filter | Dev | 368 | 36.14 | 0.950 | -12.89 | -30.09R | 15 | 7/18 |
| DC55 / prior10 / 2R / no filter | Val | 78 | 39.74 | 1.093 | +4.87 | -14.33R | 7 | 3/4 |
| DC55 / prior10 / 2R / EMA50 filter | Dev | 353 | 35.69 | 0.950 | -12.30 | -33.11R | 13 | 7/18 |
| DC55 / prior10 / 2R / EMA50 filter | Val | 65 | 33.85 | 0.842 | -7.50 | -10.18R | 7 | 0/4 |
| DC55 / prior10 / 3R / no filter | Dev | 289 | 29.07 | 0.957 | -9.44 | -28.49R | 12 | 8/18 |
| DC55 / prior10 / 3R / no filter | Val | 62 | 22.58 | 0.745 | -12.94 | -14.42R | 7 | 1/4 |
| DC55 / ATR1.5 / 2R / no filter | Dev | 1,134 | 31.31 | 0.640 | -348.57 | -349.72R | 16 | 0/18 |
| DC55 / ATR1.5 / 2R / no filter | Val | 225 | 33.33 | 0.695 | -57.36 | -68.70R | 8 | 1/4 |

The remaining configurations and all 4/7/10/20 bps results are in the complete research artifact.

## Near-candidate diagnostic — not promoted

The strongest validation row at 10 bps was DC55 / prior10 / 2R / no filter: 78 trades, 39.74% net win rate, PF 1.093 and +4.87R. It failed development with 368 trades, PF 0.950 and -12.89R. It also missed the required PF > 1.10 in validation.

| Round-trip cost | Development PF / net R | Validation PF / net R |
|---:|---:|---:|
| 4 bps | 1.037 / +9.12R | 1.201 / +9.89R |
| 7 bps | 0.992 / -1.88R | 1.145 / +7.38R |
| 10 bps | 0.950 / -12.89R | 1.093 / +4.87R |
| 20 bps | 0.823 / -49.56R | 0.939 / -3.51R |

This result is cost-sensitive and not stable across chronological partitions. Direction/regime attribution changes between development and validation; no long-only, short-only or regime subset is promoted.

## Decision

**Reject this Donchian breakout definition as tested.** No configuration met the predeclared trade-count, PF, net-R and monthly-stability gates. The final 15% OOS was not opened.

## Validation and reproducibility

- Five deterministic checks passed: shifted channel, stop-first ambiguity, adverse stop gap, capped target gap and cost-to-R arithmetic.
- Eight independent trade-ledger checks passed: next-bar entry, cost identity, positive initial risk, exit ordering, no overlapping positions, summary reconciliation, lifecycle containment and OOS isolation.
- The complete package was extracted and rerun from its included source CSV; all 128 summary rows reproduced exactly (maximum numeric difference 0.0).
- The full tested implementation and all trade/month/regime CSVs are in the research ZIP. A compact copy of the implementation has been committed to this branch; it has not been separately executed by GitHub Actions.

## Limitations

Funding was not modeled because historical Delta BTCUSD funding cashflows were not present in the source archive. Spread, slippage and market impact are not separately modeled; flat round-trip cost sensitivities are used. Results are pre-funding and do not support promotion or live use.

## Next experiment

The next frozen candidate is BTC 15-minute RSI(2) short-term mean reversion with optional completed-1H EMA200 regime filter, ATR stops, 1.5R/2R targets and a 24-hour maximum hold. Its preregistration is in research/BTC_RSI2_MEAN_REVERSION_PREREGISTRATION_2026-11-18.md.
