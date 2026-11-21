# BTC/ETH funding sentiment and public-fee audit — 2026-11-16

## Decision

**Reject the tested funding-sentiment long signals.** Negative funding did not produce positive absolute returns after the public base taker fee. BTC had zero negative-funding events in validation; ETH had only 17 and lost at both horizons. The secondary below-neutral diagnostic also lost at the 10 bps primary cost. No OOS returns were computed.

This is an exploratory forward-return event study, not a stop-defined trading system. PF and drawdown are descriptive event-sequence statistics; R and account-equity drawdown are not applicable.

## Public fee anchor

The current public Delta BTC product API reports maker commission 0.02% and taker commission 0.05% per side. Delta's ETH contract page shows the same headline rates. Delta's fee explanation notes rates may vary by product and user volume/tier.

- BTC product API: https://api.india.delta.exchange/v2/products/BTCUSD
- ETH contract fees: https://www.delta.exchange/futures-guide-ethereum
- Fee calculation and tier caveat: https://www.delta.exchange/support/solutions?articleId=80001177869

Round-trip assumptions: 4 bps maker/maker (optimistic), 7 bps maker/taker, 10 bps taker/taker (primary public base assumption), and 20 bps stress. These are not an authenticated fee quote for the user's account.

## Data

| Dataset | Rows | Coverage | Gaps | SHA-256 |
|---|---:|---|---:|---|
| BTC traded price 15m | 70,127 | 2024-11-15 07:30 to 2026-11-15 19:00 UTC | 0 | d8f210d91553ea43d1ccb0b27bb4d750013e9485c4b007f80647982d1978849a |
| ETH traded price 15m | 70,127 | 2024-11-15 07:30 to 2026-11-15 19:00 UTC | 0 | f58ce4233c5d7242974e460d811198c03614e113c6097805884ac580ebd8b95a |
| BTC funding 1h | 17,531 | 2024-11-14 16:00 to 2026-11-15 02:00 UTC | 0 | 853950ee9193d6e6c0b9ab242fe47c74313d41cbcd9a38cb6255c3d10ed58296 |
| ETH funding 1h | 17,531 | 2024-11-14 16:00 to 2026-11-15 02:00 UTC | 0 | 51eb3ca015985dbfc68891c732f45abee6fa54d32b4085aebf915ec2580aeec8 |

Only post-transition blocks were used: 1,297 common 8-hour settlement blocks from 2025-09-09 00:00 UTC. Chronological split: 70% development, 15% validation, final 15% untouched. Development ends at 2026-07-08 08:00 UTC; validation ends at 2026-09-11 08:00 UTC. OOS was not evaluated.

## Frozen event definitions

1. At each 00:00/08:00/16:00 UTC block, use the raw 1h funding candle only after one full hour has elapsed. Entry is the next 15m open at boundary +1h.
2. Primary: rate_raw < 0.0 means contrarian long; controls have rate_raw >= 0.0.
3. Secondary diagnostic: rate_raw < 0.01 means long; controls have rate_raw >= 0.01. Delta documents 0.01% per 8h as the current interest-rate baseline; this is diagnostic only.
4. Measure 1h and 4h forward returns. The 4h exit is at boundary +5h, before the next 8h settlement at boundary +8h. No funding cashflow is applied.
5. Latest completed 4h EMA50/EMA200 regime is used only for matching, not as a trade filter.
6. Match without replacement by asset, UTC weekday, settlement slot and completed 4h regime; nearest non-event control within 35 days. Exclude controls within 8h of any event.

## Results at 10 bps round-trip cost

| Signal | Asset | Sample | Events / matched | Horizon | Win % | PF* | Mean net bps | Event-seq DD bps | Max loss streak | Positive months |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Negative funding → long | BTC | Dev | 65 / 47 | 1h | 30.77 | 0.687 | -5.44 | -704.28 | 10 | 1/5 |
| Negative funding → long | BTC | Dev | 65 / 47 | 4h | 40.00 | 0.766 | -6.33 | -694.04 | 7 | 1/5 |
| Negative funding → long | BTC | Val | 0 / 0 | 1h/4h | — | — | — | — | — | — |
| Negative funding → long | ETH | Dev | 94 / 82 | 1h | 38.30 | 0.906 | -2.31 | -600.59 | 8 | 2/4 |
| Negative funding → long | ETH | Dev | 94 / 82 | 4h | 42.55 | 0.962 | -1.47 | -1,127.62 | 7 | 2/4 |
| Negative funding → long | ETH | Val | 17 / 16 | 1h | 29.41 | 0.552 | -11.00 | -281.16 | 8 | 1/3 |
| Negative funding → long | ETH | Val | 17 / 16 | 4h | 52.94 | 0.678 | -8.05 | -248.11 | 3 | 1/3 |
| Below 0.01% → long | BTC | Dev | 320 / 179 | 1h | 37.81 | 0.546 | -9.86 | -3,174.04 | 11 | 1/10 |
| Below 0.01% → long | BTC | Dev | 320 / 179 | 4h | 46.88 | 0.800 | -6.59 | -2,448.32 | 9 | 3/10 |
| Below 0.01% → long | BTC | Val | 13 / 12 | 1h | 30.77 | 0.172 | -15.46 | -200.97 | 4 | 1/3 |
| Below 0.01% → long | BTC | Val | 13 / 12 | 4h | 30.77 | 0.153 | -26.68 | -346.89 | 4 | 0/3 |
| Below 0.01% → long | ETH | Dev | 270 / 74 | 1h | 41.85 | 0.786 | -5.08 | -2,552.87 | 11 | 2/8 |
| Below 0.01% → long | ETH | Dev | 270 / 74 | 4h | 42.96 | 0.844 | -6.29 | -2,606.59 | 8 | 3/8 |
| Below 0.01% → long | ETH | Val | 176 / 19 | 1h | 35.80 | 0.552 | -9.24 | -1,799.64 | 12 | 0/3 |
| Below 0.01% → long | ETH | Val | 176 / 19 | 4h | 46.59 | 0.854 | -4.25 | -1,291.22 | 7 | 1/3 |

*PF and drawdown are descriptive on fixed-horizon event returns, not an executable stop-defined portfolio.

### Matched-control lift

For the primary negative-funding definition, day-cluster 95% CIs for paired lift all crossed zero:

| Asset/sample | Horizon | Pairs | Mean gross lift | 95% CI |
|---|---|---:|---:|---:|
| BTC Dev | 1h | 47 | +4.42 bps | [-12.34, +24.63] |
| BTC Dev | 4h | 47 | -2.41 bps | [-25.39, +21.67] |
| ETH Dev | 1h | 82 | +19.32 bps | [-3.08, +42.91] |
| ETH Dev | 4h | 82 | +4.12 bps | [-30.61, +35.73] |
| ETH Val | 1h | 16 | -22.62 bps | [-53.23, +3.92] |
| ETH Val | 4h | 16 | -21.08 bps | [-57.56, +18.96] |

The below-baseline diagnostic had some positive development lifts, but absolute returns remained negative. Validation matching was weak (BTC 12 pairs; ETH 19 pairs, too few distinct event dates for a day-cluster interval).

### Negative-funding cost sensitivity: mean net bps

| Asset/sample | Horizon | 4 bps | 7 bps | 10 bps | 20 bps |
|---|---|---:|---:|---:|---:|
| BTC Dev | 1h | +0.56 | -2.44 | -5.44 | -15.44 |
| BTC Dev | 4h | -0.33 | -3.33 | -6.33 | -16.33 |
| ETH Dev | 1h | +3.69 | +0.69 | -2.31 | -12.31 |
| ETH Dev | 4h | +4.53 | +1.53 | -1.47 | -11.47 |
| ETH Val | 1h | -5.00 | -8.00 | -11.00 | -21.00 |
| ETH Val | 4h | -2.05 | -5.05 | -8.05 | -18.05 |

## PDRT public-fee recalculation

The prior-day range break/retest trade ledgers were recalculated with fee on entry notional plus fee on exit notional. Entries, stops, targets and outcomes were unchanged.

| Target | Sample | Fee model | Trades | PF | Net R | Max DD R |
|---:|---|---|---:|---:|---:|---:|
| 3R | Dev | Maker/maker 4 bps | 207 | 0.695 | -59.85R | -63.08R |
| 3R | Dev | Maker/taker 7 bps | 207 | 0.537 | -106.17R | -108.83R |
| 3R | Dev | Taker/taker 10 bps | 207 | 0.418 | -152.50R | -155.01R |
| 3R | Val | Maker/maker 4 bps | 43 | 1.175 | +6.23R | -7.60R |
| 3R | Val | Maker/taker 7 bps | 43 | 0.885 | -4.84R | -15.55R |
| 3R | Val | Taker/taker 10 bps | 43 | 0.672 | -15.92R | -23.51R |

The apparent 3R validation gain exists only at the optimistic maker/maker rate and is paired with -59.85R development. At 7 bps, validation is already -4.84R; at 10 bps it is -15.92R. All 1.5R/2R/3R development variants lose even at 4 bps. The PDRT rejection is therefore robust to the public base taker fee.

## Decision and next step

- Negative funding → long: **reject as tested**. BTC has no validation events; ETH validation is small and negative at 10 bps.
- Below 0.01% baseline → long: **reject as tested**. Absolute expectancy is negative; event frequency changes sharply across asset and sample.
- PDRT: **rejection confirmed** under public base taker fees.
- Do not tune thresholds or inspect OOS. Next candidate: preregister a lower-turnover, wider-structural-risk BTC setup—previous-week range sweep/reclaim on 1h with 15m confirmation and an 8h cap. This candidate has **not** been tested.

## Limitations

- Historical rate-to-settlement timestamp mapping is not fully reconciled. Funding is used only as a one-hour-lagged sentiment feature, never as cashflow.
- No stop/target; R and executable account drawdown are not applicable.
- Flat fee assumptions omit spread, impact and fill uncertainty; actual account tier is unavailable.
- Matched controls are observational, not causal.
- OOS was not evaluated.

## Reproduction

- Event study: research/btc_eth_funding_sentiment_event_study.py
- PDRT fee recalculation: research/recalculate_prev_day_range_break_retest_public_fees.py
- Funding data artifact: [run 43671994620 / artifact 14145011170](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/43671994620)
- BTC/ETH 15m data artifact: [run 43752078487 / artifact 14176194941](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/43752078487)
- PDRT trade ledger artifact: [run 43857702736 / artifact 14221154137](https://github.com/undaviyabrijesh-sys/SMC-crypto-alerts/actions/runs/43857702736)

Run the event study with the two CSV directories extracted from those artifacts:
python research/btc_eth_funding_sentiment_event_study.py --price-dir <price-dir> --funding-dir <funding-dir> --output-dir <output-dir>.
